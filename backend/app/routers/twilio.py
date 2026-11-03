import html
import logging
from typing import Any
from urllib.parse import quote
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc
from sqlalchemy.future import select
from app.database import get_db
from app.models.business import Business
from app.models.chat import ChatSession, ChatMessage
from app.services.rag_engine import rag_engine
from app.services.notification_service import notification_service
from app.services.sentiment_analyzer import sentiment_analyzer
from app.services.topic_analyzer import topic_analyzer

logger = logging.getLogger("idevify-twilio")
router = APIRouter(prefix="/api/chat/twilio", tags=["Twilio WhatsApp Webhook"])

def build_twiml_message(body_text: str) -> Response:
    """Constructs a standard, compliant TwiML XML response for Twilio."""
    escaped = html.escape(body_text.strip())
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{escaped}</Message>
</Response>"""
    return Response(content=xml_content, media_type="application/xml")

@router.post("/webhook")
@router.post("/{business_slug}/webhook")
async def twilio_whatsapp_webhook(
    business_slug: str = "default",
    request: Request = None,
    From: str = Form(None),
    To: str = Form(None),
    Body: str = Form(None),
    ProfileName: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Twilio WhatsApp Inbound Webhook.
    Receives incoming customer messages from Twilio WhatsApp Sandbox or Production Numbers,
    executes Hybrid RAG + Guardrails, records the chat session, and returns TwiML with the answer
    or opens a support ticket with instant notifications if unanswered.
    """
    # Support both application/x-www-form-urlencoded and application/json (for testing)
    content_type = request.headers.get("content-type", "")
    sender_raw = From
    message_text = Body
    customer_name = ProfileName or "WhatsApp Customer"

    if "application/json" in content_type:
        try:
            payload = await request.json()
            sender_raw = payload.get("From") or payload.get("from") or payload.get("sender_phone")
            message_text = payload.get("Body") or payload.get("body") or payload.get("message")
            customer_name = payload.get("ProfileName") or payload.get("name") or customer_name
        except Exception:
            pass

    if not sender_raw or not message_text or not message_text.strip():
        logger.warning(f"Twilio webhook for {business_slug} received empty sender or body.")
        return build_twiml_message("Hello! Please send a message with your question.")

    # Clean phone number (strip 'whatsapp:' prefix if present)
    clean_phone = sender_raw.replace("whatsapp:", "").strip()
    clean_query = message_text.strip()

    # 1. Look up Business (with auto-fallback so Twilio never 404s)
    biz_query = select(Business).where(Business.slug == business_slug)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        first_biz_query = select(Business).order_by(Business.created_at.asc()).limit(1)
        business = (await db.execute(first_biz_query)).scalar_one_or_none()
        if not business:
            business = Business(
                name="Iveri Support",
                slug="iveri-support",
                settings={"brand_name": "Iveri AI Support"}
            )
            db.add(business)
            await db.flush()

    # 2. Find or create active WhatsApp ChatSession for this customer
    sess_query = select(ChatSession).where(
        ChatSession.business_id == business.id,
        ChatSession.channel == "whatsapp",
        ChatSession.customer_email == clean_phone
    ).order_by(ChatSession.created_at.desc()).limit(1)
    session = (await db.execute(sess_query)).scalar_one_or_none()

    if not session:
        session = ChatSession(
            business_id=business.id,
            channel="whatsapp",
            customer_email=clean_phone,
            sentiment="neutral",
            primary_topic="general"
        )
        db.add(session)
        await db.flush()

    # 3. Analyze Sentiment & Topic
    sentiment_label, _ = sentiment_analyzer.analyze(clean_query)
    topic_category = topic_analyzer.classify(clean_query)

    # 4. Record Customer Message
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

    # 4.5. Retrieve Prior Conversation History for Multi-Turn Continuity
    hist_query = select(ChatMessage).where(
        ChatMessage.session_id == session.id,
        ChatMessage.id != user_msg.id
    ).order_by(desc(ChatMessage.created_at)).limit(6)
    hist_results = (await db.execute(hist_query)).scalars().all()
    rolling_history = [
        {"role": m.sender, "content": m.content}
        for m in reversed(hist_results)
    ]

    # 5. Execute Hybrid RAG Pipeline
    biz_settings = {
        "name": business.name,
        "tone": business.tone,
        "fallback_message": business.fallback_message,
        "custom_prompt": getattr(business, "custom_prompt", "") or ""
    }
    rag_result = await rag_engine.query(
        business_id=business.id,
        user_query=clean_query,
        business_settings=biz_settings,
        chat_history=rolling_history
    )

    # 6. Record Assistant Reply
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

    # 7. Fallback & Auto-Ticketing
    if not rag_result["is_answered"]:
        ticket = await notification_service.create_ticket_and_notify(
            db=db,
            business=business,
            description=clean_query,
            subject="Unanswered WhatsApp Customer Query",
            session_id=session.id,
            message_id=assistant_msg.id,
            customer_name=customer_name,
            customer_phone=clean_phone,
            channel="whatsapp",
            priority="high"
        )
        reply_text = (
            f"Thank you for contacting {business.name}! I don't have this information in my documents, "
            f"so I have opened Support Ticket #{ticket.ticket_number} for our team. "
            f"A representative will reach out to you directly on this WhatsApp number."
        )
    else:
        reply_text = rag_result["answer"]

    await db.commit()

    # Check if client asked for JSON (e.g. unit tests or API consumers)
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header and "application/xml" not in accept_header:
        return {
            "status": "success",
            "channel": "whatsapp",
            "sender": clean_phone,
            "answer": reply_text,
            "is_answered": rag_result["is_answered"]
        }

    # Return standard TwiML response
    return build_twiml_message(reply_text)

@router.get("/{business_slug}/config")
async def get_twilio_config(business_slug: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Returns the webhook URL and instructions for Twilio WhatsApp Console integration."""
    biz_query = select(Business).where(Business.slug == business_slug)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")

    webhook_url = f"/api/chat/twilio/{business.slug}/webhook"
    default_sandbox_number = "+14155238886"
    encoded_join = quote(f"join {business.slug}")
    click_to_join_url = f"https://wa.me/14155238886?text={encoded_join}"

    return {
        "business_name": business.name,
        "business_slug": business.slug,
        "provider": "twilio",
        "webhook_url": webhook_url,
        "webhook_method": "POST (HTTP POST with Form Data)",
        "sandbox_number": default_sandbox_number,
        "click_to_join_url": click_to_join_url,
        "setup_steps": [
            "1. Open Twilio Console -> Messaging -> Try it out -> Send a WhatsApp message.",
            "2. Note your Sandbox Join Keyword (e.g. 'join silver-fox').",
            f"3. In Twilio Sandbox Settings, paste your Webhook URL: https://<your-domain>{webhook_url}",
            "4. Set HTTP POST method and click Save.",
            "5. Message the Twilio WhatsApp number from any phone to chat with your AI assistant!"
        ]
    }
