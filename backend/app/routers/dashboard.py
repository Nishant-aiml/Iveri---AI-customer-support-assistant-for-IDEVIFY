import csv
import io
import time
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc, delete, update
from app.database import get_db
from app.models.user import User
from app.models.business import Business
from app.models.document import Document, DocumentChunk
from app.models.chat import ChatSession, ChatMessage
from app.models.unanswered import UnansweredQuestion
from app.models.ticket import Ticket
from app.utils.security import get_current_owner, decode_access_token, security_scheme

logger = logging.getLogger("idevify-dashboard-router")
from fastapi.security import HTTPAuthorizationCredentials
from app.schemas.chat import ChatMessageResponse, SourceCitation
from app.schemas.dashboard import (
    DashboardStatsResponse, UnansweredQuestionItem,
    ResolveQuestionRequest, ResolveQuestionResponse,
    PlaygroundTestRequest, PlaygroundTestResponse, PlaygroundChunkDetail,
    ChatSessionSummary, BusinessAnalyticsResponse,
    SentimentBreakdown, TopicCount, DailyTrendItem,
    TrendBucketItem, AnalyticsSummary,
    ResolutionFunnel, LatencySummary
)
from app.services.vector_store import vector_store_service
from app.services.bm25_store import bm25_store_service
from app.services.rag_engine import rag_engine
from app.services.sentiment_analyzer import sentiment_analyzer
from app.services.topic_analyzer import topic_analyzer
from app.services.laya_router import laya_service

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

    # 2. Aggregated message statistics in a single optimized pass
    msg_stats = (await db.execute(
        select(
            func.count(ChatMessage.id).filter(ChatMessage.sender == "customer").label("questions_count"),
            func.count(ChatMessage.id).filter(ChatMessage.sender == "assistant", ChatMessage.is_answered.is_(True)).label("answered_count"),
            func.count(ChatMessage.id).filter(ChatMessage.sender == "assistant", ChatMessage.is_answered.is_(False)).label("unanswered_count"),
            func.avg(ChatMessage.latency_ms).filter(ChatMessage.sender == "assistant").label("avg_latency"),
            func.count(ChatMessage.id).filter(ChatMessage.feedback == "up").label("thumbs_up"),
            func.count(ChatMessage.id).filter(ChatMessage.feedback == "down").label("thumbs_down")
        )
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.business_id == biz_id)
    )).one()

    questions_count = msg_stats.questions_count or 0
    answered_count = msg_stats.answered_count or 0
    raw_unanswered_count = msg_stats.unanswered_count or 0
    avg_latency = msg_stats.avg_latency or 0.0
    thumbs_up = msg_stats.thumbs_up or 0
    thumbs_down = msg_stats.thumbs_down or 0

    # 2b. Synchronize with live active support tickets & pending unanswered gaps
    open_tickets_count = (await db.execute(
        select(func.count(Ticket.id)).where(Ticket.business_id == biz_id, Ticket.status == "open")
    )).scalar() or 0

    if open_tickets_count == 0 and raw_unanswered_count > 0:
        # Self-heal orphaned unanswered messages from tickets that were resolved or deleted by owner
        try:
            await db.execute(
                update(ChatMessage)
                .where(
                    ChatMessage.session_id.in_(
                        select(ChatSession.id).where(ChatSession.business_id == biz_id)
                    ),
                    ChatMessage.is_answered.is_(False)
                )
                .values(is_answered=True)
            )
            await db.execute(
                update(UnansweredQuestion)
                .where(
                    UnansweredQuestion.business_id == biz_id,
                    UnansweredQuestion.is_resolved.is_(False)
                )
                .values(is_resolved=True, resolved_at=datetime.utcnow())
            )
            await db.commit()
        except Exception as heal_err:
            logger.warning(f"Self-healing orphaned unanswered gaps note: {heal_err}")

        answered_count += raw_unanswered_count
        unanswered_count = 0
    else:
        unanswered_count = open_tickets_count if open_tickets_count > 0 else raw_unanswered_count

    # 3. Resolution rate %
    total_assistant_replies = answered_count + unanswered_count
    resolution_rate = (
        round((answered_count / total_assistant_replies) * 100.0, 1)
        if total_assistant_replies > 0 else 100.0
    )

    # 4. Document & Chunk inventory in a single pass
    doc_stats = (await db.execute(
        select(
            func.count(Document.id).label("total_docs"),
            func.coalesce(func.sum(Document.chunk_count), 0).label("indexed_chunks")
        ).where(Document.business_id == biz_id)
    )).one()

    docs_count = doc_stats.total_docs or 0
    chunks_count = doc_stats.indexed_chunks or 0

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

    # 4b. Reconcile corresponding ChatMessage and Ticket
    try:
        if unanswered.message_id:
            await db.execute(
                update(ChatMessage)
                .where(ChatMessage.id == unanswered.message_id)
                .values(is_answered=True)
            )
        elif unanswered.session_id:
            await db.execute(
                update(ChatMessage)
                .where(
                    ChatMessage.session_id == unanswered.session_id,
                    ChatMessage.is_answered.is_(False)
                )
                .values(is_answered=True)
            )

        ticket_q = select(Ticket).where(
            Ticket.business_id == biz_id,
            Ticket.status == "open",
            (
                (Ticket.message_id == unanswered.message_id) |
                (Ticket.description == unanswered.question_text) |
                (Ticket.session_id == unanswered.session_id)
            )
        )
        matched_tickets = (await db.execute(ticket_q)).scalars().all()
        for t in matched_tickets:
            t.status = "resolved"
            t.resolved_answer = req.answer_text.strip()
            t.resolved_at = datetime.utcnow()
    except Exception as sync_err:
        logger.warning(f"Note syncing Ticket/ChatMessage from resolve_unanswered_question: {sync_err}")

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
    sentiment: Optional[str] = Query(None, description="Filter by customer sentiment: 'positive', 'neutral', 'negative'"),
    topic: Optional[str] = Query(None, description="Filter by topic: 'pricing', 'shipping', 'returns', 'products', 'support'"),
    channel: Optional[str] = Query(None, description="Filter by channel: 'widget', 'whatsapp', 'public_link'"),
    search: Optional[str] = Query(None, description="Search by email or question keyword"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Lists customer conversation history with multi-filter and sentiment analytics."""
    biz_id = owner.business_id

    query = select(ChatSession).where(ChatSession.business_id == biz_id)

    if channel:
        query = query.where(ChatSession.channel == channel)

    if feedback:
        subq = (
            select(ChatMessage.session_id)
            .where(ChatMessage.feedback == feedback)
            .distinct()
        )
        query = query.where(ChatSession.id.in_(subq))

    if sentiment:
        subq_sent = (
            select(ChatMessage.session_id)
            .where(
                (ChatMessage.sentiment == sentiment) |
                (ChatMessage.feedback == ("down" if sentiment == "negative" else "up" if sentiment == "positive" else None))
            )
            .distinct()
        )
        query = query.where((ChatSession.sentiment == sentiment) | (ChatSession.id.in_(subq_sent)))

    if topic:
        subq_topic = (
            select(ChatMessage.session_id)
            .where(ChatMessage.topic == topic)
            .distinct()
        )
        query = query.where((ChatSession.primary_topic == topic) | (ChatSession.id.in_(subq_topic)))

    if search:
        search_filter = f"%{search.strip().lower()}%"
        subq_msg = (
            select(ChatMessage.session_id)
            .where(func.lower(ChatMessage.content).like(search_filter))
            .distinct()
        )
        query = query.where(
            (func.lower(ChatSession.customer_email).like(search_filter)) |
            (ChatSession.id.in_(subq_msg))
        )

    query = query.order_by(desc(ChatSession.last_message_at)).offset(offset).limit(limit)
    sessions = (await db.execute(query)).scalars().all()

    # High-Performance Batch Optimization: Fetch all messages for these sessions in 1 batch query (eliminates N+1 DB roundtrips)
    session_ids = [s.id for s in sessions]
    messages_by_session: dict[str, list[ChatMessage]] = {sid: [] for sid in session_ids}
    if session_ids:
        batch_msg_query = (
            select(ChatMessage)
            .where(ChatMessage.session_id.in_(session_ids))
            .order_by(ChatMessage.created_at)
        )
        all_msgs = (await db.execute(batch_msg_query)).scalars().all()
        for m in all_msgs:
            if m.session_id in messages_by_session:
                messages_by_session[m.session_id].append(m)

    summaries = []
    for s in sessions:
        messages = messages_by_session.get(s.id, [])
        has_downvote = any(m.feedback == "down" for m in messages)
        has_negative_msg = any(m.sentiment == "negative" or m.feedback == "down" for m in messages)
        has_positive_msg = any(m.sentiment == "positive" or m.feedback == "up" for m in messages)

        # Session sentiment hierarchy:
        # Any frustrated message or downvote marks the session as negative
        if has_negative_msg or s.sentiment == "negative":
            session_sentiment = "negative"
        elif has_positive_msg or s.sentiment == "positive":
            session_sentiment = "positive"
        elif s.sentiment and s.sentiment != "neutral":
            session_sentiment = s.sentiment
        else:
            session_sentiment = "neutral"

        session_topic = s.primary_topic or "general"
        if messages and session_topic == "general":
            customer_msgs = [m for m in messages if m.sender == "customer"]
            if customer_msgs:
                latest_customer_text = customer_msgs[-1].content
                session_topic = topic_analyzer.classify(latest_customer_text)

        msg_responses = [
            ChatMessageResponse(
                id=m.id,
                session_id=m.session_id,
                sender=m.sender,
                content=m.content,
                is_answered=m.is_answered,
                feedback=m.feedback,
                sentiment=m.sentiment or "neutral",
                topic=m.topic or session_topic,
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
            sentiment=session_sentiment,
            primary_topic=session_topic,
            share_url=f"/share/{s.id}",
            started_at=s.created_at,
            message_count=len(messages),
            has_downvote=has_downvote,
            messages=msg_responses
        ))

    return summaries

@router.get("/chats/{session_id}", response_model=ChatSessionSummary)
async def get_chat_session_detail(
    session_id: str,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves full conversation details for a specific session (used by Master-Detail 2-pane view)."""
    biz_id = owner.business_id
    query = select(ChatSession).where(ChatSession.id == session_id, ChatSession.business_id == biz_id)
    session = (await db.execute(query)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found.")

    msg_query = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at)
    )
    messages = (await db.execute(msg_query)).scalars().all()
    has_downvote = any(m.feedback == "down" for m in messages)
    has_negative_msg = any(m.sentiment == "negative" or m.feedback == "down" for m in messages)
    has_positive_msg = any(m.sentiment == "positive" or m.feedback == "up" for m in messages)

    if has_negative_msg or session.sentiment == "negative":
        effective_sentiment = "negative"
    elif has_positive_msg or session.sentiment == "positive":
        effective_sentiment = "positive"
    elif session.sentiment:
        effective_sentiment = session.sentiment
    else:
        effective_sentiment = "neutral"

    msg_responses = [
        ChatMessageResponse(
            id=m.id,
            session_id=m.session_id,
            sender=m.sender,
            content=m.content,
            is_answered=m.is_answered,
            feedback=m.feedback,
            sentiment=m.sentiment or "neutral",
            topic=m.topic or session.primary_topic or "general",
            confidence_score=m.confidence_score,
            latency_ms=m.latency_ms,
            llm_provider_used=m.llm_provider_used,
            citations=[SourceCitation(**c) for c in m.source_citations],
            created_at=m.created_at
        )
        for m in messages
    ]

    return ChatSessionSummary(
        session_id=session.id,
        channel=session.channel,
        customer_email=session.customer_email,
        sentiment=effective_sentiment,
        primary_topic=session.primary_topic or "general",
        share_url=f"/share/{session.id}",
        started_at=session.created_at,
        message_count=len(messages),
        has_downvote=has_downvote,
        messages=msg_responses
    )

@router.delete("/chats/{session_id}", status_code=status.HTTP_200_OK)
async def delete_chat_session(
    session_id: str,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Permanently deletes a customer conversation session and all its messages."""
    biz_id = owner.business_id
    query = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.business_id == biz_id
    )
    session = (await db.execute(query)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found.")

    from app.models.ticket import Ticket
    from app.models.chat import ChatMessage
    from app.models.unanswered import UnansweredQuestion

    # 1. Unlink tickets
    await db.execute(
        update(Ticket).where(Ticket.session_id == session.id).values(session_id=None, message_id=None)
    )

    # 2. Delete unanswered questions linked to this session
    await db.execute(
        delete(UnansweredQuestion).where(
            UnansweredQuestion.session_id == session.id,
            UnansweredQuestion.business_id == biz_id
        )
    )

    # 3. Explicitly delete all chat messages for this session to prevent FK constraint failures
    await db.execute(
        delete(ChatMessage).where(ChatMessage.session_id == session.id)
    )

    # 4. Delete the session
    await db.delete(session)
    await db.commit()
    return {"status": "success", "message": "Conversation session deleted successfully."}

@router.get("/analytics", response_model=BusinessAnalyticsResponse)
async def get_business_analytics(
    days: int = Query(7, ge=1, le=365),
    granularity: str = Query("date", pattern="^(date|day|year)$"),
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """
    Executive Business Analytics:
    Calculates customer sentiment distribution, top inquiry topics, resolution funnel,
    and switchable YouTube Analytics-style trends (Date, Day of Week, Year) comparing
    Answered vs. Unanswered volume for executive decision-making.
    """
    biz_id = owner.business_id

    # Determine window cutoff based on granularity
    if granularity == "year":
        effective_days = max(days, 365)
    elif granularity == "day":
        effective_days = max(days, 90)
    else:
        effective_days = days

    cutoff = datetime.utcnow() - timedelta(days=effective_days)

    # 1. Fetch all customer & assistant messages within date window
    query = (
        select(ChatMessage)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.business_id == biz_id, ChatMessage.created_at >= cutoff)
        .order_by(ChatMessage.created_at)
    )
    all_msgs = (await db.execute(query)).scalars().all()

    customer_msgs = [m for m in all_msgs if m.sender == "customer"]
    assistant_msgs = [m for m in all_msgs if m.sender == "assistant"]

    total_queries = len(customer_msgs)

    # 2. Sentiment Breakdown
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
    for m in customer_msgs:
        s = m.sentiment or sentiment_analyzer.analyze(m.content, m.feedback)[0]
        if s in sentiment_counts:
            sentiment_counts[s] += 1
        else:
            sentiment_counts["neutral"] += 1

    total_s = max(total_queries, 1)
    sentiment_breakdown = SentimentBreakdown(
        positive=sentiment_counts["positive"],
        neutral=sentiment_counts["neutral"],
        negative=sentiment_counts["negative"],
        positive_pct=round((sentiment_counts["positive"] / total_s) * 100, 1),
        neutral_pct=round((sentiment_counts["neutral"] / total_s) * 100, 1),
        negative_pct=round((sentiment_counts["negative"] / total_s) * 100, 1)
    )

    # 3. Topic Counts
    topic_map = {"pricing": 0, "shipping": 0, "returns": 0, "products": 0, "support": 0, "general": 0}
    for m in customer_msgs:
        t = (m.topic or topic_analyzer.classify(m.content)).lower()
        if t in topic_map:
            topic_map[t] += 1
        elif any(k in t for k in ["price", "cost", "bill", "gst"]):
            topic_map["pricing"] += 1
        elif any(k in t for k in ["ship", "delivery", "track"]):
            topic_map["shipping"] += 1
        elif any(k in t for k in ["return", "refund"]):
            topic_map["returns"] += 1
        elif any(k in t for k in ["product", "item", "plan"]):
            topic_map["products"] += 1
        else:
            topic_map["general"] += 1

    top_topics = [
        TopicCount(topic=k, count=v, percentage=round((v / total_s) * 100, 1))
        for k, v in sorted(topic_map.items(), key=lambda item: item[1], reverse=True)
        if v > 0
    ]

    # 4. Multi-Granular Trends (Date, Day of Week, Year)
    trend_buckets = []
    daily_trend = []

    if granularity == "day":
        # Day of week aggregation (Monday - Sunday)
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        day_stats = {name: {"label": short, "total_queries": 0, "answered": 0, "unanswered": 0, "positive": 0, "negative": 0}
                     for name, short in zip(day_names, day_short)}

        for m in customer_msgs:
            d_name = m.created_at.strftime("%A")
            if d_name in day_stats:
                day_stats[d_name]["total_queries"] += 1
                s = m.sentiment or sentiment_analyzer.analyze(m.content)[0]
                if s == "positive":
                    day_stats[d_name]["positive"] += 1
                elif s == "negative":
                    day_stats[d_name]["negative"] += 1

        for m in assistant_msgs:
            d_name = m.created_at.strftime("%A")
            if d_name in day_stats:
                if m.is_answered:
                    day_stats[d_name]["answered"] += 1
                else:
                    day_stats[d_name]["unanswered"] += 1

        for name in day_names:
            v = day_stats[name]
            resolved = v["answered"]
            unres = v["unanswered"]
            rate = round((resolved / max(resolved + unres, 1)) * 100, 1) if (resolved + unres) > 0 else 100.0
            item = TrendBucketItem(
                label=v["label"],
                date=name,
                total_queries=v["total_queries"],
                answered=resolved,
                unanswered=unres,
                resolution_rate=rate,
                positive=v["positive"],
                negative=v["negative"]
            )
            trend_buckets.append(item)
            daily_trend.append(DailyTrendItem(
                date=name,
                total_queries=v["total_queries"],
                answered=resolved,
                unanswered=unres,
                positive=v["positive"],
                negative=v["negative"]
            ))
        window_desc = f"Aggregated by Day of Week (Last {effective_days} Days)"

    elif granularity == "year":
        # 12-Month Annual Macro Trend
        now = datetime.utcnow()
        months = []
        for i in range(11, -1, -1):
            y = now.year
            m = now.month - i
            while m <= 0:
                m += 12
                y -= 1
            key = f"{y:04d}-{m:02d}"
            dt_repr = datetime(y, m, 1)
            lbl = dt_repr.strftime("%b %y")
            months.append((key, lbl))

        month_stats = {k: {"label": lbl, "total_queries": 0, "answered": 0, "unanswered": 0, "positive": 0, "negative": 0}
                       for k, lbl in months}

        for m in customer_msgs:
            m_key = m.created_at.strftime("%Y-%m")
            if m_key in month_stats:
                month_stats[m_key]["total_queries"] += 1
                s = m.sentiment or sentiment_analyzer.analyze(m.content)[0]
                if s == "positive":
                    month_stats[m_key]["positive"] += 1
                elif s == "negative":
                    month_stats[m_key]["negative"] += 1

        for m in assistant_msgs:
            m_key = m.created_at.strftime("%Y-%m")
            if m_key in month_stats:
                if m.is_answered:
                    month_stats[m_key]["answered"] += 1
                else:
                    month_stats[m_key]["unanswered"] += 1

        for key, lbl in months:
            v = month_stats[key]
            resolved = v["answered"]
            unres = v["unanswered"]
            rate = round((resolved / max(resolved + unres, 1)) * 100, 1) if (resolved + unres) > 0 else 100.0
            item = TrendBucketItem(
                label=v["label"],
                date=key,
                total_queries=v["total_queries"],
                answered=resolved,
                unanswered=unres,
                resolution_rate=rate,
                positive=v["positive"],
                negative=v["negative"]
            )
            trend_buckets.append(item)
            daily_trend.append(DailyTrendItem(
                date=key,
                total_queries=v["total_queries"],
                answered=resolved,
                unanswered=unres,
                positive=v["positive"],
                negative=v["negative"]
            ))
        window_desc = "12-Month Annual Trend"

    else:
        # Default: "date" granularity (last N days)
        daily_groups = {}
        for d in range(days):
            day_dt = datetime.utcnow() - timedelta(days=days - 1 - d)
            day_str = day_dt.strftime("%Y-%m-%d")
            day_lbl = day_dt.strftime("%b %d") if days <= 14 else day_dt.strftime("%m/%d")
            daily_groups[day_str] = {
                "label": day_lbl,
                "total_queries": 0,
                "answered": 0,
                "unanswered": 0,
                "positive": 0,
                "negative": 0
            }

        for m in customer_msgs:
            day_str = m.created_at.strftime("%Y-%m-%d")
            if day_str in daily_groups:
                daily_groups[day_str]["total_queries"] += 1
                s = m.sentiment or sentiment_analyzer.analyze(m.content)[0]
                if s == "positive":
                    daily_groups[day_str]["positive"] += 1
                elif s == "negative":
                    daily_groups[day_str]["negative"] += 1

        for m in assistant_msgs:
            day_str = m.created_at.strftime("%Y-%m-%d")
            if day_str in daily_groups:
                if m.is_answered:
                    daily_groups[day_str]["answered"] += 1
                else:
                    daily_groups[day_str]["unanswered"] += 1

        for k, v in daily_groups.items():
            resolved = v["answered"]
            unres = v["unanswered"]
            rate = round((resolved / max(resolved + unres, 1)) * 100, 1) if (resolved + unres) > 0 else 100.0
            item = TrendBucketItem(
                label=v["label"],
                date=k,
                total_queries=v["total_queries"],
                answered=resolved,
                unanswered=unres,
                resolution_rate=rate,
                positive=v["positive"],
                negative=v["negative"]
            )
            trend_buckets.append(item)
            daily_trend.append(DailyTrendItem(
                date=k,
                total_queries=v["total_queries"],
                answered=resolved,
                unanswered=unres,
                positive=v["positive"],
                negative=v["negative"]
            ))
        window_desc = f"Last {days} Days Rolling Window"

    # Compute KPI Summary for the selected granularity
    total_handled = sum(item.total_queries for item in trend_buckets)
    total_ans = sum(item.answered for item in trend_buckets)
    total_unans = sum(item.unanswered for item in trend_buckets)
    overall_res_rate = round((total_ans / max(total_ans + total_unans, 1)) * 100, 1) if (total_ans + total_unans) > 0 else 100.0

    peak_bucket = max(trend_buckets, key=lambda x: x.total_queries, default=None)
    if peak_bucket and peak_bucket.total_queries > 0:
        peak_label = f"{peak_bucket.label} ({peak_bucket.total_queries} queries)"
        peak_count = peak_bucket.total_queries
    else:
        peak_label = "No volume yet"
        peak_count = 0

    analytics_summary = AnalyticsSummary(
        total_handled=total_handled,
        total_answered=total_ans,
        total_unanswered=total_unans,
        resolution_rate=overall_res_rate,
        peak_label=peak_label,
        peak_count=peak_count,
        time_grain=granularity,
        window_description=window_desc
    )

    # 5. Funnel
    total_sessions = (await db.execute(
        select(func.count(ChatSession.id)).where(ChatSession.business_id == biz_id, ChatSession.created_at >= cutoff)
    )).scalar() or 0

    ai_resolved = sum(1 for m in assistant_msgs if m.is_answered)
    human_needed = sum(1 for m in assistant_msgs if not m.is_answered)
    res_rate = round((ai_resolved / max(len(assistant_msgs), 1)) * 100, 1) if assistant_msgs else 100.0

    funnel = ResolutionFunnel(
        total_sessions=total_sessions,
        total_queries=total_queries,
        ai_resolved=ai_resolved,
        human_followup_needed=human_needed,
        resolution_rate=res_rate
    )

    # 6. Latency Metrics
    latencies = [m.latency_ms for m in assistant_msgs if m.latency_ms > 0]
    avg_ms = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
    min_ms = min(latencies) if latencies else 0
    max_ms = max(latencies) if latencies else 0
    sub_second = sum(1 for lat in latencies if lat < 1000)
    sub_second_pct = round((sub_second / max(len(latencies), 1)) * 100, 1) if latencies else 100.0

    latency_metrics = LatencySummary(
        avg_ms=avg_ms,
        min_ms=min_ms,
        max_ms=max_ms,
        sub_second_pct=sub_second_pct
    )

    return BusinessAnalyticsResponse(
        total_queries=total_queries,
        sentiment_breakdown=sentiment_breakdown,
        top_topics=top_topics,
        daily_trend=daily_trend,
        trend_data=trend_buckets,
        granularity=granularity,
        summary=analytics_summary,
        funnel=funnel,
        latency_metrics=latency_metrics
    )

@router.get("/export/powerbi")
async def export_powerbi_dataset(
    format: str = Query("csv", pattern="^(csv|json)$"),
    token: Optional[str] = Query(None),
    business_id: Optional[str] = Query(None),
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db)
):
    """
    Exports a clean, flattened tabular dataset formatted specifically for
    Power BI / Excel / Tableau customer sentiment and support analytics.
    Accepts authentication via Authorization header or ?token= query parameter.
    If unauthenticated (e.g. direct browser navigation or Power BI Web connector),
    seamlessly resolves the active store business dataset without 401 barriers.
    """
    biz_id = None
    raw_token = None
    if auth and auth.credentials:
        raw_token = auth.credentials
    elif token:
        raw_token = token

    if raw_token:
        payload = decode_access_token(raw_token)
        if payload and "sub" in payload:
            user_id = payload.get("sub")
            user_res = await db.execute(select(User).where(User.id == user_id))
            u = user_res.scalar_one_or_none()
            if u:
                biz_id = u.business_id

    # If business_id query parameter is provided directly
    if not biz_id and business_id:
        b_res = await db.execute(select(Business).where(Business.id == business_id))
        b = b_res.scalar_one_or_none()
        if b:
            biz_id = b.id

    # Seamless fallback for Power BI / Excel Web Connector or direct browser click
    if not biz_id:
        owner_res = await db.execute(select(User).where(User.role == "owner").limit(1))
        owner = owner_res.scalar_one_or_none()
        if owner and owner.business_id:
            biz_id = owner.business_id
        else:
            biz_res = await db.execute(select(Business).limit(1))
            first_biz = biz_res.scalar_one_or_none()
            if first_biz:
                biz_id = first_biz.id

    records = []
    if biz_id:
        query = (
            select(ChatMessage, ChatSession.customer_email, ChatSession.channel)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(ChatSession.business_id == biz_id)
            .order_by(ChatMessage.created_at)
        )
        records = (await db.execute(query)).all()

    if format == "json":
        data = []
        for msg, cust_email, channel in records:
            data.append({
                "SessionID": msg.session_id,
                "Timestamp": msg.created_at.isoformat(),
                "CustomerEmail": cust_email or "anonymous",
                "Channel": channel,
                "Sender": msg.sender,
                "MessageContent": msg.content,
                "IsAnswered": bool(msg.is_answered),
                "Topic": msg.topic or topic_analyzer.classify(msg.content),
                "Sentiment": msg.sentiment or sentiment_analyzer.analyze(msg.content, msg.feedback)[0],
                "Feedback": msg.feedback or "none",
                "LatencyMS": msg.latency_ms,
                "LLMProvider": msg.llm_provider_used,
                "CitationsCount": len(msg.source_citations),
                "ConfidenceScore": round(float(msg.confidence_score), 3)
            })
        return data

    # CSV Format for Power BI and Excel
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "SessionID", "Timestamp", "CustomerEmail", "Channel", "Sender",
        "MessageContent", "IsAnswered", "Topic", "Sentiment", "Feedback",
        "LatencyMS", "LLMProvider", "CitationsCount", "ConfidenceScore"
    ])

    for msg, cust_email, channel in records:
        writer.writerow([
            msg.session_id,
            msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            cust_email or "anonymous",
            channel,
            msg.sender,
            msg.content.replace("\n", " ").replace("\r", " "),
            "Yes" if msg.is_answered else "No",
            msg.topic or topic_analyzer.classify(msg.content),
            msg.sentiment or sentiment_analyzer.analyze(msg.content, msg.feedback)[0],
            msg.feedback or "none",
            msg.latency_ms,
            msg.llm_provider_used,
            len(msg.source_citations),
            round(float(msg.confidence_score), 3)
        ])

    csv_data = "\ufeff" + output.getvalue()
    filename = f"idevify_powerbi_dataset_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Dataset-Rows": str(len(records)),
            "X-Dataset-Schema-Version": "1.2"
        }
    )

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
        "fallback_message": fallback_msg,
        "custom_prompt": getattr(biz, "custom_prompt", "") if biz else ""
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

    # 3.5 Classify Intent via Laya System 1 Router
    laya_info = laya_service.classify_intent(query_text)
    laya_intent = laya_info.get("intent", "store_support") if isinstance(laya_info, dict) else "store_support"

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
        latency_ms=elapsed_ms,
        laya_intent=laya_intent
    )
