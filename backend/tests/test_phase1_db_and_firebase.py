import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import unittest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db, AsyncSessionLocal, get_database_health
from sqlalchemy import text

class TestPhase1DatabaseAndFirebase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        self.transport = ASGITransport(app=app)
        self.client = AsyncClient(transport=self.transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_01_database_health_telemetry(self):
        """Tests database health status, driver detection, and concurrency mode."""
        health = await get_database_health()
        self.assertEqual(health["status"], "healthy")
        self.assertIn(health["database_type"], ["sqlite", "postgresql"])
        self.assertIn(health["concurrency_mode"], ["wal_journal", "connection_pool"])

        resp = await self.client.get("/api/auth/db-health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")

    async def test_02_concurrent_database_stress(self):
        """Simulates 50 concurrent async database operations to verify zero locking."""
        async def single_worker(worker_id: int):
            async with AsyncSessionLocal() as session:
                res = await session.execute(text("SELECT 1 + :w"), {"w": worker_id})
                val = res.scalar()
                return val == (1 + worker_id)

        tasks = [single_worker(i) for i in range(50)]
        results = await asyncio.gather(*tasks)
        self.assertEqual(len(results), 50)
        self.assertTrue(all(results), "All concurrent queries should succeed without lock exceptions")

    async def test_03_firebase_login_and_auto_provisioning(self):
        """Tests Firebase ID token authentication, workspace auto-provisioning, and token generation."""
        test_fb_token = "test_fb_token_user_99182:founder@enterprise-scale.io:Scale Enterprise"

        # 1. Login with Firebase token (auto-provisions business and user)
        resp = await self.client.post(
            "/api/auth/firebase-login",
            json={
                "id_token": test_fb_token,
                "business_name": "Scale Enterprise Tech"
            }
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["role"], "owner")
        self.assertEqual(data["business_name"], "Scale Enterprise Tech")
        self.assertTrue(len(data["business_slug"]) > 0)

        access_token = data["access_token"]

        # 2. Access protected /api/auth/me with the issued JWT
        me_resp = await self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        self.assertEqual(me_resp.status_code, 200)
        me_data = me_resp.json()
        self.assertEqual(me_data["email"], "founder@enterprise-scale.io")

        # 3. Access protected route directly with the Firebase ID token
        direct_me_resp = await self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {test_fb_token}"}
        )
        self.assertEqual(direct_me_resp.status_code, 200)
        direct_data = direct_me_resp.json()
        self.assertEqual(direct_data["email"], "founder@enterprise-scale.io")

    async def test_04_firebase_invalid_token_rejection(self):
        """Verifies that invalid or malformed Firebase tokens are securely rejected."""
        resp = await self.client.post(
            "/api/auth/firebase-login",
            json={"id_token": "malformed_token_12345"}
        )
        self.assertEqual(resp.status_code, 401)
