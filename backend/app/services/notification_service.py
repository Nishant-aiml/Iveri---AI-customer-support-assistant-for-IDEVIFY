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
        """Generates a human-friendly ticket identifier e.g. TICK-8492-4A7B."""
        import uuid
        num = random.randint(1000, 9999)
        suffix = uuid.uuid4().hex[:4].upper()
        return f"TICK-{num}-{suffix}"

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
        try:
            await db.flush()
        except Exception as ticket_err:
            logger.warning(f"Initial ticket flush error: {ticket_err}")
            # If foreign key check failed on message_id, flush with message_id=None
            if message_id:
                ticket.message_id = None
                try:
                    await db.flush()
                except Exception as inner_err:
                    logger.error(f"Fallback ticket flush error: {inner_err}")

        # 2. Create In-App Notification (for Dashboard Bell)
        try:
            notif_title = f"New {priority.capitalize()} Ticket #{ticket_num}"
            notif_msg = f"{subject} from {channel.upper()}: '{description[:100]}...'"
            notification = Notification(
                business_id=business.id,
                ticket_id=ticket.id if hasattr(ticket, 'id') else None,
                type="ticket_created" if priority != "urgent" else "contact_request",
                title=notif_title,
                message=notif_msg,
                link_url="/dashboard#tickets",
                is_read=False
            )
            db.add(notification)
            await db.flush()
        except Exception as notif_err:
            logger.warning(f"Notification record creation notice: {notif_err}")

        # 3. Find Business Owner Email for Direct Alert
        owner_email = None
        try:
            owner_query = select(User).where(User.business_id == business.id, User.role == "owner").limit(1)
            owner_user = (await db.execute(owner_query)).scalar_one_or_none()
            if owner_user and owner_user.email:
                owner_email = owner_user.email
        except Exception as owner_err:
            logger.warning(f"Could not retrieve owner email: {owner_err}")

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

        # 6. Dispatch WhatsApp Alert to Business Owner (if owner whatsapp_number is configured and enable_whatsapp is ON)
        is_whatsapp_enabled = getattr(business, "enable_whatsapp", True) is not False
        if business.whatsapp_number and is_whatsapp_enabled:
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

        # 7. Dispatches Instant Confirmation / Acknowledgment to the CUSTOMER
        # 7a. Customer WhatsApp Confirmation
        if customer_phone and is_whatsapp_enabled:
            try:
                from app.services.twilio_service import twilio_service
                await twilio_service.notify_customer_ticket_created(
                    customer_phone=customer_phone,
                    ticket_number=ticket_num,
                    business_name=business.name,
                    customer_name=customer_name
                )
            except Exception as e:
                logger.warning(f"Twilio WhatsApp customer confirmation notice: {e}")

        # 7b. Customer Email Confirmation
        if customer_email:
            try:
                await email_service.send_customer_ticket_acknowledgment(
                    to_email=customer_email,
                    business_name=business.name,
                    ticket_number=ticket_num,
                    customer_name=customer_name,
                    question_text=description
                )
            except Exception as e:
                logger.warning(f"Customer email confirmation notice: {e}")

        logger.info(f"Ticket {ticket_num} created successfully for business {business.name}")
        return ticket

notification_service = NotificationService()
