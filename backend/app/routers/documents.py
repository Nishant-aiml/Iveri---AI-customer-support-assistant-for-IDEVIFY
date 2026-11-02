import asyncio
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.document import Document, DocumentChunk
from app.models.unanswered import UnansweredQuestion
from app.schemas.document import DocumentResponse, DocumentUploadResponse, DocumentUploadItem, ManualQACreateRequest, ManualQAResponse
from app.utils.security import get_current_owner, security_scheme, decode_access_token
from app.utils.upload_validator import read_and_validate_upload
from app.services.ingestion_queue import ingestion_queue, IngestionJob
from app.services.rag_engine import rag_engine

router = APIRouter(prefix="/api/documents", tags=["Knowledge Base & Documents"])

ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md",
    ".xlsx", ".xls",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"
}

_biz_upload_locks: Dict[str, asyncio.Lock] = {}

def _get_biz_lock(business_id: str) -> asyncio.Lock:
    if business_id not in _biz_upload_locks:
        _biz_upload_locks[business_id] = asyncio.Lock()
    return _biz_upload_locks[business_id]

@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Uploads one or multiple documents (PDF, DOCX, TXT, Excel .xlsx/.xls, Images .png/.jpg/.webp)
    and enqueues them for background parsing and vector indexing with Docling, Tesseract OCR, and openpyxl.
    Guarantees strict single-document idempotency per filename per business tenant.
    """
    biz_lock = _get_biz_lock(owner.business_id)
    async with biz_lock:
        incoming_files: List[UploadFile] = []
        seen_names = set()
        all_uploads: List[UploadFile] = []
        if files:
            all_uploads.extend([f for f in files if f and f.filename])
        elif file and file.filename:
            all_uploads.append(file)

        for f in all_uploads:
            norm = os.path.basename(f.filename).strip()
            if norm.lower() not in seen_names:
                seen_names.add(norm.lower())
                incoming_files.append(f)

        if not incoming_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No document files provided. Please select at least one document to upload."
            )

        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        business_upload_dir = os.path.join(settings.UPLOAD_DIRECTORY, owner.business_id)
        os.makedirs(business_upload_dir, exist_ok=True)

        queued_items: List[DocumentUploadItem] = []

        for upload_item in incoming_files:
            content_bytes, sanitized_filename, ext = await read_and_validate_upload(upload_item, max_bytes)

            # Check if existing document(s) with the exact same name exist for this business
            existing_docs = (await db.execute(
                select(Document).where(
                    Document.business_id == owner.business_id,
                    Document.file_name == sanitized_filename
                )
            )).scalars().all()

            for old_doc in existing_docs:
                # Cleanly purge prior vector & BM25 chunks to prevent duplicate chunk clutter
                await rag_engine.delete_document_chunks(owner.business_id, old_doc.id)
                if old_doc.storage_path and os.path.exists(old_doc.storage_path):
                    try:
                        os.remove(old_doc.storage_path)
                    except Exception:
                        pass
                await db.delete(old_doc)
            if existing_docs:
                await db.flush()

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

            queued_items.append(DocumentUploadItem(
                document_id=doc.id,
                file_name=sanitized_filename,
                status="QUEUED",
                message="Document queued for indexing."
            ))

        first_item = queued_items[0]
        total_count = len(queued_items)
        summary_message = (
            f"{total_count} documents uploaded successfully and queued for background indexing."
            if total_count > 1
            else "Document uploaded successfully and queued for background indexing."
        )

        return DocumentUploadResponse(
            document_id=first_item.document_id,
            file_name=first_item.file_name,
            status="QUEUED",
            message=summary_message,
            uploaded_files=queued_items,
            total_queued=total_count
        )

@router.post("/batch-upload", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def batch_upload_documents(
    files: List[UploadFile] = File(...),
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Batch uploads multiple documents simultaneously."""
    return await upload_document(files=files, file=None, owner=owner, db=db)

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

async def _resolve_doc_owner(
    token: Optional[str] = None,
    auth: Optional[HTTPAuthorizationCredentials] = None,
    db: AsyncSession = None
) -> User:
    raw_token = auth.credentials if (auth and auth.credentials) else token
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication token required.")
    payload = decode_access_token(raw_token)
    user_id = payload.get("sub") if payload else None
    if not user_id:
        try:
            from app.services.firebase_auth import firebase_auth_service
            fb_decoded = firebase_auth_service.verify_token(raw_token)
            user_id = fb_decoded.get("uid")
        except Exception:
            pass
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token.")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or user.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Business owner role required.")
    return user

@router.get("/{document_id}/file")
async def preview_document_file(
    document_id: str,
    token: Optional[str] = Query(None),
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db)
):
    """Streams the raw uploaded PDF or document file inline so the business owner can cross-verify documents."""
    owner = await _resolve_doc_owner(token=token, auth=auth, db=db)
    query = select(Document).where(
        Document.id == document_id,
        Document.business_id == owner.business_id
    )
    doc = (await db.execute(query)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if not doc.storage_path or not os.path.exists(doc.storage_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical document file not found on disk.")

    ext = os.path.splitext(doc.file_name)[1].lower()
    media_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
    }
    media_type = media_map.get(ext, "application/octet-stream")

    return FileResponse(
        path=doc.storage_path,
        media_type=media_type,
        filename=doc.file_name,
        content_disposition_type="inline"
    )

@router.get("/{document_id}/chunks")
async def get_document_chunks(
    document_id: str,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves all indexed vector & BM25 chunks for an uploaded document for owner cross-verification."""
    query = select(Document).where(
        Document.id == document_id,
        Document.business_id == owner.business_id
    )
    doc = (await db.execute(query)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    chunks_q = select(DocumentChunk).where(
        DocumentChunk.document_id == document_id,
        DocumentChunk.business_id == owner.business_id
    ).order_by(DocumentChunk.chunk_index)
    chunks = (await db.execute(chunks_q)).scalars().all()

    return {
        "document_id": doc.id,
        "file_name": doc.file_name,
        "file_type": doc.file_type,
        "total_chunks": len(chunks),
        "total_pages": doc.total_pages,
        "status": doc.status,
        "parser_used": doc.parser_used,
        "chunks": [
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "content": c.content,
                "metadata": c.payload
            }
            for c in chunks
        ]
    }
