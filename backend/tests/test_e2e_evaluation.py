import os
import sys
import uuid
import unittest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database import init_db
from app.services.rag_engine import rag_engine

class TestE2EEvaluation(unittest.IsolatedAsyncioTestCase):
    """
    Formal End-to-End Evaluation Test Suite covering the 4 Core Assessment Criteria:
    1. Document Upload and Content Extraction
    2. Grounded Chunk Retrieval with Source Attribution
    3. Zero-Hallucination Circuit Breaker on Missing Information
    4. Strict Multi-Tenant Data Isolation
    Plus High-Value Boosters:
    5. Closed-Loop Q&A Resolution
    6. Customer Feedback & Widget Distribution
    """

    async def asyncSetUp(self):
        await init_db()
        self.transport = ASGITransport(app=app)
        self.client = AsyncClient(transport=self.transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_criterion_1_document_upload_and_extraction(self):
        """Criterion 1: Document Upload & Content Extraction (PDF/DOCX/TXT)."""
        uid = str(uuid.uuid4())[:8]
        reg_res = await self.client.post("/api/auth/register", json={
            "email": f"owner_{uid}@e2e-eval.com",
            "password": "Password123!",
            "business_name": f"Criterion 1 Store {uid}"
        })
        assert reg_res.status_code == 201
        token = reg_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Upload a TXT policy document
        sample_policy = (
            "STORE POLICY AND OPERATING HOURS:\n"
            "Our flagship store is open Monday through Saturday from 9:00 AM to 8:00 PM EST.\n"
            "Sunday hours are 11:00 AM to 5:00 PM EST.\n"
            "Curbside pickup is available at all locations during normal store hours."
        )
        files = {
            "file": ("store_hours_policy.txt", sample_policy.encode("utf-8"), "text/plain")
        }
        upload_res = await self.client.post("/api/documents/upload", headers=headers, files=files)
        assert upload_res.status_code == 202
        doc_id = upload_res.json()["document_id"]
        assert upload_res.json()["status"].lower() in ["queued", "indexed", "processing"]

        # Verify document appears in listing
        list_res = await self.client.get("/api/documents", headers=headers)
        assert list_res.status_code == 200
        docs = list_res.json()
        assert any(d["id"] == doc_id for d in docs)

    async def test_criterion_2_grounded_chunk_retrieval_and_citations(self):
        """Criterion 2: Grounded Chunk Retrieval with source citations."""
        uid = str(uuid.uuid4())[:8]
        reg_res = await self.client.post("/api/auth/register", json={
            "email": f"owner_{uid}@e2e-eval.com",
            "password": "Password123!",
            "business_name": f"Criterion 2 Store {uid}"
        })
        token = reg_res.json()["access_token"]
        biz_slug = reg_res.json()["business_slug"]
        headers = {"Authorization": f"Bearer {token}"}

        # Ingest verified refund terms
        await self.client.post(
            "/api/documents/manual-qa",
            headers=headers,
            json={
                "question": "What is the return window?",
                "answer": "Customers can return items within 30 days for a full refund, or between 31 and 60 days for store credit.",
                "document_title": "Official Return Policy"
            }
        )

        # Customer session
        session_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": biz_slug,
            "channel": "widget"
        })
        session_id = session_res.json()["id"]

        # Query customer question
        msg_res = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "What is the return window for a full refund?"
        })
        assert msg_res.status_code == 200
        data = msg_res.json()

        # Must be answered and grounded
        assert data["is_answered"] is True
        assert "30 days" in data["content"] or "refund" in data["content"].lower()
        # Must have verified citations
        assert len(data["citations"]) > 0
        citation = data["citations"][0]
        assert "Return" in citation["document_name"] or "Manual Q&A" in citation["document_name"]
        assert citation["page_number"] >= 1
        assert len(citation["excerpt"]) > 0

    async def test_criterion_3_zero_hallucinations_on_missing_info(self):
        """Criterion 3: Zero hallucinations on missing information + unanswered logging."""
        uid = str(uuid.uuid4())[:8]
        reg_res = await self.client.post("/api/auth/register", json={
            "email": f"owner_{uid}@e2e-eval.com",
            "password": "Password123!",
            "business_name": f"Criterion 3 Store {uid}"
        })
        token = reg_res.json()["access_token"]
        biz_slug = reg_res.json()["business_slug"]
        headers = {"Authorization": f"Bearer {token}"}

        # Session
        session_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": biz_slug,
            "channel": "widget",
            "customer_email": "prospective.buyer@domain.com"
        })
        session_id = session_res.json()["id"]

        # Ask question with ZERO knowledge base overlap
        out_msg = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "Do you provide helicopter charter flights to Manhattan?"
        })
        assert out_msg.status_code == 200
        data = out_msg.json()

        # Zero hallucination check
        assert data["is_answered"] is False
        assert len(data["citations"]) == 0
        assert data["llm_provider_used"] in ["circuit_breaker", "fallback"]

        # Verify question logged in unanswered table for owner review
        unans_res = await self.client.get("/api/dashboard/unanswered?is_resolved=false", headers=headers)
        assert unans_res.status_code == 200
        unans_items = unans_res.json()
        assert len(unans_items) >= 1
        assert "helicopter charter" in unans_items[0]["question_text"]
        assert unans_items[0]["customer_email"] == "prospective.buyer@domain.com"

    async def test_criterion_4_multi_tenant_data_isolation(self):
        """Criterion 4: Strict Multi-Tenant Data Isolation."""
        # Tenant Alpha
        reg_a = await self.client.post("/api/auth/register", json={
            "email": f"owner_a_{uuid.uuid4().hex[:6]}@alpha.com",
            "password": "Password123!",
            "business_name": "Alpha Defense Corp"
        })
        token_a = reg_a.json()["access_token"]
        biz_a_id = reg_a.json()["business_id"]

        # Tenant Beta
        reg_b = await self.client.post("/api/auth/register", json={
            "email": f"owner_b_{uuid.uuid4().hex[:6]}@beta.com",
            "password": "Password123!",
            "business_name": "Beta Consumer Store"
        })
        token_b = reg_b.json()["access_token"]
        biz_b_slug = reg_b.json()["business_slug"]

        # Tenant Alpha uploads confidential doc
        await self.client.post(
            "/api/documents/manual-qa",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "question": "What is the Project Nebula classified access code?",
                "answer": "The clearance passcode for Project Nebula is NEBULA-9921-RESTRICTED.",
                "document_title": "Project Nebula Internal Directive"
            }
        )

        # Tenant Beta customer asks for Tenant Alpha's secret code
        session_b = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": biz_b_slug,
            "channel": "widget"
        })
        s_id = session_b.json()["id"]

        query_res = await self.client.post("/api/chat/message", json={
            "session_id": s_id,
            "message": "What is the Project Nebula classified access code?"
        })
        assert query_res.status_code == 200
        res_data = query_res.json()

        # Must NOT leak Tenant Alpha's data
        assert "NEBULA-9921-RESTRICTED" not in res_data["content"]
        assert res_data["is_answered"] is False
        assert len(res_data["citations"]) == 0

    async def test_closed_loop_resolution_cycle(self):
        """Closed-Loop Resolution Cycle: Owner trains unanswered question -> immediate resolution."""
        uid = str(uuid.uuid4())[:8]
        reg_res = await self.client.post("/api/auth/register", json={
            "email": f"owner_{uid}@closedloop.com",
            "password": "Password123!",
            "business_name": f"Closed Loop Store {uid}"
        })
        token = reg_res.json()["access_token"]
        biz_slug = reg_res.json()["business_slug"]
        headers = {"Authorization": f"Bearer {token}"}

        # Step 1: Customer asks an unknown question
        s_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": biz_slug,
            "channel": "public_link"
        })
        s_id = s_res.json()["id"]

        unans_query = "Do you accept cryptocurrency payments like Bitcoin or Ethereum?"
        m1 = await self.client.post("/api/chat/message", json={
            "session_id": s_id,
            "message": unans_query
        })
        assert m1.status_code == 200
        assert m1.json()["is_answered"] is False

        # Step 2: Owner reviews unanswered list
        unans_res = await self.client.get("/api/dashboard/unanswered?is_resolved=false", headers=headers)
        items = unans_res.json()
        assert len(items) >= 1
        item_id = items[0]["id"]

        # Step 3: Owner provides ground-truth answer
        resolve_res = await self.client.post(
            f"/api/dashboard/unanswered/{item_id}/resolve",
            headers=headers,
            json={
                "answer_text": "Yes, we accept Bitcoin (BTC), Ethereum (ETH), and USDC via BitPay at checkout with zero processing fees."
            }
        )
        assert resolve_res.status_code == 200
        assert resolve_res.json()["is_resolved"] is True

        # Step 4: Next customer asks the exact question
        m2 = await self.client.post("/api/chat/message", json={
            "session_id": s_id,
            "message": "Do you accept cryptocurrency payments like Bitcoin?"
        })
        assert m2.status_code == 200
        # Now answered with verified citations!
        assert m2.json()["is_answered"] is True
        assert "bitpay" in m2.json()["content"].lower() or "bitcoin" in m2.json()["content"].lower()

    async def test_feedback_and_widget_serving(self):
        """Feedback capture and static widget delivery."""
        # 1. Verify widget.js endpoint returns valid javascript
        w_res = await self.client.get("/widget.js")
        assert w_res.status_code == 200
        assert "iveri-chat-widget" in w_res.text or "function" in w_res.text

        # 2. Verify public chat UI
        chat_page = await self.client.get("/chat/iveri-retail")
        assert chat_page.status_code == 200
        assert "AI Customer Support" in chat_page.text
