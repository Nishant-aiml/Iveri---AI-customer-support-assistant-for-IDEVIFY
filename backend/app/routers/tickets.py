import logging
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote

logger = logging.getLogger("idevify-tickets-router")
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, delete
from app.database import get_db
from app.models.user import User
from app.models.business import Business
from app.models.ticket import Ticket
from app.models.chat import ChatSession, ChatMessage
from app.models.notification import Notification
from app.models.document import Document, DocumentChunk
from app.utils.security import get_current_owner
from app.schemas.ticket import (
    TicketResponse,
    TicketResolveRequest,
    TicketConversationResponse,
    UnansweredConversationMessage
)
from app.services.vector_store import vector_store_service
from app.services.bm25_store import bm25_store_service

router = APIRouter(prefix="/api/tickets", tags=["Support Tickets"])

@router.get("/summary/stats")
async def get_ticket_stats(
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves authoritative ticket summary counts for the business owner cards."""
    biz_id = owner.business_id
    from sqlalchemy import func

    total = (await db.execute(select(func.count(Ticket.id)).where(Ticket.business_id == biz_id))).scalar() or 0
    open_count = (await db.execute(select(func.count(Ticket.id)).where(Ticket.business_id == biz_id, Ticket.status == "open"))).scalar() or 0
    urgent_count = (await db.execute(select(func.count(Ticket.id)).where(Ticket.business_id == biz_id, Ticket.priority == "urgent", Ticket.status != "resolved"))).scalar() or 0
    wa_count = (await db.execute(select(func.count(Ticket.id)).where(Ticket.business_id == biz_id, Ticket.channel == "whatsapp"))).scalar() or 0
    resolved_count = (await db.execute(select(func.count(Ticket.id)).where(Ticket.business_id == biz_id, Ticket.status == "resolved"))).scalar() or 0

    return {
        "total": total,
        "open": open_count,
        "urgent": urgent_count,
        "whatsapp": wa_count,
        "resolved": resolved_count
    }

@router.get("", response_model=List[TicketResponse])
async def list_tickets(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: 'open', 'in_progress', 'resolved'"),
    priority: Optional[str] = Query(None, description="Filter by priority: 'urgent', 'high', 'medium', 'low'"),
    channel: Optional[str] = Query(None, description="Filter by channel: 'widget', 'whatsapp', 'public_link'"),
    search: Optional[str] = Query(None, description="Search by customer name, email, phone or ticket number"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves support tickets for the authenticated business with multi-parameter filtering."""
    query = select(Ticket).where(Ticket.business_id == owner.business_id)

    if status_filter:
        query = query.where(Ticket.status == status_filter)
    if priority:
        query = query.where(Ticket.priority == priority)
    if channel:
        query = query.where(Ticket.channel == channel)
    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.where(
            (Ticket.id.ilike(search_pattern)) |
            (Ticket.ticket_number.ilike(search_pattern)) |
            (Ticket.customer_name.ilike(search_pattern)) |
            (Ticket.customer_email.ilike(search_pattern)) |
            (Ticket.customer_phone.ilike(search_pattern)) |
            (Ticket.description.ilike(search_pattern))
        )

    query = query.order_by(desc(Ticket.created_at)).offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: str,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves a single ticket by its UUID or ticket number."""
    query = select(Ticket).where(
        Ticket.business_id == owner.business_id,
        (Ticket.id == ticket_id) | (Ticket.ticket_number == ticket_id)
    )
    ticket = (await db.execute(query)).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
    return ticket


@router.get("/{ticket_id}/conversation", response_model=TicketConversationResponse)
async def get_ticket_conversation(
    ticket_id: str,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieves the specific chat conversation history associated with an unanswered ticket.
    Identifies and flags the exact customer question / unanswered inquiry that triggered the ticket
    so it can be highlighted in the UI.
    """
    biz_id = owner.business_id
    query = select(Ticket).where(
        Ticket.business_id == biz_id,
        (Ticket.id == ticket_id) | (Ticket.ticket_number == ticket_id)
    )
    ticket = (await db.execute(query)).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    messages: list[UnansweredConversationMessage] = []
    has_chat_session = bool(ticket.session_id)

    if ticket.session_id:
        sess_query = select(ChatSession).where(
            ChatSession.id == ticket.session_id,
            ChatSession.business_id == biz_id
        )
        session = (await db.execute(sess_query)).scalar_one_or_none()

        if session:
            msg_query = (
                select(ChatMessage)
                .where(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at)
            )
            raw_msgs = (await db.execute(msg_query)).scalars().all()

            unanswered_text_clean = (ticket.description or "").strip().lower()
            target_idx = -1

            # 1. Match by content against customer messages
            if unanswered_text_clean:
                for idx, m in enumerate(raw_msgs):
                    if m.sender == "customer" and unanswered_text_clean in m.content.strip().lower():
                        target_idx = idx

            # 2. Match by ticket.message_id
            if target_idx == -1 and ticket.message_id:
                for idx, m in enumerate(raw_msgs):
                    if m.id == ticket.message_id:
                        if m.sender == "assistant" and idx > 0 and raw_msgs[idx - 1].sender == "customer":
                            target_idx = idx - 1
                        else:
                            target_idx = idx
                        break

            # 3. Fallback to last customer message
            if target_idx == -1:
                for idx in range(len(raw_msgs) - 1, -1, -1):
                    if raw_msgs[idx].sender == "customer":
                        target_idx = idx
                        break

            for idx, m in enumerate(raw_msgs):
                is_target = (idx == target_idx)
                messages.append(
                    UnansweredConversationMessage(
                        id=m.id,
                        sender=m.sender,
                        content=m.content,
                        is_answered=m.is_answered if m.is_answered is not None else True,
                        is_unanswered_target=is_target,
                        created_at=m.created_at,
                        sentiment=m.sentiment or "neutral",
                        feedback=m.feedback
                    )
                )

    return TicketConversationResponse(
        ticket_id=ticket.id,
        ticket_number=ticket.ticket_number,
        session_id=ticket.session_id,
        channel=ticket.channel,
        customer_name=ticket.customer_name,
        customer_email=ticket.customer_email,
        customer_phone=ticket.customer_phone,
        unanswered_question=ticket.description or ticket.subject,
        status=ticket.status,
        priority=ticket.priority,
        messages=messages,
        has_chat_session=has_chat_session and len(messages) > 0
    )



@router.post("/{ticket_id}/draft-reply")
async def generate_draft_reply(
    ticket_id: str,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """
    Generates an AI-drafted reply based on the ticket inquiry, customer details, and business knowledge base.
    Returns the drafted text along with pre-built direct WhatsApp, Phone dialer, Gmail web, and mailto URLs.
    """
    biz_id = owner.business_id
    query = select(Ticket).where(
        Ticket.business_id == biz_id,
        (Ticket.id == ticket_id) | (Ticket.ticket_number == ticket_id)
    )
    ticket = (await db.execute(query)).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    biz_record = (await db.execute(select(Business).where(Business.id == biz_id))).scalar_one_or_none()
    biz_name = biz_record.name if biz_record else "Customer Support"
    cust_name = ticket.customer_name or "there"
    inquiry = ticket.description or ticket.subject or "your inquiry"

    # 1. Ask RAG Engine if knowledge base has relevant facts
    rag_ans = None
    try:
        from app.services.rag_engine import rag_engine
        rag_result = await rag_engine.query(business_id=biz_id, query=inquiry, chat_history=[])
        if rag_result and rag_result.get("is_answered"):
            rag_ans = rag_result.get("answer")
    except Exception as e:
        logger.warning(f"RAG draft query note: {e}")

    # 2. Formulate customized draft
    if "callback" in inquiry.lower() or "call me" in inquiry.lower():
        draft = (
            f"Hi {cust_name}, thank you for contacting {biz_name}! Regarding your request ('{inquiry}'), "
            f"our team is ready to connect with you. Please let us know if now is a good time to speak, "
            f"or what time works best for you. Best regards, {biz_name} Team."
        )
    elif rag_ans:
        draft = (
            f"Hi {cust_name}, thank you for reaching out to {biz_name}! Here is the information regarding your inquiry: "
            f"{rag_ans} "
            f"Please let us know if you have any questions! Best regards, {biz_name} Team."
        )
    else:
        draft = (
            f"Hi {cust_name}, thank you for reaching out to {biz_name} regarding '{inquiry}'. "
            f"Our team has received your inquiry and we are here to help. "
            f"How can we assist you today? Best regards, {biz_name} Team."
        )

    # 3. Build Deep Links for WhatsApp, Phone Dialer, and Gmail Web
    phone = ticket.customer_phone or (ticket.customer_email if ticket.channel == "whatsapp" else "")
    clean_phone = "".join(filter(str.isdigit, phone)) if phone else ""
    email = ticket.customer_email if (ticket.customer_email and "@" in ticket.customer_email) else ""
    subject = f"Re: Your inquiry ({ticket.ticket_number}) - {biz_name}"

    whatsapp_url = f"https://wa.me/{clean_phone}?text={quote(draft)}" if clean_phone else ""
    tel_url = f"tel:{phone}" if phone else ""
    gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={quote(email)}&su={quote(subject)}&body={quote(draft)}" if email else ""
    mailto_url = f"mailto:{email}?subject={quote(subject)}&body={quote(draft)}" if email else ""

    return {
        "ticket_number": ticket.ticket_number,
        "customer_name": ticket.customer_name,
        "customer_phone": phone,
        "customer_email": email,
        "draft": draft,
        "whatsapp_url": whatsapp_url,
        "tel_url": tel_url,
        "gmail_url": gmail_url,
        "mailto_url": mailto_url
    }

@router.post("/{ticket_id}/resolve", response_model=TicketResponse)
async def resolve_ticket(
    ticket_id: str,
    req: TicketResolveRequest,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """
    Resolves a ticket with the business owner's verified answer.
    Permanently auto-indexes the Q&A into ChromaDB & BM25 so the AI assistant learns it immediately.
    """
    biz_id = owner.business_id
    query = select(Ticket).where(
        Ticket.business_id == biz_id,
        (Ticket.id == ticket_id) | (Ticket.ticket_number == ticket_id)
    )
    ticket = (await db.execute(query)).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    # 1. Update Ticket
    ticket.status = "resolved"
    ticket.resolved_answer = req.resolved_answer.strip()
    ticket.resolved_at = datetime.utcnow()

    # 2. Permanent Knowledge Base Indexing (Closed-Loop Learning)
    # Strictly opt-in for authenticated business owners to prevent conversational pollution
    if req.train_ai:
        knowledge_to_learn = (req.verified_knowledge_fact or req.resolved_answer).strip()
        doc_title = f"Verified Rule: {ticket.ticket_number}"
        doc = Document(
            business_id=biz_id,
            file_name=f"verified_{ticket.ticket_number.lower()}.txt",
            file_type="manual_qa",
            file_size_bytes=len(knowledge_to_learn),
            status="INDEXED",
            total_pages=1,
            processed_pages=1,
            processing_progress=100
        )
        db.add(doc)
        await db.flush()

        chunk_content = f"Question: {ticket.description}\nVerified Answer: {knowledge_to_learn}"
        chunk = DocumentChunk(
            document_id=doc.id,
            business_id=biz_id,
            chunk_index=0,
            page_number=1,
            content=chunk_content
        )
        chunk.payload = {
            "document_name": doc_title,
            "source_type": "resolved_ticket",
            "ticket_number": ticket.ticket_number,
            "verified_by": owner.email
        }
        db.add(chunk)
        await db.flush()

        # 3. Add to ChromaDB and BM25 index
        chunk_item = {
            "id": chunk.id,
            "content": chunk_content,
            "metadata": {
                "document_name": doc_title,
                "page_number": 1,
                "document_id": doc.id,
                "source_type": "resolved_ticket",
                "ticket_number": ticket.ticket_number,
                "verified_by": owner.email
            }
        }
        await vector_store_service.add_chunks(biz_id, [chunk_item])
        bm25_store_service.add_chunks(biz_id, [chunk_item])

    # 4. Create In-App Notification for Resolution
    notif_msg = (
        f"Verified fact indexed into AI knowledge base: '{req.resolved_answer[:60]}...'"
        if req.train_ai
        else "Ticket resolved and sent to customer."
    )
    notif = Notification(
        business_id=biz_id,
        ticket_id=ticket.id,
        type="ticket_resolved",
        title=f"Ticket #{ticket.ticket_number} Resolved",
        message=notif_msg,
        link_url="/dashboard#tickets",
        is_read=False
    )
    db.add(notif)

    # 4b. Synchronize with any corresponding UnansweredQuestion
    try:
        from app.models.unanswered import UnansweredQuestion
        unans_q = select(UnansweredQuestion).where(
            UnansweredQuestion.business_id == biz_id,
            (
                (UnansweredQuestion.question_text == ticket.description) |
                (UnansweredQuestion.session_id == ticket.session_id)
            )
        )
        unans_records = (await db.execute(unans_q)).scalars().all()
        for u in unans_records:
            u.is_resolved = True
            u.resolved_answer = req.resolved_answer.strip()
            u.resolved_at = datetime.utcnow()
    except Exception as e:
        logger.warning(f"Note syncing UnansweredQuestion: {e}")

    # 4c. Append resolution message to customer's chat session if linked
    if ticket.session_id:
        try:
            from app.models.chat import ChatMessage
            chat_msg = ChatMessage(
                session_id=ticket.session_id,
                sender="assistant",
                content=f"✅ Support Update regarding Ticket #{ticket.ticket_number}:\n\n{req.resolved_answer}",
                is_answered=True,
                confidence_score=1.0,
                llm_provider_used="human_verified"
            )
            db.add(chat_msg)
        except Exception as e:
            logger.warning(f"Note appending resolution to session {ticket.session_id}: {e}")

    # 5. Outbound WhatsApp Notification to Customer (if contact phone exists and WhatsApp is enabled)
    biz_record = (await db.execute(select(Business).where(Business.id == biz_id))).scalar_one_or_none()
    is_whatsapp_enabled = getattr(biz_record, "enable_whatsapp", True) is not False if biz_record else True

    target_phone = ticket.customer_phone or (ticket.customer_email if ticket.channel == "whatsapp" else None)
    if target_phone and is_whatsapp_enabled:
        try:
            from app.services.twilio_service import twilio_service, normalize_phone_number
            norm_phone = normalize_phone_number(target_phone)
            res_wa = await twilio_service.notify_customer_ticket_resolved(
                customer_phone=norm_phone,
                ticket_number=ticket.ticket_number,
                question=ticket.description or ticket.subject or "Inquiry",
                resolved_answer=req.resolved_answer
            )
            logger.info(f"Outbound customer WhatsApp resolution result: {res_wa}")
        except Exception as e:
            logger.warning(f"Twilio WhatsApp customer resolution notification note: {e}")

    # 5b. Outbound Email Notification to Customer (if customer_email exists)
    if ticket.customer_email and "@" in ticket.customer_email:
        try:
            from app.services.email_service import email_service
            await email_service.send_customer_ticket_resolved(
                to_email=ticket.customer_email,
                business_name=biz_record.name if biz_record else "Iveri Support",
                ticket_number=ticket.ticket_number,
                question_text=ticket.description or ticket.subject or "Inquiry",
                resolved_answer=req.resolved_answer,
                customer_name=ticket.customer_name
            )
        except Exception as e:
            logger.warning(f"Customer email resolution notification note: {e}")

    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/{ticket_id}/notify-customer")
async def notify_customer_ticket(
    ticket_id: str,
    channel_type: Optional[str] = Query(None, description="'whatsapp', 'email', or 'all'"),
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """
    Explicitly re-sends or dispatches the ticket resolution answer to the customer's phone (WhatsApp) and/or email.
    Works for open or resolved tickets.
    """
    biz_id = owner.business_id
    query = select(Ticket).where(
        Ticket.business_id == biz_id,
        (Ticket.id == ticket_id) | (Ticket.ticket_number == ticket_id)
    )
    ticket = (await db.execute(query)).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    answer = ticket.resolved_answer or ticket.description
    if not answer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No answer or message available to send.")

    results = {}
    biz_record = (await db.execute(select(Business).where(Business.id == biz_id))).scalar_one_or_none()

    # WhatsApp
    target_phone = ticket.customer_phone or (ticket.customer_email if ticket.channel == "whatsapp" else None)
    if target_phone and channel_type in (None, "whatsapp", "all"):
        from app.services.twilio_service import twilio_service, normalize_phone_number
        norm_phone = normalize_phone_number(target_phone)
        wa_res = await twilio_service.notify_customer_ticket_resolved(
            customer_phone=norm_phone,
            ticket_number=ticket.ticket_number,
            question=ticket.description or ticket.subject or "Inquiry",
            resolved_answer=answer
        )
        results["whatsapp"] = wa_res

    # Email
    if ticket.customer_email and "@" in ticket.customer_email and channel_type in (None, "email", "all"):
        from app.services.email_service import email_service
        em_res = await email_service.send_customer_ticket_resolved(
            to_email=ticket.customer_email,
            business_name=biz_record.name if biz_record else "Iveri Support",
            ticket_number=ticket.ticket_number,
            question_text=ticket.description or ticket.subject or "Inquiry",
            resolved_answer=answer,
            customer_name=ticket.customer_name
        )
        results["email"] = em_res

    return {"status": "dispatched", "ticket_number": ticket.ticket_number, "results": results}

@router.delete("/{ticket_id}", status_code=status.HTTP_200_OK)
async def delete_ticket(
    ticket_id: str,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Permanently deletes a support ticket for the authenticated business owner."""
    biz_id = owner.business_id
    query = select(Ticket).where(
        Ticket.business_id == biz_id,
        (Ticket.id == ticket_id) | (Ticket.ticket_number == ticket_id)
    )
    ticket = (await db.execute(query)).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    await db.execute(
        delete(Notification).where(
            Notification.business_id == biz_id,
            Notification.ticket_id == ticket.id
        )
    )
    await db.delete(ticket)
    await db.commit()
    return {"status": "success", "message": f"Ticket #{ticket.ticket_number} deleted successfully."}
