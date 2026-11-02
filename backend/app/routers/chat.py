import json
import asyncio
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from app.database import get_db
from app.models.business import Business
from app.models.chat import ChatSession, ChatMessage
from app.models.unanswered import UnansweredQuestion
from app.schemas.chat import (
    ChatSessionCreateRequest, ChatSessionResponse,
    ChatMessageRequest, ChatMessageResponse, SourceCitation,
    FeedbackRequest, LeadCaptureRequest
)
from app.services.rag_engine import rag_engine
from app.services.sentiment_analyzer import sentiment_analyzer
from app.services.topic_analyzer import topic_analyzer
from app.services.notification_service import notification_service
from app.schemas.ticket import ContactRequest

router = APIRouter(prefix="/api/chat", tags=["Customer Chat"])

@router.post("/session", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(req: ChatSessionCreateRequest, db: AsyncSession = Depends(get_db)):
    """Initializes a new customer chat session using the business slug or share token."""
    biz_query = select(Business).where(
        (Business.slug == req.business_slug_or_token) | (Business.share_token == req.business_slug_or_token)
    )
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business assistant not found."
        )

    session = ChatSession(
        business_id=business.id,
        channel=req.channel,
        customer_email=str(req.customer_email) if req.customer_email else None
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return ChatSessionResponse(
        id=session.id,
        business_id=business.id,
        business_name=business.name,
        business_slug=business.slug,
        channel=session.channel,
        started_at=session.created_at,
        last_message_at=session.last_message_at
    )

@router.post("/message", response_model=ChatMessageResponse)
async def send_chat_message(req: ChatMessageRequest, db: AsyncSession = Depends(get_db)):
    """Sends a question in an active chat session, runs Hybrid RAG, and saves the conversation."""
    # 1. Fetch Session & Business
    session_query = select(ChatSession).where(ChatSession.id == req.session_id)
    session = (await db.execute(session_query)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found.")

    biz_query = select(Business).where(Business.id == session.business_id)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")

    # 2. Analyze Sentiment & Topic
    sentiment_label, _ = sentiment_analyzer.analyze(req.message.strip())
    topic_category = topic_analyzer.classify(req.message.strip())

    # 3. Record Customer Message
    user_msg = ChatMessage(
        session_id=session.id,
        sender="customer",
        content=req.message.strip(),
        sentiment=sentiment_label,
        topic=topic_category,
        is_answered=True
    )
    db.add(user_msg)
    session.last_message_at = datetime.utcnow()
    session.sentiment = sentiment_label
    session.primary_topic = topic_category
    await db.flush()

    # 3. Retrieve Rolling History (last 4 message pairs)
    hist_query = select(ChatMessage).where(
        ChatMessage.session_id == session.id
    ).order_by(desc(ChatMessage.created_at)).limit(8)
    hist_results = (await db.execute(hist_query)).scalars().all()
    rolling_history = [
        {"role": m.sender, "content": m.content}
        for m in reversed(hist_results)
    ]

    # 4. Execute Multi-Hybrid RAG Pipeline
    biz_settings = {
        "name": business.name,
        "tone": business.tone,
        "fallback_message": business.fallback_message,
        "custom_prompt": getattr(business, "custom_prompt", "") or ""
    }
    rag_result = await rag_engine.query(
        business_id=business.id,
        user_query=req.message.strip(),
        business_settings=biz_settings,
        chat_history=rolling_history
    )

    # 5. Format Citations
    citation_objs = [
        SourceCitation(
            document_name=c.get("document_name", "Document"),
            page_number=c.get("page_number", 1),
            chunk_id=c.get("chunk_id", ""),
            excerpt=c.get("excerpt", "")
        )
        for c in rag_result.get("citations", [])
    ]

    # 6. Record Assistant Message
    assistant_msg = ChatMessage(
        session_id=session.id,
        sender="assistant",
        content=rag_result["answer"],
        sentiment=sentiment_label,
        topic=topic_category,
        is_answered=rag_result["is_answered"],
        confidence_score=rag_result["confidence_score"],
        latency_ms=rag_result["latency_ms"],
        llm_provider_used=rag_result["llm_provider"],
        source_citations=[c.model_dump() for c in citation_objs]
    )
    db.add(assistant_msg)
    await db.flush()

    # 7. If Unknown Question: Log to Unanswered Questions & Auto-Generate Support Ticket
    if not rag_result["is_answered"]:
        unanswered_entry = UnansweredQuestion(
            business_id=business.id,
            session_id=session.id,
            message_id=assistant_msg.id,
            question_text=req.message.strip(),
            customer_email=session.customer_email,
            top_retrieval_score=rag_result["confidence_score"]
        )
        db.add(unanswered_entry)

        # Auto-provision support ticket and trigger alerts
        await notification_service.create_ticket_and_notify(
            db=db,
            business=business,
            description=req.message.strip(),
            subject="Unanswered Customer Question",
            session_id=session.id,
            message_id=assistant_msg.id,
            customer_email=session.customer_email,
            channel=session.channel,
            priority="medium"
        )

    await db.commit()
    await db.refresh(assistant_msg)

    return ChatMessageResponse(
        id=assistant_msg.id,
        session_id=session.id,
        sender=assistant_msg.sender,
        content=assistant_msg.content,
        is_answered=assistant_msg.is_answered,
        feedback=assistant_msg.feedback,
        sentiment=assistant_msg.sentiment or "neutral",
        topic=assistant_msg.topic or "general",
        confidence_score=assistant_msg.confidence_score,
        latency_ms=assistant_msg.latency_ms,
        llm_provider_used=assistant_msg.llm_provider_used,
        citations=citation_objs,
        created_at=assistant_msg.created_at
    )

@router.get("/session/{session_id}/history", response_model=List[ChatMessageResponse])
async def get_session_history(session_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieves chronological conversation history for a chat session."""
    query = select(ChatMessage).where(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at)
    
    result = await db.execute(query)
    messages = result.scalars().all()

    return [
        ChatMessageResponse(
            id=m.id,
            session_id=m.session_id,
            sender=m.sender,
            content=m.content,
            is_answered=m.is_answered,
            feedback=m.feedback,
            sentiment=m.sentiment or "neutral",
            topic=m.topic or "general",
            confidence_score=m.confidence_score,
            latency_ms=m.latency_ms,
            llm_provider_used=m.llm_provider_used,
            citations=[SourceCitation(**c) for c in m.source_citations],
            created_at=m.created_at
        )
        for m in messages
    ]

@router.post("/message/{message_id}/feedback")
async def submit_message_feedback(
    message_id: str,
    req: FeedbackRequest,
    db: AsyncSession = Depends(get_db)
):
    """Submits thumbs up ('up') or thumbs down ('down') feedback on an assistant message."""
    query = select(ChatMessage).where(ChatMessage.id == message_id)
    msg = (await db.execute(query)).scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

    msg.feedback = req.feedback
    if req.feedback == "down":
        msg.sentiment = "negative"
        session_obj = (await db.execute(select(ChatSession).where(ChatSession.id == msg.session_id))).scalar_one_or_none()
        if session_obj:
            session_obj.sentiment = "negative"
    elif req.feedback == "up":
        msg.sentiment = "positive"
        session_obj = (await db.execute(select(ChatSession).where(ChatSession.id == msg.session_id))).scalar_one_or_none()
        if session_obj:
            session_obj.sentiment = "positive"
    await db.commit()
    return {"status": "success", "message_id": message_id, "feedback": req.feedback}

@router.post("/session/{session_id}/lead")
async def capture_customer_lead(
    session_id: str,
    req: LeadCaptureRequest,
    db: AsyncSession = Depends(get_db)
):
    """Captures customer email for human handoff when a question could not be answered."""
    session_query = select(ChatSession).where(ChatSession.id == session_id)
    session = (await db.execute(session_query)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    session.customer_email = str(req.email)

    # Attach email to recent unanswered questions in this session
    unans_query = select(UnansweredQuestion).where(
        UnansweredQuestion.session_id == session_id
    )
    unans_results = (await db.execute(unans_query)).scalars().all()
    for u in unans_results:
        u.customer_email = str(req.email)

    await db.commit()
    return {"status": "success", "message": "Email captured successfully. Our team will contact you."}

@router.get("/stream")
async def stream_chat_message(session_id: str, message: str, db: AsyncSession = Depends(get_db)):
    """Server-Sent Events (SSE) streaming endpoint returning answer tokens in real-time."""
    session_query = select(ChatSession).where(ChatSession.id == session_id)
    session = (await db.execute(session_query)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    biz_query = select(Business).where(Business.id == session.business_id)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found.")

    rag_result = await rag_engine.query(
        business_id=business.id,
        user_query=message,
        business_settings={
            "name": business.name,
            "tone": business.tone,
            "fallback_message": business.fallback_message,
            "custom_prompt": getattr(business, "custom_prompt", "") or ""
        }
    )

    full_text = rag_result["answer"]
    tokens = full_text.split(" ")

    async def event_generator():
        for token in tokens:
            yield f"data: {json.dumps({'token': token + ' '})}\n\n"
            await asyncio.sleep(0.04)
        
        # Final metadata event
        yield f"data: {json.dumps({'done': True, 'citations': rag_result['citations'], 'is_answered': rag_result['is_answered']})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/contact-request", status_code=status.HTTP_201_CREATED)
async def submit_contact_request(req: ContactRequest, db: AsyncSession = Depends(get_db)):
    """Receives a customer human callback or contact request and dispatches urgent alerts."""
    session_query = select(ChatSession).where(ChatSession.id == req.session_id)
    session = (await db.execute(session_query)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found.")

    biz_query = select(Business).where(Business.id == session.business_id)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")

    contact = req.customer_contact.strip()
    c_email = contact if "@" in contact else None
    c_phone = contact if "@" not in contact else None
    if c_email and not session.customer_email:
        session.customer_email = c_email

    ticket = await notification_service.create_ticket_and_notify(
        db=db,
        business=business,
        description=req.message.strip(),
        subject="Urgent Contact Request / Callback",
        session_id=session.id,
        customer_name=req.customer_name,
        customer_email=c_email,
        customer_phone=c_phone,
        channel=session.channel or req.channel,
        priority="urgent"
    )

    await db.commit()
    return {
        "status": "success",
        "ticket_number": ticket.ticket_number,
        "message": "Thank you! Our support team has been notified and will contact you promptly."
    }


