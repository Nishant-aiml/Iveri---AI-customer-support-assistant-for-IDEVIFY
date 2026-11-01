import time
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc
from app.database import get_db
from app.models.user import User
from app.models.business import Business
from app.models.document import Document, DocumentChunk
from app.models.chat import ChatSession, ChatMessage
from app.models.unanswered import UnansweredQuestion
from app.utils.security import get_current_owner
from app.schemas.chat import ChatMessageResponse, SourceCitation
from app.schemas.dashboard import (
    DashboardStatsResponse, UnansweredQuestionItem,
    ResolveQuestionRequest, ResolveQuestionResponse,
    PlaygroundTestRequest, PlaygroundTestResponse, PlaygroundChunkDetail,
    ChatSessionSummary
)
from app.services.vector_store import vector_store_service
from app.services.bm25_store import bm25_store_service
from app.services.circuit_breaker import circuit_breaker
from app.services.rag_engine import rag_engine

router = APIRouter(prefix="/api/dashboard", tags=["Owner Dashboard"])

@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Returns aggregated high-level performance metrics for the authenticated business."""
    biz_id = owner.business_id

    # 1. Total chat sessions
    chats_count = (await db.execute(
        select(func.count(ChatSession.id)).where(ChatSession.business_id == biz_id)
    )).scalar() or 0

    # 2. Total customer questions asked
    questions_count = (await db.execute(
        select(func.count(ChatMessage.id))
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.business_id == biz_id, ChatMessage.sender == "customer")
    )).scalar() or 0

    # 3. Answered & Unanswered counts
    answered_count = (await db.execute(
        select(func.count(ChatMessage.id))
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(
            ChatSession.business_id == biz_id,
            ChatMessage.sender == "assistant",
            ChatMessage.is_answered.is_(True)
        )
    )).scalar() or 0

    unanswered_count = (await db.execute(
        select(func.count(ChatMessage.id))
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(
            ChatSession.business_id == biz_id,
            ChatMessage.sender == "assistant",
            ChatMessage.is_answered.is_(False)
        )
    )).scalar() or 0

    # 4. Resolution rate %
    total_assistant_replies = answered_count + unanswered_count
    resolution_rate = (
        round((answered_count / total_assistant_replies) * 100.0, 1)
        if total_assistant_replies > 0 else 100.0
    )

    # 5. Average latency in ms
    avg_latency = (await db.execute(
        select(func.avg(ChatMessage.latency_ms))
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.business_id == biz_id, ChatMessage.sender == "assistant")
    )).scalar() or 0.0

    # 6. Customer feedback totals
    thumbs_up = (await db.execute(
        select(func.count(ChatMessage.id))
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.business_id == biz_id, ChatMessage.feedback == "up")
    )).scalar() or 0

    thumbs_down = (await db.execute(
        select(func.count(ChatMessage.id))
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.business_id == biz_id, ChatMessage.feedback == "down")
    )).scalar() or 0

    # 7. Document & Chunk inventory
    docs_count = (await db.execute(
        select(func.count(Document.id)).where(Document.business_id == biz_id)
    )).scalar() or 0

    chunks_count = (await db.execute(
        select(func.count(DocumentChunk.id)).where(DocumentChunk.business_id == biz_id)
    )).scalar() or 0

    return DashboardStatsResponse(
        total_chats=chats_count,
        total_questions=questions_count,
        answered_count=answered_count,
        unanswered_count=unanswered_count,
        resolution_rate=resolution_rate,
        avg_latency_ms=round(float(avg_latency), 1),
        thumbs_up_count=thumbs_up,
        thumbs_down_count=thumbs_down,
        total_documents=docs_count,
        indexed_chunks=chunks_count
    )

@router.get("/unanswered", response_model=List[UnansweredQuestionItem])
async def list_unanswered_questions(
    is_resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Lists customer questions where the AI lacked knowledge, with optional resolution filter."""
    biz_id = owner.business_id
    query = select(UnansweredQuestion).where(UnansweredQuestion.business_id == biz_id)
    if is_resolved is not None:
        query = query.where(UnansweredQuestion.is_resolved == is_resolved)
    
    query = query.order_by(desc(UnansweredQuestion.created_at))
    result = await db.execute(query)
    items = result.scalars().all()

    return [
        UnansweredQuestionItem(
            id=item.id,
            session_id=item.session_id,
            question_text=item.question_text,
            customer_email=item.customer_email,
            top_retrieval_score=item.top_retrieval_score,
            is_resolved=item.is_resolved,
            resolved_answer=item.resolved_answer,
            resolved_at=item.resolved_at,
            created_at=item.created_at
        )
        for item in items
    ]

@router.post("/unanswered/{unanswered_id}/resolve", response_model=ResolveQuestionResponse)
async def resolve_unanswered_question(
    unanswered_id: str,
    req: ResolveQuestionRequest,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """
    Closed-Loop Knowledge Ingestion:
    Owner enters ground-truth answer for an unanswered question.
    The system immediately embeds and indexes the Q&A chunk into BM25 and ChromaDB,
    ensuring future matching customer inquiries are answered directly.
    """
    biz_id = owner.business_id
    q_query = select(UnansweredQuestion).where(
        UnansweredQuestion.id == unanswered_id,
        UnansweredQuestion.business_id == biz_id
    )
    unanswered = (await db.execute(q_query)).scalar_one_or_none()
    if not unanswered:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unanswered question not found."
        )

    # 1. Create a dedicated knowledge base manual document
    doc_title = f"Resolved Q&A: {unanswered.question_text[:40]}"
    doc = Document(
        business_id=biz_id,
        file_name="Manual Q&A Entry",
        storage_path="manual://qa",
        file_size_bytes=len(req.answer_text.encode("utf-8")),
        file_type="manual_qa",
        status="INDEXED",
        parser_used="manual",
        chunk_count=1
    )
    db.add(doc)
    await db.flush()

    # 2. Format Q&A chunk
    chunk_text = f"Question: {unanswered.question_text.strip()}\nAnswer: {req.answer_text.strip()}"
    chunk = DocumentChunk(
        document_id=doc.id,
        business_id=biz_id,
        chunk_index=0,
        page_number=1,
        content=chunk_text,
    )
    chunk.payload = {
        "document_name": doc_title,
        "source_type": "resolved_qa",
        "page_number": 1,
        "unanswered_id": unanswered_id
    }
    db.add(chunk)
    await db.flush()

    # 3. Index immediately into ChromaDB & BM25
    chunk_item = {
        "id": chunk.id,
        "content": chunk_text,
        "metadata": {
            "document_name": doc_title,
            "page_number": 1,
            "document_id": doc.id,
            "source_type": "resolved_qa"
        }
    }
    await vector_store_service.add_chunks(biz_id, [chunk_item])
    bm25_store_service.add_chunks(biz_id, [chunk_item])

    # 4. Mark question as resolved
    unanswered.is_resolved = True
    unanswered.resolved_answer = req.answer_text.strip()
    unanswered.resolved_at = datetime.utcnow()

    await db.commit()

    return ResolveQuestionResponse(
        status="success",
        unanswered_id=unanswered.id,
        is_resolved=True,
        document_id=doc.id,
        chunks_created=1,
        message="Question resolved and permanently indexed into the business knowledge base."
    )

@router.get("/chats", response_model=List[ChatSessionSummary])
async def list_chat_sessions(
    feedback: Optional[str] = Query(None, description="Filter by customer feedback: 'down' or 'up'"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Lists customer conversation history with optional filtering for downvoted answers."""
    biz_id = owner.business_id

    query = select(ChatSession).where(ChatSession.business_id == biz_id)

    if feedback:
        # Subquery for sessions containing matching feedback
        subq = (
            select(ChatMessage.session_id)
            .where(ChatMessage.feedback == feedback)
            .distinct()
        )
        query = query.where(ChatSession.id.in_(subq))

    query = query.order_by(desc(ChatSession.last_message_at)).offset(offset).limit(limit)
    sessions = (await db.execute(query)).scalars().all()

    summaries = []
    for s in sessions:
        # Load messages for this session
        msg_query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == s.id)
            .order_by(ChatMessage.created_at)
        )
        messages = (await db.execute(msg_query)).scalars().all()
        has_downvote = any(m.feedback == "down" for m in messages)

        msg_responses = [
            ChatMessageResponse(
                id=m.id,
                session_id=m.session_id,
                sender=m.sender,
                content=m.content,
                is_answered=m.is_answered,
                feedback=m.feedback,
                confidence_score=m.confidence_score,
                latency_ms=m.latency_ms,
                llm_provider_used=m.llm_provider_used,
                citations=[SourceCitation(**c) for c in m.source_citations],
                created_at=m.created_at
            )
            for m in messages
        ]

        summaries.append(ChatSessionSummary(
            session_id=s.id,
            channel=s.channel,
            customer_email=s.customer_email,
            started_at=s.created_at,
            message_count=len(messages),
            has_downvote=has_downvote,
            messages=msg_responses
        ))

    return summaries

@router.post("/playground", response_model=PlaygroundTestResponse)
async def test_playground_query(
    req: PlaygroundTestRequest,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """
    RAG Playground for the Business Owner:
    Executes dense, sparse, and hybrid retrieval against uploaded documents,
    evaluating circuit-breaker threshold pass/fail with full scoring diagnostics.
    """
    biz_id = owner.business_id
    query_text = req.query.strip()
    start_time = time.time()

    # 1. Fetch Business Settings
    biz = (await db.execute(select(Business).where(Business.id == biz_id))).scalar_one_or_none()
    fallback_msg = biz.fallback_message if biz else "I apologize, but I do not have sufficient information."
    biz_settings = {
        "name": biz.name if biz else "Business",
        "tone": biz.tone if biz else "professional",
        "fallback_message": fallback_msg
    }

    # 2. Retrieve BM25 sparse results
    bm25_hits = bm25_store_service.search(biz_id, query_text, top_k=3)
    # 3. Retrieve ChromaDB dense results
    dense_hits = await vector_store_service.search(biz_id, query_text, top_k=3)

    chunk_details: List[PlaygroundChunkDetail] = []
    for hit in bm25_hits:
        meta = hit.get("metadata", {})
        chunk_details.append(PlaygroundChunkDetail(
            chunk_id=hit.get("id", ""),
            document_name=meta.get("document_name", "Document"),
            page_number=int(meta.get("page_number", 1)),
            text_excerpt=hit.get("content", "")[:160] + "...",
            score=round(float(hit.get("score", 0.0)), 4),
            retrieval_type="bm25_sparse"
        ))

    for hit in dense_hits:
        meta = hit.get("metadata", {})
        chunk_details.append(PlaygroundChunkDetail(
            chunk_id=hit.get("id", ""),
            document_name=meta.get("document_name", "Document"),
            page_number=int(meta.get("page_number", 1)),
            text_excerpt=hit.get("content", "")[:160] + "...",
            score=round(float(hit.get("score", 0.0)), 4),
            retrieval_type="dense_vector"
        ))

    # 4. Run RAG Engine Pipeline
    rag_result = await rag_engine.query(
        business_id=biz_id,
        user_query=query_text,
        business_settings=biz_settings
    )

    elapsed_ms = int((time.time() - start_time) * 1000)

    cb_passed = rag_result["is_answered"]
    cb_reason = (
        "Sufficient grounded context retrieved above confidence threshold."
        if cb_passed else
        "Circuit breaker triggered: insufficient keyword/vector similarity in uploaded documents."
    )

    return PlaygroundTestResponse(
        query=query_text,
        circuit_breaker_passed=cb_passed,
        circuit_breaker_reason=cb_reason,
        retrieved_chunks=chunk_details,
        top_confidence=rag_result["confidence_score"],
        generated_answer=rag_result["answer"],
        llm_provider=rag_result["llm_provider"],
        latency_ms=elapsed_ms
    )
