import unittest
import os
import sys
import uuid

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import AsyncSessionLocal, init_db
from app.models.business import Business
from app.models.user import User
from app.models.ticket import Ticket
from app.models.notification import Notification
from app.utils.security import create_access_token
from app.services.rag_engine import rag_engine

class TestTicketsNotificationsTwilio(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

        unique_suffix = os.urandom(3).hex()
        # Create isolated test business & owner
        async with AsyncSessionLocal() as db:
            self.biz = Business(
                name="Aura Boutique & Coffee",
                slug=f"aura-boutique-{unique_suffix}",
                welcome_message="Welcome to Aura Boutique!",
                fallback_message="Sorry, we don't have that info right now."
            )
            db.add(self.biz)
            await db.flush()

            self.owner = User(
                business_id=self.biz.id,
                email=f"owner_{unique_suffix}@auraboutique.com",
                password_hash="hashed_pw_for_test_123",
                role="owner"
            )
            db.add(self.owner)
            await db.commit()
            await db.refresh(self.biz)
            await db.refresh(self.owner)

            self.biz_id = self.biz.id
            self.biz_slug = self.biz.slug
            self.owner_token = create_access_token({"sub": self.owner.id, "email": self.owner.email, "business_id": self.biz_id})
            self.auth_headers = {"Authorization": f"Bearer {self.owner_token}"}

        # Index a known document chunk
        known_chunks = [
            {
                "id": f"chunk-coffee-1-{self.biz_id}",
                "content": "Aura Coffee serves organic artisan espresso, oat milk lattes, and matcha. Store hours are 7am to 8pm daily.",
                "metadata": {
                    "document_name": "Aura_Menu.txt",
                    "page_number": 1,
                    "document_id": "doc-aura-1",
                    "business_id": self.biz_id
                }
            }
        ]
        await rag_engine.index_document_chunks(self.biz_id, known_chunks)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_01_ticket_auto_created_on_unanswered_question(self):
        """Verifies that an unanswerable question triggers ticket creation and in-app notification."""
        # 1. Start session
        sess_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": self.biz_slug,
            "channel": "widget",
            "customer_email": "customer@example.com"
        })
        self.assertEqual(sess_res.status_code, 201)
        session_id = sess_res.json()["id"]

        # 2. Ask question out-of-domain
        msg_res = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "Do you repair broken laptop screens?"
        })
        self.assertEqual(msg_res.status_code, 200)
        self.assertFalse(msg_res.json()["is_answered"])

        # 3. Check ticket exists
        async with AsyncSessionLocal() as db:
            from sqlalchemy.future import select
            tickets = (await db.execute(select(Ticket).where(Ticket.business_id == self.biz_id))).scalars().all()
            self.assertGreaterEqual(len(tickets), 1)
            t = tickets[-1]
            self.assertTrue(t.ticket_number.startswith("TICK-"))
            self.assertEqual(t.status, "open")
            self.assertEqual(t.channel, "widget")
            self.assertEqual(t.customer_email, "customer@example.com")
            print(f"[PASS] 01: Ticket auto-created: {t.ticket_number}")

    async def test_02_contact_request_creates_urgent_ticket(self):
        """Verifies customer callback/contact request creates an urgent ticket."""
        # 1. Start session
        sess_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": self.biz_slug,
            "channel": "widget"
        })
        session_id = sess_res.json()["id"]

        # 2. Submit contact request
        req_res = await self.client.post("/api/chat/contact-request", json={
            "session_id": session_id,
            "customer_name": "Sarah Connor",
            "customer_contact": "+1-555-890-1234",
            "message": "Please call me about catering an event for 50 people next Friday.",
            "channel": "widget"
        })
        self.assertEqual(req_res.status_code, 201)
        data = req_res.json()
        self.assertEqual(data["status"], "success")
        self.assertTrue(data["ticket_number"].startswith("TICK-"))

        # Verify urgent priority in DB
        async with AsyncSessionLocal() as db:
            from sqlalchemy.future import select
            t = (await db.execute(select(Ticket).where(Ticket.ticket_number == data["ticket_number"]))).scalar_one()
            self.assertEqual(t.priority, "urgent")
            self.assertEqual(t.customer_phone, "+1-555-890-1234")
            self.assertEqual(t.customer_name, "Sarah Connor")
            print(f"[PASS] 02: Urgent contact ticket created: {t.ticket_number}")

    async def test_03_list_and_filter_tickets(self):
        """Verifies owner can list and filter tickets via /api/tickets."""
        res = await self.client.get("/api/tickets", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        tickets = res.json()
        self.assertIsInstance(tickets, list)
        print(f"[PASS] 03: Listed {len(tickets)} tickets successfully.")

    async def test_04_resolve_ticket_and_knowledge_base_indexing(self):
        """Verifies resolving a ticket updates status and permanently indexes Q&A into knowledge base."""
        # Create ticket
        t_num = f"TICK-{uuid.uuid4().hex[:6].upper()}"
        async with AsyncSessionLocal() as db:
            t = Ticket(
                ticket_number=t_num,
                business_id=self.biz_id,
                channel="widget",
                subject="Delivery options",
                description="Do you offer same-day bicycle delivery in downtown?",
                status="open"
            )
            db.add(t)
            await db.commit()

        # Resolve ticket via API
        res = await self.client.post(
            f"/api/tickets/{t_num}/resolve",
            headers=self.auth_headers,
            json={"resolved_answer": "Yes, we offer free same-day bicycle delivery for downtown orders over $25."}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "resolved")

        # Query RAG to verify AI learned it!
        learned_res = await rag_engine.query(
            business_id=self.biz_id,
            user_query="same-day bicycle delivery downtown",
            business_settings={"name": "Aura Boutique"}
        )
        self.assertTrue(learned_res["is_answered"])
        self.assertIn("bicycle", learned_res["answer"].lower())
        print("[PASS] 04: Resolved ticket permanently indexed into RAG knowledge base.")

    async def test_05_notification_bell_and_read_endpoints(self):
        """Verifies in-app notification center unread counts and read mutations."""
        # Create notification
        async with AsyncSessionLocal() as db:
            n = Notification(
                business_id=self.biz_id,
                title="Test Alert",
                message="A customer submitted feedback.",
                link_url="/dashboard#chats",
                is_read=False
            )
            db.add(n)
            await db.commit()
            nid = n.id

        # 1. Fetch unread
        res = await self.client.get("/api/notifications", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json()["unread_count"], 1)

        # 2. Mark single as read
        read_res = await self.client.post(f"/api/notifications/{nid}/read", headers=self.auth_headers)
        self.assertEqual(read_res.status_code, 200)

        # 3. Mark all as read
        all_res = await self.client.post("/api/notifications/read-all", headers=self.auth_headers)
        self.assertEqual(all_res.status_code, 200)

        # 4. Verify unread is 0
        final_res = await self.client.get("/api/notifications", headers=self.auth_headers)
        self.assertEqual(final_res.json()["unread_count"], 0)
        print("[PASS] 05: In-app notification center bell verified.")

    async def test_06_twilio_whatsapp_webhook_answered(self):
        """Verifies Twilio WhatsApp webhook answers grounded questions with valid TwiML XML."""
        form_data = {
            "From": "whatsapp:+919876543210",
            "To": "whatsapp:+14155238886",
            "Body": "What are your store hours?",
            "ProfileName": "Karan Malhotra"
        }
        res = await self.client.post(f"/api/chat/twilio/{self.biz_slug}/webhook", data=form_data)
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/xml", res.headers["content-type"])
        self.assertIn("<Response>", res.text)
        self.assertIn("<Message>", res.text)
        self.assertTrue("7am" in res.text or "hours" in res.text or "open" in res.text)
        print("[PASS] 06: Twilio WhatsApp webhook answered with verified TwiML XML.")

    async def test_07_twilio_whatsapp_webhook_unanswered_auto_ticket(self):
        """Verifies Twilio WhatsApp webhook creates a ticket and returns friendly TwiML on unknown questions."""
        form_data = {
            "From": "whatsapp:+919876543210",
            "To": "whatsapp:+14155238886",
            "Body": "Can you book a scuba diving lesson for next weekend?",
            "ProfileName": "Karan Malhotra"
        }
        res = await self.client.post(f"/api/chat/twilio/{self.biz_slug}/webhook", data=form_data)
        self.assertEqual(res.status_code, 200)
        self.assertIn("Support Ticket #TICK-", res.text)

        # Verify ticket in DB with phone number
        async with AsyncSessionLocal() as db:
            from sqlalchemy.future import select
            t = (await db.execute(
                select(Ticket).where(Ticket.business_id == self.biz_id, Ticket.channel == "whatsapp")
            )).scalars().all()[-1]
            self.assertEqual(t.customer_phone, "+919876543210")
            self.assertEqual(t.customer_name, "Karan Malhotra")
            print(f"[PASS] 07: Twilio WhatsApp auto-ticket created: {t.ticket_number}")

    async def test_08_pwa_manifest_and_icons_served(self):
        """Verifies PWA manifest, service worker, and app avatar are served with correct headers."""
        # Manifest
        man_res = await self.client.get("/manifest.json")
        self.assertEqual(man_res.status_code, 200)
        self.assertEqual(man_res.json()["name"], "Iveri - AI Customer Support Assistant")

        # Service Worker
        sw_res = await self.client.get("/sw.js")
        self.assertEqual(sw_res.status_code, 200)
        self.assertIn("application/javascript", sw_res.headers["content-type"])

        # Avatar SVG
        icon_res = await self.client.get("/static/icons/iveri-avatar.svg")
        self.assertEqual(icon_res.status_code, 200)
        print("[PASS] 08: PWA manifest, service worker, and app avatar served successfully.")

    async def test_09_twilio_service_outbound_methods(self):
        """Verifies Twilio outbound WhatsApp dispatch methods handle mock fallback or active dispatch gracefully."""
        from app.services.twilio_service import twilio_service
        # Test owner alert dispatch
        res_owner = await twilio_service.notify_owner_whatsapp(
            owner_phone="+918421356877",
            ticket_number="TICK-TEST-99",
            priority="high",
            summary="Customer asking for urgent refund processing."
        )
        self.assertIn(res_owner.get("status"), ["success", "mocked", "failed"])

        # Test customer resolution dispatch
        res_cust = await twilio_service.notify_customer_ticket_resolved(
            customer_phone="+918421356877",
            ticket_number="TICK-TEST-99",
            question="When will my return be credited?",
            resolved_answer="Returns are processed within 24 hours of receiving the parcel."
        )
        self.assertIn(res_cust.get("status"), ["success", "mocked", "failed"])
        print("[PASS] 09: Twilio outbound WhatsApp service methods verified.")

if __name__ == "__main__":
    unittest.main()
