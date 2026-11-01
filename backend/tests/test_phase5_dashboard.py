import os
import sys
import uuid
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db

class TestPhase5Dashboard(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.transport = ASGITransport(app=app)
        self.client = AsyncClient(transport=self.transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def _create_test_business_with_doc(self):
        unique_id = str(uuid.uuid4())[:8]
        email = f"owner_{unique_id}@dashboard-test.com"
        reg_res = await self.client.post("/api/auth/register", json={
            "email": email,
            "password": "SecurePassword123!",
            "business_name": f"Apex Electronics {unique_id}"
        })
        assert reg_res.status_code == 201
        data = reg_res.json()
        token = data["access_token"]
        biz_slug = data["business_slug"]
        headers = {"Authorization": f"Bearer {token}"}

        # Ingest warranty document
        doc_res = await self.client.post(
            "/api/documents/manual-qa",
            headers=headers,
            json={
                "question": "What is the warranty period for laptops?",
                "answer": "All laptops purchased from Apex Electronics include a 2-year manufacturer warranty covering hardware defects.",
                "document_title": "Apex Electronics Warranty Policy"
            }
        )
        assert doc_res.status_code == 201
        return headers, biz_slug, token

    async def test_01_dashboard_stats_and_metrics(self):
        headers, biz_slug, _ = await self._create_test_business_with_doc()

        # Create a chat session and send questions
        session_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": biz_slug,
            "channel": "widget"
        })
        assert session_res.status_code == 201
        session_id = session_res.json()["id"]

        # Grounded query (Answered)
        msg1 = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "What is the warranty period for laptops?"
        })
        assert msg1.status_code == 200
        assert msg1.json()["is_answered"] is True
        msg1_id = msg1.json()["id"]

        # Vote thumbs up on msg1
        await self.client.post(f"/api/chat/message/{msg1_id}/feedback", json={"feedback": "up"})

        # Out of domain query (Unanswered)
        msg2 = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "Do you sell international airline flight tickets?"
        })
        assert msg2.status_code == 200
        assert msg2.json()["is_answered"] is False
        msg2_id = msg2.json()["id"]

        # Vote thumbs down on msg2
        await self.client.post(f"/api/chat/message/{msg2_id}/feedback", json={"feedback": "down"})

        # Fetch Dashboard Stats
        stats_res = await self.client.get("/api/dashboard/stats", headers=headers)
        assert stats_res.status_code == 200
        data = stats_res.json()

        assert data["total_chats"] >= 1
        assert data["total_questions"] >= 2
        assert data["answered_count"] >= 1
        assert data["unanswered_count"] >= 1
        assert data["thumbs_up_count"] >= 1
        assert data["thumbs_down_count"] >= 1
        assert data["total_documents"] >= 1
        assert data["resolution_rate"] > 0

    async def test_02_unanswered_questions_closed_loop_resolution(self):
        headers, biz_slug, _ = await self._create_test_business_with_doc()

        # Create session and ask unanswered question
        session_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": biz_slug,
            "channel": "widget"
        })
        session_id = session_res.json()["id"]

        out_msg = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "Do you sell international airline flight tickets?"
        })
        assert out_msg.status_code == 200
        assert out_msg.json()["is_answered"] is False

        # List unanswered questions
        unans_res = await self.client.get("/api/dashboard/unanswered?is_resolved=false", headers=headers)
        assert unans_res.status_code == 200
        items = unans_res.json()
        assert len(items) >= 1
        target_item = next((i for i in items if "flight" in i["question_text"].lower()), items[0])
        unanswered_id = target_item["id"]

        # Resolve the question by providing authoritative business knowledge
        resolve_res = await self.client.post(
            f"/api/dashboard/unanswered/{unanswered_id}/resolve",
            headers=headers,
            json={
                "answer_text": "We do not sell flight tickets; however, our travel desk partners provide flight booking assistance for corporate accounts."
            }
        )
        assert resolve_res.status_code == 200
        res_data = resolve_res.json()
        assert res_data["status"] == "success"
        assert res_data["is_resolved"] is True
        assert res_data["chunks_created"] == 1

        # Ask the question again in a customer chat session -> Should now be answered from the newly trained knowledge!
        followup_msg = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "Do you sell international airline flight tickets?"
        })
        assert followup_msg.status_code == 200
        f_data = followup_msg.json()
        assert f_data["is_answered"] is True
        assert "flight" in f_data["content"].lower() or "travel desk" in f_data["content"].lower()

    async def test_03_chat_history_and_downvote_filtering(self):
        headers, biz_slug, _ = await self._create_test_business_with_doc()

        session_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": biz_slug,
            "channel": "public_link"
        })
        session_id = session_res.json()["id"]

        msg = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "What is the warranty period for laptops?"
        })
        msg_id = msg.json()["id"]
        # Cast downvote
        await self.client.post(f"/api/chat/message/{msg_id}/feedback", json={"feedback": "down"})

        # Fetch all chats
        all_chats_res = await self.client.get("/api/dashboard/chats", headers=headers)
        assert all_chats_res.status_code == 200
        all_chats = all_chats_res.json()
        assert len(all_chats) >= 1

        # Fetch only downvoted chats
        down_chats_res = await self.client.get("/api/dashboard/chats?feedback=down", headers=headers)
        assert down_chats_res.status_code == 200
        down_chats = down_chats_res.json()
        assert len(down_chats) >= 1
        assert any(s["has_downvote"] is True for s in down_chats)

    async def test_04_playground_query_diagnostics(self):
        headers, _, _ = await self._create_test_business_with_doc()

        # Test playground with grounded query
        pg_res = await self.client.post(
            "/api/dashboard/playground",
            headers=headers,
            json={"query": "What is the warranty period for laptops?"}
        )
        assert pg_res.status_code == 200
        data = pg_res.json()
        assert data["circuit_breaker_passed"] is True
        assert len(data["retrieved_chunks"]) > 0
        assert "2-year" in data["generated_answer"] or "warranty" in data["generated_answer"].lower()
        assert data["latency_ms"] >= 0

    async def test_05_static_routes_served(self):
        # Dashboard HTML
        dash_res = await self.client.get("/dashboard")
        assert dash_res.status_code == 200
        assert "Owner Portal" in dash_res.text

        # Customer Chat HTML
        chat_res = await self.client.get("/chat/test-store")
        assert chat_res.status_code == 200
        assert "AI Customer Support" in chat_res.text
