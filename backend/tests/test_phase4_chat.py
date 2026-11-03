import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db
from app.services.rag_engine import rag_engine

class TestPhase4Chat(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.transport = ASGITransport(app=app)
        self.client = AsyncClient(transport=self.transport, base_url="http://test")

        # Create a test business
        reg_payload = {
            "business_name": "Zenith Cloud Hosting",
            "email": "contact@zenithcloud.com",
            "password": "Password123!",
            "role": "owner"
        }
        res = await self.client.post("/api/auth/register", json=reg_payload)
        if res.status_code == 201:
            data = res.json()
            self.slug = data["business_slug"]
            self.biz_id = data["business_id"]
        else:
            # Login if existing
            login_res = await self.client.post("/api/auth/login", json={
                "email": "contact@zenithcloud.com",
                "password": "Password123!"
            })
            data = login_res.json()
            self.slug = data["business_slug"]
            self.biz_id = data["business_id"]

        # Index policy document into knowledge base
        await rag_engine.index_document_chunks(self.biz_id, [
            {
                "id": "zenith-sla-1",
                "content": (
                    "SERVICE LEVEL AGREEMENT (SLA):\n"
                    "We guarantee 99.95% uptime for all cloud servers.\n"
                    "If uptime falls below 99.95%, customers receive a 25% credit on their monthly bill.\n"
                    "Automated backups run every 24 hours at midnight UTC."
                ),
                "metadata": {
                    "document_name": "Zenith_SLA_2026.pdf",
                    "page_number": 1,
                    "document_id": "doc-sla-1",
                    "business_id": self.biz_id
                }
            }
        ])

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_01_create_session(self):
        # Happy Path
        res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": self.slug,
            "channel": "public_link"
        })
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIn("id", data)
        self.assertEqual(data["business_slug"], self.slug)

        # Black-Box Error Path: Non-existent slug
        err_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": "non-existent-business-xyz-999",
            "channel": "public_link"
        })
        self.assertEqual(err_res.status_code, 404)
        print("\n[PASS] CHAT-01: Session creation and 404 handling passed.")

    async def test_02_send_message_grounded_answer(self):
        # Create session
        s_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": self.slug,
            "channel": "public_link"
        })
        session_id = s_res.json()["id"]

        # Send grounded inquiry
        m_res = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "What is your uptime guarantee under the SLA?"
        })
        self.assertEqual(m_res.status_code, 200)
        data = m_res.json()
        self.assertTrue(data["is_answered"])
        self.assertIn("99.95%", data["content"])
        self.assertTrue(len(data["citations"]) > 0)
        self.assertEqual(data["citations"][0]["document_name"], "Zenith_SLA_2026.pdf")
        print(f"[PASS] CHAT-02: Grounded customer chat message answered with citation: {data['citations'][0]['document_name']}.")

    async def test_03_unknown_question_and_lead_capture(self):
        # Create session
        s_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": self.slug,
            "channel": "public_link"
        })
        session_id = s_res.json()["id"]

        # Ask out-of-domain question
        m_res = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "Do you offer wedding photography packages?"
        })
        self.assertEqual(m_res.status_code, 200)
        data = m_res.json()
        self.assertFalse(data["is_answered"])
        self.assertEqual(len(data["citations"]), 0)

        # Capture customer email lead on unknown question
        lead_res = await self.client.post(f"/api/chat/session/{session_id}/lead", json={
            "email": "customer@example.com"
        })
        self.assertEqual(lead_res.status_code, 200)
        self.assertEqual(lead_res.json()["status"], "success")
        print("[PASS] CHAT-03: Unknown question logged and lead capture form submitted.")

    async def test_04_message_thumbs_feedback(self):
        # Create session and message
        s_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": self.slug,
            "channel": "widget"
        })
        session_id = s_res.json()["id"]

        m_res = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "How often do automated backups run?"
        })
        msg_id = m_res.json()["id"]

        # Submit Thumbs Down feedback
        fb_res = await self.client.post(f"/api/chat/message/{msg_id}/feedback", json={
            "feedback": "down"
        })
        self.assertEqual(fb_res.status_code, 200)
        self.assertEqual(fb_res.json()["feedback"], "down")
        print("[PASS] CHAT-04: Thumbs down feedback recorded on message.")

    async def test_05_session_history_and_widget_script(self):
        s_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": self.slug,
            "channel": "widget"
        })
        session_id = s_res.json()["id"]

        await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "Hello!"
        })

        hist_res = await self.client.get(f"/api/chat/session/{session_id}/history")
        self.assertEqual(hist_res.status_code, 200)
        history = hist_res.json()
        self.assertEqual(len(history), 2)  # User + Assistant

        # Verify Widget Script endpoint
        widget_res = await self.client.get("/widget.js")
        self.assertEqual(widget_res.status_code, 200)
        self.assertIn("application/javascript", widget_res.headers.get("content-type", ""))
        print("[PASS] CHAT-05: Chat history transcript and widget.js static serving verified.")

    async def test_06_citation_ranking_inflections_and_deduplication(self):
        # Ingest multi-chunk policy mimicking coffee store guide
        doc_chunks = [
            {
                "id": "chunk-p1-s4",
                "content": "4. Returns and Refunds\nCoffee beans: Because coffee is perishable, we do not accept returns of opened bags. Unopened bags can be returned within 7 days of delivery. Equipment can be returned within 15 days.",
                "metadata": {"document_name": "BrewNest_Customer_Help_Guide.pdf", "page_number": 1, "chunk_index": 2}
            },
            {
                "id": "chunk-p2-shipping",
                "content": "Return shipping: For all other returns, the customer pays a return shipping fee of Rs. 100. Refunds are processed within 5 to 7 business days after we receive the returned item, to the original payment method.",
                "metadata": {"document_name": "BrewNest_Customer_Help_Guide.pdf", "page_number": 2, "chunk_index": 4}
            },
            {
                "id": "chunk-p2-product-info",
                "content": "9. Product Information\nAll BrewNest coffee is vegan and gluten-free. For best flavor, use beans within 60 days of the roast date printed on the bag.",
                "metadata": {"document_name": "BrewNest_Customer_Help_Guide.pdf", "page_number": 2, "chunk_index": 7}
            }
        ]
        await rag_engine.index_document_chunks(self.biz_id, doc_chunks)

        s_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": self.slug,
            "channel": "widget"
        })
        session_id = s_res.json()["id"]

        # User asks with typo and inflection stems ("can i return the cofee bag")
        m_res = await self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "can i return the cofee bag"
        })
        self.assertEqual(m_res.status_code, 200)
        data = m_res.json()
        citations = data.get("citations", [])
        self.assertTrue(len(citations) >= 1)

        # Primary citation must be Page 1 (Section 4: Returns and Refunds)
        top_cite = citations[0]
        self.assertEqual(top_cite["page_number"], 1)
        self.assertTrue("return" in top_cite["excerpt"].lower())
        self.assertTrue("unopened bags can be returned" in top_cite["excerpt"].lower())

        # If second citation exists, it must be the return shipping on Page 2, NEVER Product Information (vegan bag)
        if len(citations) > 1:
            second_cite = citations[1]
            self.assertEqual(second_cite["page_number"], 2)
            self.assertIn("Return shipping", second_cite["excerpt"])
            self.assertNotIn("vegan", second_cite["excerpt"].lower())

        print("[PASS] CHAT-06: Citation ranking prioritized Page 1 direct answer and excluded irrelevant product info chunk.")

if __name__ == "__main__":
    unittest.main()
