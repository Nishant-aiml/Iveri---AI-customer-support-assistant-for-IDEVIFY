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

@router.post("/{notification_id}/unread", response_model=Dict[str, Any])
async def mark_notification_unread(
    notification_id: str,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Marks a single notification as unread."""
    query = select(Notification).where(
        Notification.id == notification_id,
        Notification.business_id == owner.business_id
    )
    notif = (await db.execute(query)).scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")

    notif.is_read = False
    await db.commit()
    return {"status": "success", "id": notification_id, "is_read": False}

@router.post("/{notification_id}/toggle-read", response_model=Dict[str, Any])
async def toggle_notification_read(
    notification_id: str,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Toggles read/unread status of a single notification."""
    query = select(Notification).where(
        Notification.id == notification_id,
        Notification.business_id == owner.business_id
    )
    notif = (await db.execute(query)).scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")

    notif.is_read = not notif.is_read
    await db.commit()
    return {"status": "success", "id": notification_id, "is_read": notif.is_read}

@router.delete("/{notification_id}", response_model=Dict[str, Any])
async def delete_single_notification(
    notification_id: str,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Permanently deletes a single notification."""
    query = select(Notification).where(
        Notification.id == notification_id,
        Notification.business_id == owner.business_id
    )
    notif = (await db.execute(query)).scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")

    await db.delete(notif)
    await db.commit()
    return {"status": "success", "id": notification_id}

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
    else:
        existing.p256dh = req.p256dh
        existing.auth = req.auth
        existing.user_id = owner.id
        await db.commit()

    return {"status": "success", "message": "Device successfully subscribed to real-time mobile push notifications."}

@router.get("/push/status", response_model=Dict[str, Any])
async def get_push_status(
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Checks whether the business owner has active push-subscribed devices."""
    biz_id = owner.business_id
    query = select(func.count(PushSubscription.id)).where(PushSubscription.business_id == biz_id)
    count = (await db.execute(query)).scalar() or 0
    return {
        "has_active_devices": count > 0,
        "device_count": count
    }

@router.post("/push/test", response_model=Dict[str, Any])
async def test_push_notification(
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """
    Dispatches a real-time test push notification to all subscribed mobile/desktop devices.
    Allows owners to verify background ringing, vibration, and app icon badges with the app closed.
    """
    biz_id = owner.business_id
    query = select(PushSubscription).where(PushSubscription.business_id == biz_id)
    subs = (await db.execute(query)).scalars().all()

    if not subs:
        return {
            "status": "warning",
            "sent_count": 0,
            "message": "No registered phone or browser devices found. Please tap 'Enable Mobile Push' and allow browser notifications first."
        }

    sent_count = 0
    test_payload = {
        "title": "🔔 Iveri Live Test Alert",
        "body": "Your device is connected! Notifications and app icon badges work even when the app is closed.",
        "url": "/dashboard#tickets",
        "unread_count": 1,
        "tag": "iveri-live-test",
        "ticket_number": "TEST-LIVE"
    }

    for sub in subs:
        sub_dict = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}
        try:
            ok = await push_service.send_web_push(sub_dict, test_payload)
            if ok:
                sent_count += 1
        except Exception:
            pass

    return {
        "status": "success",
        "sent_count": sent_count,
        "total_devices": len(subs),
        "message": f"Dispatched live test notification to {sent_count} device(s)!"
    }
