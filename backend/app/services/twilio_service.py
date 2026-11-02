import logging
import httpx
from app.config import settings

logger = logging.getLogger("idevify-twilio-service")

class TwilioService:
    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.api_key_sid = settings.TWILIO_API_KEY_SID
        self.api_key_secret = settings.TWILIO_API_KEY_SECRET
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.default_from = settings.TWILIO_WHATSAPP_FROM or "whatsapp:+14155238886"

    def is_configured(self) -> bool:
        """Checks if Twilio credentials are provided."""
        has_account = bool(self.account_sid)
        has_auth = bool(self.auth_token or (self.api_key_sid and self.api_key_secret))
        return has_account and has_auth

    def _get_auth(self):
        """Returns HTTP Basic Auth tuple for Twilio REST API."""
        if self.api_key_sid and self.api_key_secret:
            return (self.api_key_sid, self.api_key_secret)
        return (self.account_sid, self.auth_token)

    async def send_whatsapp_message(self, to_number: str, message_text: str) -> dict:
        """
        Dispatches an outbound WhatsApp message via Twilio REST API.
        Automatically formats 'whatsapp:+...' prefix and handles async dispatch.
        """
        if not self.is_configured():
            logger.info(f"[TWILIO_MOCK_DISPATCH] To: {to_number} | Message: {message_text[:60]}...")
            return {"status": "mocked", "detail": "Twilio credentials not configured in environment"}

        clean_to = to_number.strip()
        if not clean_to.startswith("whatsapp:"):
            clean_to = f"whatsapp:{clean_to}"

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = {
            "From": self.default_from,
            "To": clean_to,
            "Body": message_text
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, auth=self._get_auth(), data=data)
                if res.status_code in (200, 201):
                    res_data = res.json()
                    logger.info(f"Twilio WhatsApp message sent successfully: SID {res_data.get('sid')} to {clean_to}")
                    return {"status": "success", "sid": res_data.get("sid")}
                else:
                    logger.warning(f"Twilio dispatch HTTP {res.status_code}: {res.text}")
                    return {"status": "failed", "error": res.text, "code": res.status_code}
        except Exception as e:
            logger.error(f"Error dispatching Twilio WhatsApp message: {e}")
            return {"status": "error", "error": str(e)}

    async def notify_owner_whatsapp(self, owner_phone: str, ticket_number: str, priority: str, summary: str) -> dict:
        """Sends an urgent WhatsApp notification to the business owner about a new ticket."""
        msg = (
            f"🚨 *[Iveri Alert]* New {priority.upper()} Support Ticket #{ticket_number}\n\n"
            f"📝 *Inquiry:* {summary[:200]}\n\n"
            f"👉 Open your Iveri Dashboard to view and resolve in 1 click."
        )
        return await self.send_whatsapp_message(owner_phone, msg)

    async def notify_customer_ticket_resolved(
        self,
        customer_phone: str,
        ticket_number: str,
        question: str,
        resolved_answer: str
    ) -> dict:
        """Sends an outbound WhatsApp message to the customer with the verified resolution answer."""
        msg = (
            f"✅ *[Iveri Support]* Update regarding Ticket #{ticket_number}\n\n"
            f"❓ *Your Question:* {question[:150]}\n\n"
            f"💬 *Verified Answer:* {resolved_answer}\n\n"
            f"Thank you for reaching out!"
        )
        return await self.send_whatsapp_message(customer_phone, msg)

twilio_service = TwilioService()
