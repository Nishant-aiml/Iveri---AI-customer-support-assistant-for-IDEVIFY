import random
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.business import Business
from app.models.user import User
from app.models.ticket import Ticket
from app.models.notification import Notification
from app.models.push_subscription import PushSubscription
from app.services.email_service import email_service
from app.services.push_service import push_service

logger = logging.getLogger("idevify-notifications")

class NotificationService:
    @staticmethod
    def generate_ticket_number() -> str:
        """Generates a human-friendly ticket identifier e.g. TICK-8492."""
        num = random.randint(1000, 9999)
        return f"TICK-{num}"

    async def create_ticket_and_notify(
        self,
        db: AsyncSession,
        business: Business,
        description: str,
        subject: str = "Unanswered Customer Query",
        session_id: str | None = None,
        message_id: str | None = None,
        customer_name: str | None = None,
        customer_email: str | None = None,
        customer_phone: str | None = None,
        channel: str = "widget",
        priority: str = "medium"
    ) -> Ticket:
        """Provisions a new support ticket and sends omnichannel alerts (In-App, Email, Push)."""
        ticket_num = self.generate_ticket_number()

        # 1. Create Ticket Record
        ticket = Ticket(
            ticket_number=ticket_num,
            business_id=business.id,
            session_id=session_id,
            message_id=message_id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            channel=channel,
            subject=subject,
            description=description,
            priority=priority,
            status="open"
        )
        db.add(ticket)
        await db.flush()

        # 2. Create In-App Notification (for Dashboard Bell)
        notif_title = f"New {priority.capitalize()} Ticket #{ticket_num}"
        notif_msg = f"{subject} from {channel.upper()}: '{description[:100]}...'"
        notification = Notification(
            business_id=business.id,
            ticket_id=ticket.id,
            type="ticket_created" if priority != "urgent" else "contact_request",
            title=notif_title,
            message=notif_msg,
            link_url="/dashboard#tickets",
            is_read=False
        )
        db.add(notification)
        await db.flush()

        # 3. Find Business Owner Email for Direct Alert
        owner_email = None
        owner_query = select(User).where(User.business_id == business.id, User.role == "owner").limit(1)
        owner_user = (await db.execute(owner_query)).scalar_one_or_none()
        if owner_user and owner_user.email:
            owner_email = owner_user.email

        # 4. Asynchronously Dispatch Email Alert
        contact_info = customer_phone or customer_email or "In-Chat Customer"
        if owner_email:
            try:
                await email_service.send_ticket_alert(
                    to_email=owner_email,
                    business_name=business.name,
                    ticket_number=ticket_num,
                    customer_contact=contact_info,
                    channel=channel,
                    question_text=description,
                    priority=priority
                )
            except Exception as e:
                logger.warning(f"Email dispatch error: {e}")

        # 5. Asynchronously Dispatch Web Push to Registered Devices
        try:
            push_query = select(PushSubscription).where(PushSubscription.business_id == business.id)
            subs = (await db.execute(push_query)).scalars().all()
            for sub in subs:
                sub_dict = {
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh,
                        "auth": sub.auth
                    }
                }
                push_payload = {
                    "title": f"🚨 {notif_title}",
                    "body": f"{contact_info}: {description[:120]}",
                    "url": "/dashboard#tickets"
                }
                await push_service.send_web_push(sub_dict, push_payload)
        except Exception as e:
            logger.warning(f"Push dispatch note: {e}")

        # 6. Dispatch WhatsApp Alert to Business Owner (if owner whatsapp_number is configured)
        if business.whatsapp_number:
            try:
                from app.services.twilio_service import twilio_service
                await twilio_service.notify_owner_whatsapp(
                    owner_phone=business.whatsapp_number,
                    ticket_number=ticket_num,
                    priority=priority,
                    summary=f"{contact_info}: {description[:140]}"
                )
            except Exception as e:
                logger.warning(f"Twilio WhatsApp owner notification notice: {e}")

        logger.info(f"Ticket {ticket_num} created successfully for business {business.name}")
        return ticket

notification_service = NotificationService()
