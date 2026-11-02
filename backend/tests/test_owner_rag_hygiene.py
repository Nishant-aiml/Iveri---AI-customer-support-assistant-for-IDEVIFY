import unittest
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import AsyncSessionLocal, init_db
from app.models.business import Business
from app.models.user import User
from app.models.ticket import Ticket
from app.models.document import Document
from app.utils.security import create_access_token
from app.services.rag_engine import rag_engine
from app.services.llm_client import llm_client
from sqlalchemy.future import select

class TestOwnerRAGHygiene(unittest.IsolatedAsyncioTestCase):
    """Verifies owner-only RAG training opt-in, knowledge deduplication, and data hygiene."""

    async def asyncSetUp(self):
        await init_db()
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        unique_suffix = os.urandom(3).hex()

        async with AsyncSessionLocal() as db:
            self.biz = Business(
                name="Hygiene Verified Dental",
                slug=f"hygiene-dental-{unique_suffix}",
                welcome_message="Welcome to Hygiene Dental!",
                fallback_message="We will check our dental records."
            )
            db.add(self.biz)
            await db.flush()

            self.owner = User(
                business_id=self.biz.id,
                email=f"dentist_{unique_suffix}@hygienedental.example",
                password_hash="test_pw_hash",
                role="owner"
            )
            db.add(self.owner)
            await db.commit()
            await db.refresh(self.biz)
            await db.refresh(self.owner)

            self.biz_id = self.biz.id
            self.owner_token = create_access_token({
                "sub": self.owner.id,
                "email": self.owner.email,
                "business_id": self.biz_id
            })
            self.auth_headers = {"Authorization": f"Bearer {self.owner_token}"}

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_01_ticket_resolution_without_rag_training(self):
        """Resolving a ticket with train_ai=False resolves ticket without polluting knowledge base."""
        t_num = f"TICK-{uuid.uuid4().hex[:6].upper()}"
        async with AsyncSessionLocal() as db:
            t = Ticket(
                ticket_number=t_num,
                business_id=self.biz_id,
                channel="widget",
                subject="Appointment rescheduling",
                description="Can I reschedule my routine cleaning to next Tuesday at 3pm?",
                status="open"
            )
            db.add(t)
            await db.commit()

        # Resolve ticket with train_ai=False (routine greeting/response)
        res = await self.client.post(
            f"/api/tickets/{t_num}/resolve",
            headers=self.auth_headers,
            json={
                "resolved_answer": "Hi there, thank you for reaching out! Yes, you are rescheduled for Tuesday 3pm.",
                "train_ai": False
            }
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "resolved")

        # Verify no manual_qa document or chunks created
        async with AsyncSessionLocal() as db:
            doc = (await db.execute(
                select(Document).where(
                    Document.business_id == self.biz_id,
                    Document.file_name == f"verified_{t_num.lower()}.txt"
                )
            )).scalar_one_or_none()
            self.assertIsNone(doc, "No document should be created in RAG when train_ai=False")

    async def test_02_ticket_resolution_with_owner_verified_fact(self):
        """Resolving with train_ai=True and verified_knowledge_fact indexes clean rule."""
        t_num = f"TICK-{uuid.uuid4().hex[:6].upper()}"
        async with AsyncSessionLocal() as db:
            t = Ticket(
                ticket_number=t_num,
                business_id=self.biz_id,
                channel="widget",
                subject="Emergency contact inquiry",
                description="What is the after-hours emergency phone number?",
                status="open"
            )
            db.add(t)
            await db.commit()

        # Resolve ticket: customer gets greeting, but RAG learns clean factual rule
        res = await self.client.post(
            f"/api/tickets/{t_num}/resolve",
            headers=self.auth_headers,
            json={
                "resolved_answer": "Hi patient, our team has noted your question and here is our contact details.",
                "train_ai": True,
                "verified_knowledge_fact": "Hygiene Dental after-hours emergency helpline is +91 20 5550 9988, open 24/7."
            }
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "resolved")

        # Query RAG: RAG returns after-hours phone number without greeting fluff
        learned_res = await rag_engine.query(
            business_id=self.biz_id,
            user_query="what is the emergency phone number",
            business_settings={"name": "Hygiene Dental"}
        )
        self.assertTrue(learned_res["is_answered"])
        self.assertIn("5550 9988", learned_res["answer"])

    def test_03_extractive_synthesis_deduplication(self):
        """Verifies duplicate chunk excerpts do not stutter or repeat identical sentences."""
        duplicate_chunks = [
            {
                "id": "c1",
                "content": "Clinic is open Sunday 10am to 1pm. Contact: Phone +91 20 5550 2468, email care@dental.example."
            },
            {
                "id": "c2",
                "content": "Clinic is open Sunday 10am to 1pm. Contact: Phone +91 20 5550 2468, email care@dental.example."
            }
        ]
        synthesis = llm_client._synthesize_grounded_extractive("contact number", duplicate_chunks)
        # Ensure the phone number line appears only once, not duplicated
        occurrences = synthesis.count("5550 2468")
        self.assertEqual(occurrences, 1, f"Expected 1 occurrence of phone number, got {occurrences}:\n{synthesis}")
