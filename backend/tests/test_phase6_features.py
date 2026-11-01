import io
import os
import sys
import unittest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database import init_db

class TestPhase6Features(unittest.IsolatedAsyncioTestCase):
    """Integration test suite for Phase 6 features:
    - Direct Power BI / Excel CSV export with query token & dev fallback
    - Local avatar DP upload and static retrieval
    - Dedicated chatbot custom prompt persistence and strict grounding
    - Chat history session sentiment alignment with downvote / negative messages
    - Chat history topic and sentiment filtering for chart drill-downs
    """

    async def asyncSetUp(self):
        await init_db()
        self.transport = ASGITransport(app=app)
        self.client = AsyncClient(transport=self.transport, base_url="http://test")

        # Register dedicated store for Phase 6 test
        import uuid
        self.uid = str(uuid.uuid4())[:8]
        self.email = f"owner_{self.uid}@teststore.com"
        self.password = "SecurePass123!"
        reg = await self.client.post("/api/auth/register", json={
            "email": self.email,
            "password": self.password,
            "business_name": f"Phase6 Store {self.uid}",
            "role": "owner"
        })
        self.token = reg.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.slug = reg.json()["business_slug"]

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_01_powerbi_export_with_token_and_dev_mode(self):
        # 1. Direct browser URL access without Auth header (development fallback)
        res_no_auth = await self.client.get("/api/dashboard/export/powerbi?format=csv")
        self.assertEqual(res_no_auth.status_code, 200)
        self.assertIn("SessionID,Timestamp", res_no_auth.text)

        # 2. Access with token in URL query parameter
        res_token = await self.client.get(f"/api/dashboard/export/powerbi?format=csv&token={self.token}")
        self.assertEqual(res_token.status_code, 200)
        self.assertIn("SessionID,Timestamp", res_token.text)

    async def test_02_avatar_upload_and_static_serving(self):
        # Create a tiny 1x1 valid PNG image
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00"
            b"\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        files = {"file": ("avatar.png", io.BytesIO(png_bytes), "image/png")}
        res = await self.client.post("/api/business/avatar/upload", headers=self.headers, files=files)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("avatar_url", data)
        avatar_url = data["avatar_url"]

        # Fetch uploaded avatar via public GET endpoint
        res_img = await self.client.get(avatar_url)
        self.assertEqual(res_img.status_code, 200)
        self.assertEqual(res_img.content, png_bytes)

    async def test_03_custom_prompt_settings_persistence(self):
        custom_instructions = "You are a specialized coffee sommelier. Recommend medium roast always."
        put_res = await self.client.put("/api/business/settings", headers=self.headers, json={
            "custom_prompt": custom_instructions,
            "name": f"Phase6 Store {self.uid}"
        })
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()["custom_prompt"], custom_instructions)

        # Verify public business info exposes custom prompt for client hydration
        pub_res = await self.client.get(f"/api/public/business/{self.slug}")
        self.assertEqual(pub_res.status_code, 200)
        self.assertEqual(pub_res.json()["custom_prompt"], custom_instructions)

    async def test_04_session_sentiment_alignment_with_downvote(self):
        # Create a customer session
        sess_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": self.slug,
            "customer_email": "frustrated_user@domain.com"
        })
        self.assertIn(sess_res.status_code, (200, 201))
        session_id = sess_res.json().get("session_id") or sess_res.json()["id"]

        # Send a message
        msg_res = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "The product broke on first use, this is terrible."
        })
        self.assertEqual(msg_res.status_code, 200)
        msg_id = msg_res.json().get("message_id") or msg_res.json()["id"]

        # Downvote the message
        fb_res = await self.client.post(f"/api/chat/message/{msg_id}/feedback", json={"feedback": "down"})
        self.assertEqual(fb_res.status_code, 200)

        # Inspect chat history: Session must be marked as 'negative'
        chats_res = await self.client.get("/api/dashboard/chats?search=frustrated_user", headers=self.headers)
        self.assertEqual(chats_res.status_code, 200)
        sessions = chats_res.json()
        self.assertTrue(len(sessions) >= 1)
        target_session = next(s for s in sessions if s["session_id"] == session_id)
        self.assertEqual(target_session["sentiment"], "negative")

        # Test drill-down filter by sentiment=negative
        filtered_res = await self.client.get("/api/dashboard/chats?sentiment=negative", headers=self.headers)
        self.assertEqual(filtered_res.status_code, 200)
        filtered_ids = [s["session_id"] for s in filtered_res.json()]
        self.assertIn(session_id, filtered_ids)

    async def test_05_session_token_validation(self):
        res = await self.client.get("/api/auth/session/validate", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["email"], self.email)
        self.assertEqual(data["business_slug"], self.slug)
