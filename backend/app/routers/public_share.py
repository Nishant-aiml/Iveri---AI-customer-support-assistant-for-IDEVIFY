from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db
from app.models.business import Business
from app.models.chat import ChatSession, ChatMessage
from app.models.unanswered import UnansweredQuestion

router = APIRouter(prefix="/api/public/share", tags=["Public Share Permalinks"])

@router.get("/session/{session_id}")
async def get_shared_chat_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Public read-only permalink endpoint to view a customer chat transcript."""
    query = select(ChatSession).where(ChatSession.id == session_id)
    session = (await db.execute(query)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found or expired.")

    biz = (await db.execute(select(Business).where(Business.id == session.business_id))).scalar_one_or_none()
    biz_name = biz.name if biz else "Business Assistant"
    brand_color = biz.brand_color if biz else "#2563eb"
    avatar_url = biz.avatar_url if biz else ""

    msg_query = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at)
    )
    messages = (await db.execute(msg_query)).scalars().all()

    return {
        "type": "session",
        "session_id": session.id,
        "business_name": biz_name,
        "brand_color": brand_color,
        "avatar_url": avatar_url,
        "started_at": session.created_at.isoformat(),
        "sentiment": session.sentiment or "neutral",
        "primary_topic": session.primary_topic or "general",
        "customer_email": session.customer_email,
        "messages": [
            {
                "id": m.id,
                "sender": m.sender,
                "content": m.content,
                "is_answered": m.is_answered,
                "feedback": m.feedback,
                "latency_ms": m.latency_ms,
                "llm_provider": m.llm_provider_used,
                "citations": m.source_citations,
                "created_at": m.created_at.isoformat()
            }
            for m in messages
        ]
    }

@router.get("/unanswered/{unanswered_id}")
async def get_shared_unanswered_question(unanswered_id: str, db: AsyncSession = Depends(get_db)):
    """Public read-only permalink endpoint to view an unanswered inquiry item."""
    query = select(UnansweredQuestion).where(UnansweredQuestion.id == unanswered_id)
    item = (await db.execute(query)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inquiry not found.")

    biz = (await db.execute(select(Business).where(Business.id == item.business_id))).scalar_one_or_none()
    biz_name = biz.name if biz else "Business Assistant"

    return {
        "type": "unanswered",
        "unanswered_id": item.id,
        "business_name": biz_name,
        "question_text": item.question_text,
        "customer_email": item.customer_email,
        "is_resolved": item.is_resolved,
        "resolved_answer": item.resolved_answer,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "created_at": item.created_at.isoformat()
    }
