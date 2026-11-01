import os
import uuid
import shutil
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.document import Document, DocumentChunk
from app.models.unanswered import UnansweredQuestion
from app.schemas.document import DocumentResponse, DocumentUploadResponse, ManualQACreateRequest, ManualQAResponse
from app.utils.security import get_current_owner
from app.utils.upload_validator import read_and_validate_upload
from app.services.ingestion_queue import ingestion_queue, IngestionJob
from app.services.rag_engine import rag_engine

router = APIRouter(prefix="/api/documents", tags=["Knowledge Base & Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Uploads a PDF, DOCX, or TXT file and enqueues it for background parsing and vector indexing."""
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    content_bytes, sanitized_filename, ext = await read_and_validate_upload(file, max_bytes)

    # Save to disk in owner's isolated tenant directory
    business_upload_dir = os.path.join(settings.UPLOAD_DIRECTORY, owner.business_id)
    os.makedirs(business_upload_dir, exist_ok=True)
    
    unique_file_id = uuid.uuid4().hex[:8]
    disk_filename = f"{unique_file_id}_{sanitized_filename}"
    saved_file_path = os.path.join(business_upload_dir, disk_filename)

    with open(saved_file_path, "wb") as buffer:
        buffer.write(content_bytes)

    file_size = len(content_bytes)

    # Create document record with QUEUED status
    doc = Document(
        business_id=owner.business_id,
        file_name=sanitized_filename,
        file_type=ext.lstrip("."),
        storage_path=saved_file_path,
        file_size_bytes=file_size,
        status="QUEUED"
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Enqueue to background worker
    job = IngestionJob(
        document_id=doc.id,
        business_id=owner.business_id,
        file_path=saved_file_path,
        file_name=sanitized_filename
    )
    await ingestion_queue.enqueue(job)

    return DocumentUploadResponse(
        document_id=doc.id,
        file_name=sanitized_filename,
        status="QUEUED",
        message="Document uploaded successfully and queued for background indexing."
    )

@router.post("/manual-qa", response_model=ManualQAResponse, status_code=status.HTTP_201_CREATED)
async def create_manual_qa(
    req: ManualQACreateRequest,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Answers an unanswered question and saves it directly into the knowledge base.
    
    Immediately vectorizes and indexes the Q&A chunk so future customer queries retrieve it!
    """
    qa_title = f"Manual Q&A: {req.question[:50]}..."
    formatted_content = f"Question: {req.question.strip()}\nAnswer: {req.answer.strip()}"

    # 1. Create Document container
    doc = Document(
        business_id=owner.business_id,
        file_name=qa_title,
        file_type="manual_qa",
        file_size_bytes=len(formatted_content.encode("utf-8")),
        chunk_count=1,
        status="INDEXED",
        parser_used="manual"
    )
    db.add(doc)
    await db.flush()

    # 2. Create Chunk
    meta = {
        "document_name": qa_title,
        "page_number": 1,
        "chunk_index": 0,
        "business_id": owner.business_id,
        "document_id": doc.id,
        "category": req.category or "General"
    }

    chunk = DocumentChunk(
        document_id=doc.id,
        business_id=owner.business_id,
        chunk_index=0,
        page_number=1,
        content=formatted_content,
        payload=meta
    )
    db.add(chunk)
    await db.flush()

    # 3. If resolving an unanswered question, mark it resolved
    if req.unanswered_question_id:
        unans_query = select(UnansweredQuestion).where(
            UnansweredQuestion.id == req.unanswered_question_id,
            UnansweredQuestion.business_id == owner.business_id
        )
        unans = (await db.execute(unans_query)).scalar_one_or_none()
        if unans:
            unans.is_resolved = True
            unans.resolved_answer = req.answer.strip()
            unans.resolved_at = datetime.utcnow()

    await db.commit()

    # 4. Index immediately into Hybrid RAG Engine
    await rag_engine.index_document_chunks(
        owner.business_id, 
        [{
            "id": chunk.id,
            "content": formatted_content,
            "metadata": meta
        }]
    )

    return ManualQAResponse(
        document_id=doc.id,
        chunk_id=chunk.id,
        question=req.question,
        status="INDEXED",
        message="Verified Q&A saved and indexed into knowledge base successfully."
    )

@router.get("", response_model=List[DocumentResponse])
async def list_documents(owner: User = Depends(get_current_owner), db: AsyncSession = Depends(get_db)):
    """Lists all documents and manual Q&A items for the authenticated business owner."""
    query = select(Document).where(
        Document.business_id == owner.business_id
    ).order_by(desc(Document.created_at))
    
    result = await db.execute(query)
    docs = result.scalars().all()
    return docs

@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    document_id: str,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Deletes a document and immediately purges all associated chunks from vector and BM25 stores."""
    query = select(Document).where(
        Document.id == document_id,
        Document.business_id == owner.business_id
    )
    doc = (await db.execute(query)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # 1. Purge from vector store and BM25 index
    await rag_engine.delete_document_chunks(owner.business_id, document_id)

    # 2. Delete file from disk if exists
    if doc.storage_path and os.path.exists(doc.storage_path):
        try:
            os.remove(doc.storage_path)
        except Exception:
            pass

    # 3. Delete from database (cascades to DocumentChunk)
    await db.delete(doc)
    await db.commit()

    return {"status": "success", "message": f"Document '{doc.file_name}' and its knowledge chunks were permanently removed."}
