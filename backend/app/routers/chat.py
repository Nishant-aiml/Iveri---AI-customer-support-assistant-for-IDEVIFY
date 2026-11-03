import logging
logger = logging.getLogger("idevify-chat")
import json
import asyncio
from datetime import datetime
import os
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse, FileResponse
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
    try:
        # 1. High-Performance Joined Session & Business Fetch (Single DB Round-Trip)
        sess_biz_query = (
            select(ChatSession, Business)
            .join(Business, Business.id == ChatSession.business_id)
            .where(ChatSession.id == req.session_id)
        )
        row = (await db.execute(sess_biz_query)).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session or business not found.")
        session, business = row

        # 2. Retrieve Rolling History (prior message pairs)
        hist_query = select(ChatMessage).where(
            ChatMessage.session_id == session.id
        ).order_by(desc(ChatMessage.created_at)).limit(8)
        hist_results = (await db.execute(hist_query)).scalars().all()
        rolling_history = [
            {"role": m.sender, "content": m.content}
            for m in reversed(hist_results)
        ]

        # 3. Analyze Sentiment & Topic
        sentiment_label, _ = sentiment_analyzer.analyze(req.message.strip())
        topic_category = topic_analyzer.classify(req.message.strip())

        # 4. Record Customer Message
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

        # 5. Execute Multi-Hybrid RAG Pipeline
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

        # 6. Format Citations
        citation_objs = [
            SourceCitation(
                document_name=c.get("document_name", "Document"),
                page_number=c.get("page_number", 1),
                chunk_id=c.get("chunk_id", ""),
                excerpt=c.get("excerpt", ""),
                document_id=c.get("document_id"),
                highlight_terms=c.get("highlight_terms", []),
                has_pdf_preview=c.get("has_pdf_preview", True)
            )
            for c in rag_result.get("citations", [])
        ]

        # 7. Record Assistant Message
        from app.models.base import generate_uuid
        asst_msg_id = generate_uuid()
        assistant_msg = ChatMessage(
            id=asst_msg_id,
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

        # Explicit flush guarantees user_msg and assistant_msg exist before any child references
        try:
            await db.flush()
        except Exception as flush_err:
            logger.warning(f"Preliminary chat messages flush warning: {flush_err}")

        # 8. If Unknown Question: Log to Unanswered Questions & Auto-Generate Support Ticket
        if not rag_result["is_answered"]:
            try:
                unanswered_entry = UnansweredQuestion(
                    business_id=business.id,
                    session_id=session.id,
                    message_id=asst_msg_id,
                    question_text=req.message.strip(),
                    customer_email=session.customer_email,
                    top_retrieval_score=rag_result["confidence_score"]
                )
                db.add(unanswered_entry)
                await db.flush()
            except Exception as unans_err:
                logger.warning(f"Unanswered question logging notice: {unans_err}")

            # Auto-provision support ticket and trigger alerts (non-fatal shield)
            try:
                await notification_service.create_ticket_and_notify(
                    db=db,
                    business=business,
                    description=req.message.strip(),
                    subject="Unanswered Customer Question",
                    session_id=session.id,
                    message_id=asst_msg_id,
                    customer_email=session.customer_email,
                    channel=session.channel,
                    priority="medium"
                )
            except Exception as ticket_err:
                logger.warning(f"Ticket auto-provision notice: {ticket_err}")

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
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Critical error in send_chat_message: {exc}", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        from app.models.base import generate_uuid
        fallback_msg = (
            "I'm sorry, but I do not have this information in my documents. "
            "I have logged your question for our support team, and an agent will follow up shortly."
        )
        return ChatMessageResponse(
            id=generate_uuid(),
            session_id=req.session_id,
            sender="assistant",
            content=fallback_msg,
            is_answered=False,
            feedback=None,
            sentiment="neutral",
            topic="general",
            confidence_score=0.0,
            latency_ms=100,
            llm_provider_used="system",
            citations=[],
            created_at=datetime.utcnow()
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
            citations=[
                SourceCitation(
                    document_name=c.get("document_name", "Document"),
                    page_number=c.get("page_number", 1),
                    chunk_id=c.get("chunk_id", ""),
                    excerpt=c.get("excerpt", ""),
                    document_id=c.get("document_id"),
                    highlight_terms=c.get("highlight_terms", []),
                    has_pdf_preview=c.get("has_pdf_preview", True)
                )
                for c in (m.source_citations or [])
            ],
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

    # Attach email to any open tickets for this session
    from app.models.ticket import Ticket
    ticket_query = select(Ticket).where(
        Ticket.session_id == session_id,
        Ticket.status != "resolved"
    )
    open_tickets = (await db.execute(ticket_query)).scalars().all()
    for t in open_tickets:
        t.customer_email = str(req.email)

    await db.commit()

    # Dispatches immediate customer confirmation email acknowledging the inquiry
    biz_query = select(Business).where(Business.id == session.business_id)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if business:
        ticket_num = open_tickets[0].ticket_number if open_tickets else "PENDING"
        last_question = unans_results[-1].question_text if unans_results else None
        try:
            from app.services.email_service import email_service
            await email_service.send_customer_ticket_acknowledgment(
                to_email=str(req.email),
                business_name=business.name,
                ticket_number=ticket_num,
                question_text=last_question
            )
        except Exception as e:
            logger.warning(f"Customer email lead acknowledgment notice: {e}")

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
    session = None
    business = None

    if req.session_id:
        session_biz_query = (
            select(ChatSession, Business)
            .join(Business, Business.id == ChatSession.business_id)
            .where(ChatSession.id == req.session_id)
        )
        row = (await db.execute(session_biz_query)).first()
        if row:
            session, business = row

    if not business and req.business_slug:
        biz_query = select(Business).where(
            (Business.slug == req.business_slug) | (Business.share_token == req.business_slug)
        )
        business = (await db.execute(biz_query)).scalar_one_or_none()
        if business:
            session = ChatSession(
                business_id=business.id,
                channel=req.channel,
                customer_email=req.customer_contact if "@" in req.customer_contact else None
            )
            db.add(session)
            await db.flush()

    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session or business not found.")

    contact = req.customer_contact.strip()
    c_email = contact if "@" in contact else None
    c_phone = contact if "@" not in contact else None
    if session and c_email and not session.customer_email:
        session.customer_email = c_email

    ticket = await notification_service.create_ticket_and_notify(
        db=db,
        business=business,
        description=req.message.strip(),
        subject="Urgent Contact Request / Callback",
        session_id=session.id if session else None,
        customer_name=req.customer_name,
        customer_email=c_email,
        customer_phone=c_phone,
        channel=(session.channel if session else None) or req.channel,
        priority="urgent"
    )

    await db.commit()
    return {
        "status": "success",
        "ticket_number": ticket.ticket_number,
        "message": "Thank you! Our support team has been notified and will contact you promptly."
    }

@router.get("/citation/{chunk_id}/page-preview")
async def get_citation_page_preview(
    chunk_id: str,
    query: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Renders the cited document page as a high-DPI image with source highlights directly on the PDF."""
    from app.models.document import DocumentChunk, Document
    query_stmt = (
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.id == chunk_id)
    )
    res = (await db.execute(query_stmt)).first()
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Citation chunk not found.")
    chunk, doc = res

    if not doc.storage_path or not os.path.exists(doc.storage_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found on disk.")

    ext = os.path.splitext(doc.file_name)[1].lower()
    if ext != ".pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Page highlight view only available for PDF documents.")

    import pymupdf
    try:
        pdf_doc = pymupdf.open(doc.storage_path)
        page_idx = max(0, min(chunk.page_number - 1, len(pdf_doc) - 1))
        page = pdf_doc[page_idx]

        # Gather highlight phrases
        terms_to_highlight = set()
        if query:
            stop_words = {"what", "is", "are", "how", "much", "many", "the", "for", "with", "from", "tell", "about", "your", "our", "do", "does", "can", "you", "this", "that"}
            q_words = [w for w in re.findall(r"\b[a-zA-Z0-9_\-]+\b", query) if w.lower() not in stop_words and len(w) >= 3]
            terms_to_highlight.update(q_words)

        # Extract sentences from chunk content that match query
        chunk_lines = [l.strip() for l in chunk.content.split("\n") if len(l.strip()) > 6]
        for line in chunk_lines:
            if any(t.lower() in line.lower() for t in terms_to_highlight):
                clean_line = line.strip(" -•*#").strip()
                if 8 <= len(clean_line) <= 100:
                    terms_to_highlight.add(clean_line)

        # Add yellow highlight annotations on PDF
        for term in terms_to_highlight:
            rects = page.search_for(term)
            for r in rects:
                annot = page.add_highlight_annot(r)
                annot.set_colors(stroke=(1.0, 0.9, 0.1))
                annot.update()

        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        pdf_doc.close()

        return Response(
            content=img_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Document-Name": doc.file_name,
                "X-Page-Number": str(chunk.page_number)
            }
        )
    except Exception as e:
        logger.error(f"Error rendering PDF page highlight: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not render PDF preview.")

@router.get("/document/{document_id}/file")
async def view_public_document_file(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Allows customers/visitors to view the verified grounding source PDF inline in browser."""
    from app.models.document import Document
    doc_query = select(Document).where(Document.id == document_id)
    doc = (await db.execute(doc_query)).scalar_one_or_none()
    if not doc or not doc.storage_path or not os.path.exists(doc.storage_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found.")

    ext = os.path.splitext(doc.file_name)[1].lower()
    media_type = "application/pdf" if ext == ".pdf" else "application/octet-stream"
    return FileResponse(
        path=doc.storage_path,
        media_type=media_type,
        filename=doc.file_name,
        content_disposition_type="inline"
    )

