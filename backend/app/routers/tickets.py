import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger("idevify-tickets-router")
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from app.database import get_db
from app.models.user import User
from app.models.ticket import Ticket
from app.models.notification import Notification
from app.models.document import Document, DocumentChunk
from app.utils.security import get_current_owner
from app.schemas.ticket import TicketResponse, TicketResolveRequest
from app.services.vector_store import vector_store_service
from app.services.bm25_store import bm25_store_service

router = APIRouter(prefix="/api/tickets", tags=["Support Tickets"])

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
    doc_title = f"Resolved Ticket: {ticket.ticket_number}"
    doc = Document(
        business_id=biz_id,
        file_name=f"resolved_{ticket.ticket_number.lower()}.txt",
        file_type="manual_qa",
        file_size_bytes=len(req.resolved_answer),
        status="INDEXED",
        total_pages=1,
        processed_pages=1,
        processing_progress=100
    )
    db.add(doc)
    await db.flush()

    chunk_content = f"Question: {ticket.description}\nVerified Answer: {req.resolved_answer.strip()}"
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
        "ticket_number": ticket.ticket_number
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
            "ticket_number": ticket.ticket_number
        }
    }
    await vector_store_service.add_chunks(biz_id, [chunk_item])
    bm25_store_service.add_chunks(biz_id, [chunk_item])

    # 4. Create In-App Notification for Resolution
    notif = Notification(
        business_id=biz_id,
        ticket_id=ticket.id,
        type="ticket_resolved",
        title=f"Ticket #{ticket.ticket_number} Resolved",
        message=f"Answer indexed into AI knowledge base: '{req.resolved_answer[:80]}...'",
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

    # 5. Outbound WhatsApp Notification to Customer (if contact phone exists and WhatsApp is enabled)
    biz_record = (await db.execute(select(Business).where(Business.id == biz_id))).scalar_one_or_none()
    is_whatsapp_enabled = getattr(biz_record, "enable_whatsapp", True) is not False if biz_record else True

    target_phone = ticket.customer_phone or (ticket.customer_email if ticket.channel == "whatsapp" else None)
    if target_phone and is_whatsapp_enabled:
        try:
            from app.services.twilio_service import twilio_service
            await twilio_service.notify_customer_ticket_resolved(
                customer_phone=target_phone,
                ticket_number=ticket.ticket_number,
                question=ticket.description or ticket.subject or "Inquiry",
                resolved_answer=req.resolved_answer
            )
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
