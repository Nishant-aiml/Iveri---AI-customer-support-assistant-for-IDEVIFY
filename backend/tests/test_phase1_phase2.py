import asyncio
import os
import sys
import unittest

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db

class TestPhase1AndPhase2(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Initialize database tables
        await init_db()
        self.transport = ASGITransport(app=app)
        self.client = AsyncClient(transport=self.transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_01_health_check(self):
        response = await self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        print("\n[PASS] 01: Health check endpoint passed.")

    async def test_02_register_and_login_owner(self):
        # Register Owner 1
        reg_payload = {
            "business_name": "Maria Boutique Store",
            "email": "maria@boutique.com",
            "password": "Password123!",
            "role": "owner"
        }
        res = await self.client.post("/api/auth/register", json=reg_payload)
        self.assertIn(res.status_code, (201, 400))  # 400 if already created in earlier test run
        
        # Login
        login_payload = {
            "email": "maria@boutique.com",
            "password": "Password123!"
        }
        login_res = await self.client.post("/api/auth/login", json=login_payload)
        self.assertEqual(login_res.status_code, 200)
        data = login_res.json()
        self.assertIn("access_token", data)
        self.assertIn("business_slug", data)
        self.assertIn("share_token", data)
        print(f"[PASS] 02: Registration & JWT Login passed. Slug: {data['business_slug']}")

    async def test_03_business_settings_and_public_link(self):
        # Login
        login_res = await self.client.post("/api/auth/login", json={
            "email": "maria@boutique.com",
            "password": "Password123!"
        })
        token = login_res.json()["access_token"]
        slug = login_res.json()["business_slug"]
        headers = {"Authorization": f"Bearer {token}"}

        # Get Settings
        settings_res = await self.client.get("/api/business/settings", headers=headers)
        self.assertEqual(settings_res.status_code, 200)
        settings_data = settings_res.json()
        self.assertIn("embed_snippet", settings_data)
        self.assertIn("starter_questions", settings_data)

        # Update Settings
        update_res = await self.client.put("/api/business/settings", headers=headers, json={
            "tone": "formal",
            "brand_color": "#10b981",
            "fallback_message": "Our representatives will contact you shortly."
        })
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.json()["tone"], "formal")
        self.assertEqual(update_res.json()["brand_color"], "#10b981")

        # Test Public Endpoint without auth
        public_res = await self.client.get(f"/api/public/business/{slug}")
        self.assertEqual(public_res.status_code, 200)
        public_data = public_res.json()
        self.assertEqual(public_data["brand_color"], "#10b981")
        print("[PASS] 03: Owner settings update and public link resolution passed.")

    async def test_04_manual_qa_knowledge_ingestion(self):
        login_res = await self.client.post("/api/auth/login", json={
            "email": "maria@boutique.com",
            "password": "Password123!"
        })
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Add Manual Q&A to knowledge base
        qa_payload = {
            "question": "What is your return policy for damaged items?",
            "answer": "Damaged items can be returned within 14 days of delivery for a 100% full refund.",
            "category": "Returns"
        }
        res = await self.client.post("/api/documents/manual-qa", headers=headers, json=qa_payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["status"], "INDEXED")
        print("[PASS] 04: Manual Q&A closed-loop ingestion passed.")

    async def test_05_document_upload_and_listing(self):
        login_res = await self.client.post("/api/auth/login", json={
            "email": "maria@boutique.com",
            "password": "Password123!"
        })
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Upload a sample TXT policy document
        sample_doc_content = (
            "SHIPPING POLICY 2026\n\n"
            "We offer standard shipping (3-5 business days) for $5.99.\n"
            "Express shipping (1-2 business days) is available for $14.99.\n"
            "Orders above $50 qualify for free standard delivery across all states."
        )

        files = {
            "file": ("shipping_policy.txt", sample_doc_content.encode("utf-8"), "text/plain")
        }
        upload_res = await self.client.post("/api/documents/upload", headers=headers, files=files)
        self.assertEqual(upload_res.status_code, 202)
        upload_data = upload_res.json()
        self.assertEqual(upload_data["status"], "QUEUED")
        self.assertTrue(upload_data["document_id"])

        # Wait briefly for background ingestion worker
        await asyncio.sleep(2.0)

        # List documents
        docs_res = await self.client.get("/api/documents", headers=headers)
        self.assertEqual(docs_res.status_code, 200)
        docs = docs_res.json()
        self.assertTrue(len(docs) >= 2)  # manual_qa + shipping_policy
        print(f"[PASS] 05: Document upload & background queue ingestion passed. Total docs: {len(docs)}")

    async def test_06_multi_tenant_isolation(self):
        # Register a second business owner
        reg2_payload = {
            "business_name": "Apex Electronics Ltd",
            "email": "owner@apexelectronics.com",
            "password": "Password123!",
            "role": "owner"
        }
        await self.client.post("/api/auth/register", json=reg2_payload)

        login2_res = await self.client.post("/api/auth/login", json={
            "email": "owner@apexelectronics.com",
            "password": "Password123!"
        })
        token2 = login2_res.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        # Ensure Business 2 has 0 documents (does NOT see Maria Boutique's documents)
        docs2_res = await self.client.get("/api/documents", headers=headers2)
        self.assertEqual(docs2_res.status_code, 200)
        docs2 = docs2_res.json()
        self.assertEqual(len(docs2), 0)
        print("[PASS] 06: Multi-tenant isolation verified (Business 2 cannot access Business 1 data).")

if __name__ == "__main__":
    unittest.main()
