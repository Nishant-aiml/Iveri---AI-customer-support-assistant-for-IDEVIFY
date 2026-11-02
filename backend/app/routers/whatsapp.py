import os
import logging
from typing import Dict, Any
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db
from app.models.business import Business
from app.models.chat import ChatSession, ChatMessage
from app.services.rag_engine import rag_engine
from app.services.notification_service import notification_service
from app.services.sentiment_analyzer import sentiment_analyzer
from app.services.topic_analyzer import topic_analyzer

logger = logging.getLogger("idevify-whatsapp")
router = APIRouter(prefix="/api/chat/whatsapp", tags=["WhatsApp Omnichannel Interface"])

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "idevify_whatsapp_verify_token_2026")

@router.get("/{business_slug}/webhook")
async def verify_whatsapp_webhook(
    business_slug: str,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    db: AsyncSession = Depends(get_db)
):
    """
    Meta WhatsApp Cloud API Webhook Verification Challenge.
    Meta sends a GET request to verify endpoint authenticity.
    """
    # 1. Verify business exists
    biz_query = select(Business).where(Business.slug == business_slug)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")

    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info(f"WhatsApp webhook successfully verified for business: {business_slug}")
        return Response(content=hub_challenge, media_type="text/plain")

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch.")

@router.post("/{business_slug}/webhook")
async def receive_whatsapp_message(
    business_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Receives inbound customer messages from WhatsApp, runs Hybrid RAG + Guardrails,
    records chat into database with channel='whatsapp', and triggers tickets on fallback.
    """
    payload = await request.json()
    logger.info(f"Inbound WhatsApp payload received for {business_slug}")

    # 1. Find business
    biz_query = select(Business).where(Business.slug == business_slug)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")

    # 2. Extract Message details from Meta WhatsApp Cloud API format or Twilio format
    sender_phone = None
    customer_name = "WhatsApp User"
    message_text = ""

    # Meta Cloud API format
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]["value"]
        messages = change.get("messages", [])
        if messages:
            msg = messages[0]
            sender_phone = msg.get("from")
            if msg.get("type") == "text":
                message_text = msg.get("text", {}).get("body", "")
            contacts = change.get("contacts", [])
            if contacts:
                customer_name = contacts[0].get("profile", {}).get("name", customer_name)
    except Exception:
        # Fallback to direct JSON format for testing
        sender_phone = payload.get("from") or payload.get("sender_phone")
        message_text = payload.get("message") or payload.get("text") or payload.get("body", "")
        customer_name = payload.get("name") or customer_name

    if not sender_phone or not message_text.strip():
        return {"status": "ignored", "reason": "No actionable text message found"}

    clean_query = message_text.strip()

    # 3. Find or Create WhatsApp Chat Session
    sess_query = select(ChatSession).where(
        ChatSession.business_id == business.id,
        ChatSession.channel == "whatsapp",
        ChatSession.customer_email == sender_phone
    ).order_by(ChatSession.created_at.desc()).limit(1)
    session = (await db.execute(sess_query)).scalar_one_or_none()

    if not session:
        session = ChatSession(
            business_id=business.id,
            channel="whatsapp",
            customer_email=sender_phone,
            sentiment="neutral",
            primary_topic="general"
        )
        db.add(session)
        await db.flush()

    # 4. Sentiment & Topic Analysis
    sentiment_label, _ = sentiment_analyzer.analyze(clean_query)
    topic_category = topic_analyzer.classify(clean_query)

    # 5. Record Customer Message
    user_msg = ChatMessage(
        session_id=session.id,
        sender="customer",
        content=clean_query,
        sentiment=sentiment_label,
        topic=topic_category,
        is_answered=True
    )
    db.add(user_msg)
    session.sentiment = sentiment_label
    session.primary_topic = topic_category
    await db.flush()

    # 6. Execute Hybrid RAG Pipeline
    biz_settings = {
        "name": business.name,
        "tone": business.tone,
        "fallback_message": business.fallback_message,
        "custom_prompt": getattr(business, "custom_prompt", "") or ""
    }
    rag_result = await rag_engine.query(
        business_id=business.id,
        user_query=clean_query,
        business_settings=biz_settings
    )

    # 7. Record Assistant Message
    assistant_msg = ChatMessage(
        session_id=session.id,
        sender="assistant",
        content=rag_result["answer"],
        sentiment=sentiment_label,
        topic=topic_category,
        is_answered=rag_result["is_answered"],
        confidence_score=rag_result["confidence_score"],
        latency_ms=rag_result["latency_ms"],
        llm_provider_used=rag_result["llm_provider"]
    )
    db.add(assistant_msg)
    await db.flush()

    # 8. If Unanswered / Fallback: Auto-Generate Ticket & Send Email Alert to Owner!
    ticket_id = None
    if not rag_result["is_answered"]:
        ticket = await notification_service.create_ticket_and_notify(
            db=db,
            business=business,
            description=clean_query,
            subject="Unanswered WhatsApp Question",
            session_id=session.id,
            message_id=assistant_msg.id,
            customer_name=customer_name,
            customer_phone=sender_phone,
            channel="whatsapp",
            priority="high"
        )
        ticket_id = ticket.ticket_number

    await db.commit()

    return {
        "status": "success",
        "channel": "whatsapp",
        "sender": sender_phone,
        "customer_name": customer_name,
        "answer": rag_result["answer"],
        "is_answered": rag_result["is_answered"],
        "ticket_created": ticket_id
    }

@router.get("/{business_slug}/config", response_model=Dict[str, Any])
async def get_whatsapp_config(
    business_slug: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns Click-to-Chat URL, QR payload, and webhook credentials for business WhatsApp deployment.
    """
    biz_query = select(Business).where(Business.slug == business_slug)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")

    phone = getattr(business, "whatsapp_number", "") or ""
    clean_phone = "".join(filter(str.isdigit, phone))
    
    welcome = f"Hello {business.name}! I would like to inquire about your services."
    encoded_text = quote(welcome)
    click_to_chat_url = f"https://wa.me/{clean_phone}?text={encoded_text}" if clean_phone else ""

    return {
        "business_name": business.name,
        "business_slug": business.slug,
        "whatsapp_number": phone,
        "click_to_chat_url": click_to_chat_url,
        "webhook_url": f"/api/chat/whatsapp/{business.slug}/webhook",
        "verify_token": WHATSAPP_VERIFY_TOKEN
    }
