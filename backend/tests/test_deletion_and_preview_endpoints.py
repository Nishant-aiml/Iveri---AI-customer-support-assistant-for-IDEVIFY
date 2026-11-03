import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from sqlalchemy.future import select
from app.main import app
from app.database import AsyncSessionLocal, init_db
from app.models.user import User
from app.models.business import Business
from app.models.document import Document, DocumentChunk
from app.models.ticket import Ticket
from app.models.chat import ChatSession, ChatMessage
from app.utils.security import create_access_token, hash_password

class TestDeletionAndPreviewEndpoints(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        self.db = AsyncSessionLocal()

        # Create a test business
        self.biz_id = "test-deletion-biz-id"
        biz = Business(
            id=self.biz_id,
            name="Apex Dental Care",
            slug="apex-dental-care",
            share_token="apex-token-123"
        )
        self.db.add(biz)

        # Create test owner user
        self.owner_id = "test-deletion-owner-id"
        owner = User(
            id=self.owner_id,
            business_id=self.biz_id,
            email="owner@apexdental.com",
            password_hash=hash_password("ApexSecure123!"),
            role="owner"
        )
        self.db.add(owner)
        await self.db.commit()

        self.token = create_access_token({"sub": self.owner_id, "role": "owner", "business_id": self.biz_id})
        self.auth_headers = {"Authorization": f"Bearer {self.token}"}

        # Create sample document with dummy file on disk
        self.test_file_path = os.path.abspath("test_sample_guide.pdf")
        with open(self.test_file_path, "wb") as f:
            f.write(b"%PDF-1.4 sample pdf content for cross verification test")

        self.doc_id = "test-doc-inspect-id"
        doc = Document(
            id=self.doc_id,
            business_id=self.biz_id,
            file_name="Lakeview_Dental_Patient_Guide.pdf",
            file_type="pdf",
            storage_path=self.test_file_path,
            status="INDEXED",
            chunk_count=2,
            total_pages=1,
            processed_pages=1
        )
        self.db.add(doc)

        chunk1 = DocumentChunk(
            id="test-chunk-1",
            document_id=self.doc_id,
            business_id=self.biz_id,
            chunk_index=0,
            page_number=1,
            content="Emergency clinic is open 10am to 1pm. Contact: Phone +91 20 5550 2468."
        )
        chunk2 = DocumentChunk(
            id="test-chunk-2",
            document_id=self.doc_id,
            business_id=self.biz_id,
            chunk_index=1,
            page_number=1,
            content="Appointments email: appointments@lakeviewdental.example."
        )
        self.db.add(chunk1)
        self.db.add(chunk2)

        # Create sample ticket
        self.ticket_id = "test-ticket-del-id"
        ticket = Ticket(
            id=self.ticket_id,
            ticket_number="TICK-DEL-01",
            business_id=self.biz_id,
            customer_name="Jane Doe",
            customer_phone="+919876543210",
            subject="Pricing Inquiry",
            description="How much is root canal treatment?",
            priority="medium",
            status="open"
        )
        self.db.add(ticket)

        # Create sample chat session with messages
        self.session_id = "test-session-del-id"
        session = ChatSession(
            id=self.session_id,
            business_id=self.biz_id,
            customer_email="jane@example.com",
            channel="public_link"
        )
        self.db.add(session)

        msg1 = ChatMessage(
            session_id=self.session_id,
            sender="customer",
            content="Hello, what is your contact number?"
        )
        msg2 = ChatMessage(
            session_id=self.session_id,
            sender="assistant",
            content="Our contact number is +91 20 5550 2468."
        )
        self.db.add(msg1)
        self.db.add(msg2)

        await self.db.commit()

    async def asyncTearDown(self):
        # Cleanup dummy file
        if os.path.exists(self.test_file_path):
            try:
                os.remove(self.test_file_path)
            except Exception:
                pass

        # Cleanup DB
        await self.db.execute(select(Document).where(Document.business_id == self.biz_id))
        docs = (await self.db.execute(select(Document).where(Document.business_id == self.biz_id))).scalars().all()
        for d in docs:
            await self.db.delete(d)

        tickets = (await self.db.execute(select(Ticket).where(Ticket.business_id == self.biz_id))).scalars().all()
        for t in tickets:
            await self.db.delete(t)

        sessions = (await self.db.execute(select(ChatSession).where(ChatSession.business_id == self.biz_id))).scalars().all()
        for s in sessions:
            await self.db.delete(s)

        user = (await self.db.execute(select(User).where(User.id == self.owner_id))).scalar_one_or_none()
        if user:
            await self.db.delete(user)

        biz = (await self.db.execute(select(Business).where(Business.id == self.biz_id))).scalar_one_or_none()
        if biz:
            await self.db.delete(biz)

        await self.db.commit()
        await self.db.close()

    async def test_01_document_file_preview_with_token(self):
        """Ensures the business owner can preview/stream the uploaded PDF file via query token."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get(f"/api/documents/{self.doc_id}/file?token={self.token}")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.headers.get("content-type"), "application/pdf")
            self.assertIn("inline", res.headers.get("content-disposition", ""))
            self.assertIn(b"%PDF-1.4", res.content)

    async def test_02_document_chunks_inspection(self):
        """Ensures the business owner can retrieve extracted knowledge chunks for cross verification."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get(f"/api/documents/{self.doc_id}/chunks", headers=self.auth_headers)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["document_id"], self.doc_id)
            self.assertEqual(data["total_chunks"], 2)
            self.assertIn("Phone +91 20 5550 2468", data["chunks"][0]["content"])

    async def test_03_delete_ticket(self):
        """Ensures the business owner can permanently delete a support ticket."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.delete(f"/api/tickets/{self.ticket_id}", headers=self.auth_headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], "success")

            # Verify ticket is gone
            chk = (await self.db.execute(select(Ticket).where(Ticket.id == self.ticket_id))).scalar_one_or_none()
            self.assertIsNone(chk)

    async def test_04_delete_chat_session(self):
        """Ensures the business owner can permanently delete a customer chat session and history."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.delete(f"/api/dashboard/chats/{self.session_id}", headers=self.auth_headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], "success")

            # Verify session and messages are deleted
            chk = (await self.db.execute(select(ChatSession).where(ChatSession.id == self.session_id))).scalar_one_or_none()
            self.assertIsNone(chk)
            msgs = (await self.db.execute(select(ChatMessage).where(ChatMessage.session_id == self.session_id))).scalars().all()
            self.assertEqual(len(msgs), 0)

    async def test_05_unauthorized_document_file_preview_rejected(self):
        """Ensures that unauthenticated requests to view document files are strictly rejected."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get(f"/api/documents/{self.doc_id}/file")
            self.assertEqual(res.status_code, 401)

if __name__ == "__main__":
    unittest.main()
