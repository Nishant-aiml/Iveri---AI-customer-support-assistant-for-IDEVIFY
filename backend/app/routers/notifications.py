from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, func, update
from app.database import get_db
from app.models.user import User
from app.models.notification import Notification
from app.models.push_subscription import PushSubscription
from app.utils.security import get_current_owner
from app.schemas.ticket import NotificationResponse, PushSubscribeRequest
from app.services.push_service import push_service

router = APIRouter(prefix="/api/notifications", tags=["Notifications & Alerts"])

@router.get("", response_model=Dict[str, Any])
async def get_notifications(
    limit: int = 30,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Returns the unread notification count and list of recent alerts for the dashboard bell."""
    biz_id = owner.business_id

    # 1. Unread count
    unread_count_query = select(func.count(Notification.id)).where(
        Notification.business_id == biz_id,
        Notification.is_read.is_(False)
    )
    unread_count = (await db.execute(unread_count_query)).scalar() or 0

    # 2. Recent alerts
    list_query = (
        select(Notification)
        .where(Notification.business_id == biz_id)
        .order_by(desc(Notification.created_at))
        .limit(limit)
    )
    notifications = (await db.execute(list_query)).scalars().all()

    return {
        "unread_count": unread_count,
        "items": [
            NotificationResponse.model_validate(n) for n in notifications
        ]
    }

@router.post("/{notification_id}/read", response_model=Dict[str, Any])
async def mark_notification_read(
    notification_id: str,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Marks a single notification as read."""
    query = select(Notification).where(
        Notification.id == notification_id,
        Notification.business_id == owner.business_id
    )
    notif = (await db.execute(query)).scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")

    notif.is_read = True
    await db.commit()
    return {"status": "success", "id": notification_id, "is_read": True}

@router.post("/read-all", response_model=Dict[str, Any])
async def mark_all_notifications_read(
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Marks all notifications for the business as read."""
    stmt = (
        update(Notification)
        .where(Notification.business_id == owner.business_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    await db.execute(stmt)
    await db.commit()
    return {"status": "success", "message": "All notifications marked as read."}

@router.get("/push/vapid-public-key", response_model=Dict[str, str])
async def get_vapid_public_key():
    """Returns the VAPID public key for Web Push client subscription."""
    return {"public_key": push_service.get_public_key()}

@router.post("/push/subscribe", response_model=Dict[str, str])
async def subscribe_push_notifications(
    req: PushSubscribeRequest,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Registers a browser Web Push subscription for native mobile/desktop notifications."""
    biz_id = owner.business_id

    # Check if subscription already exists
    query = select(PushSubscription).where(
        PushSubscription.business_id == biz_id,
        PushSubscription.endpoint == req.endpoint
    )
    existing = (await db.execute(query)).scalar_one_or_none()
    if not existing:
        sub = PushSubscription(
            business_id=biz_id,
            user_id=owner.id,
            endpoint=req.endpoint,
            p256dh=req.p256dh,
            auth=req.auth
        )
        db.add(sub)
        await db.commit()

    return {"status": "success", "message": "Device successfully subscribed to real-time mobile push notifications."}
