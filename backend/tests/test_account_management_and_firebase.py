import os
import sys
import uuid
import unittest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.future import select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database import AsyncSessionLocal, init_db
from app.models.business import Business
from app.models.user import User
from app.models.document import Document
from app.models.ticket import Ticket
from app.utils.security import create_access_token, hash_password
from app.services.vector_store import vector_store_service
from app.services.bm25_store import bm25_store_service


class TestAccountManagementAndFirebase(unittest.IsolatedAsyncioTestCase):
    """Verifies Account renaming, Password change, Permanent deletion, and Firebase Google auth."""

    async def asyncSetUp(self):
        await init_db()
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.suffix = os.urandom(3).hex()

        async with AsyncSessionLocal() as db:
            self.biz = Business(
                name=f"Original Biz {self.suffix}",
                slug=f"orig-biz-{self.suffix}",
                welcome_message="Hello!",
                fallback_message="Sorry."
            )
            db.add(self.biz)
            await db.flush()

            self.owner = User(
                business_id=self.biz.id,
                email=f"owner_{self.suffix}@testbiz.example",
                password_hash=hash_password("OldPassword123"),
                role="owner",
                auth_provider="local"
            )
            db.add(self.owner)
            await db.commit()
            await db.refresh(self.biz)
            await db.refresh(self.owner)

            self.biz_id = self.biz.id
            self.owner_id = self.owner.id
            self.owner_email = self.owner.email
            self.token = create_access_token({
                "sub": self.owner_id,
                "email": self.owner_email,
                "role": "owner",
                "business_id": self.biz_id
            })
            self.headers = {"Authorization": f"Bearer {self.token}"}

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_01_rename_account(self):
        """Owner can successfully rename their business account."""
        new_name = f"Renamed Global Healthcare {self.suffix}"
        res = await self.client.put(
            "/api/auth/rename-account",
            headers=self.headers,
            json={"business_name": new_name}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["business_name"], new_name)

        # Verify DB updated
        async with AsyncSessionLocal() as db:
            biz = (await db.execute(select(Business).where(Business.id == self.biz_id))).scalar_one()
            self.assertEqual(biz.name, new_name)

    async def test_02_change_password_and_login_with_new_password(self):
        """User can change password with correct current password, and log in with new password."""
        # 1. Reject if current password is wrong
        res_fail = await self.client.put(
            "/api/auth/change-password",
            headers=self.headers,
            json={"current_password": "WrongPassword999", "new_password": "BrandNewPassword456"}
        )
        self.assertEqual(res_fail.status_code, 400)
        self.assertIn("Current password is incorrect", res_fail.json()["detail"])

        # 2. Reject if new password does not meet complexity (must have letters and numbers)
        res_weak = await self.client.put(
            "/api/auth/change-password",
            headers=self.headers,
            json={"current_password": "OldPassword123", "new_password": "short"}
        )
        self.assertEqual(res_weak.status_code, 422)

        # 3. Successful password change
        res_ok = await self.client.put(
            "/api/auth/change-password",
            headers=self.headers,
            json={"current_password": "OldPassword123", "new_password": "BrandNewPassword456"}
        )
        self.assertEqual(res_ok.status_code, 200)

        # 4. Sign in with old password must fail
        login_old = await self.client.post(
            "/api/auth/login",
            json={"email": self.owner_email, "password": "OldPassword123"}
        )
        self.assertEqual(login_old.status_code, 401)

        # 5. Sign in with new password must succeed
        login_new = await self.client.post(
            "/api/auth/login",
            json={"email": self.owner_email, "password": "BrandNewPassword456"}
        )
        self.assertEqual(login_new.status_code, 200)
        self.assertIn("access_token", login_new.json())

    async def test_03_firebase_google_login_auto_provisions_and_signs_in(self):
        """Firebase Google Auth auto-provisions a new business workspace and returns access token."""
        google_uid = f"g_uid_{uuid.uuid4().hex[:8]}"
        google_email = f"google_user_{self.suffix}@gmail.com"
        # Test token bypass format: test_fb_token_<uid>:<email>:<name>
        fb_token = f"test_fb_token_{google_uid}:{google_email}:Apex Dentistry Google"

        res = await self.client.post(
            "/api/auth/firebase-login",
            json={"id_token": fb_token, "business_name": "Apex Dentistry Google"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["role"], "owner")
        self.assertEqual(data["business_name"], "Apex Dentistry Google")

        # Calling again with same token logs into existing user and workspace
        res_existing = await self.client.post(
            "/api/auth/firebase-login",
            json={"id_token": fb_token}
        )
        self.assertEqual(res_existing.status_code, 200)
        data_existing = res_existing.json()
        self.assertEqual(data_existing["business_id"], data["business_id"])
        self.assertEqual(data_existing["user_id"], data["user_id"])

    async def test_04_delete_account_permanent(self):
        """Permanent account deletion requires confirmation phrase and deletes business, users, documents, and vector index."""
        # Add a test document and ticket to verify cascade
        async with AsyncSessionLocal() as db:
            doc = Document(
                business_id=self.biz_id,
                file_name="patient_guide.pdf",
                storage_path="/uploads/patient_guide.pdf",
                file_type="pdf",
                file_size_bytes=1024,
                status="INDEXED",
                chunk_count=2
            )
            tick = Ticket(
                ticket_number=f"TICK-{self.suffix.upper()}",
                business_id=self.biz_id,
                channel="widget",
                subject="Appointment query",
                description="Routine cleaning appointment reschedule request",
                status="open"
            )
            db.add(doc)
            db.add(tick)
            await db.commit()

        # Seed in-memory BM25 index
        bm25_store_service.add_chunks(self.biz_id, [{"id": "c1", "content": "dental care test", "metadata": {}}])
        self.assertIn(self.biz_id, bm25_store_service._corpus)

        # 1. Reject if phrase does not match
        res_bad = await self.client.request(
            "DELETE",
            "/api/auth/delete-account",
            headers=self.headers,
            json={"confirmation_phrase": "WRONG PHRASE"}
        )
        self.assertEqual(res_bad.status_code, 400)

        # 2. Accept with exact confirmation phrase
        res_ok = await self.client.request(
            "DELETE",
            "/api/auth/delete-account",
            headers=self.headers,
            json={"confirmation_phrase": "DELETE MY ACCOUNT"}
        )
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.json()["status"], "deleted")

        # 3. Verify BM25 index pruned
        self.assertNotIn(self.biz_id, bm25_store_service._corpus)

        # 4. Verify Business, User, Document, and Ticket completely erased from SQLite
        async with AsyncSessionLocal() as db:
            biz_check = (await db.execute(select(Business).where(Business.id == self.biz_id))).scalar_one_or_none()
            user_check = (await db.execute(select(User).where(User.id == self.owner_id))).scalar_one_or_none()
            doc_check = (await db.execute(select(Document).where(Document.business_id == self.biz_id))).scalar_one_or_none()
            tick_check = (await db.execute(select(Ticket).where(Ticket.business_id == self.biz_id))).scalar_one_or_none()

            self.assertIsNone(biz_check, "Business must be permanently deleted.")
            self.assertIsNone(user_check, "Associated user must be deleted.")
            self.assertIsNone(doc_check, "Associated documents must be cascade deleted.")
            self.assertIsNone(tick_check, "Associated tickets must be cascade deleted.")

    async def test_05_firebase_duplicate_email_and_case_insensitive_linking(self):
        """Verifies that signing in with Google Firebase when an account already exists (even with differing case)

        links the user smoothly without UniqueViolationError or duplicate key errors.
        """
        # 1. Existing local user with uppercase/mixed email
        test_email = f"GoogleUser_{self.suffix}@example.com"
        async with AsyncSessionLocal() as db:
            biz = Business(name=f"Existing Biz {self.suffix}", slug=f"exist-biz-{self.suffix}")
            db.add(biz)
            await db.flush()
            existing_user = User(
                business_id=biz.id,
                email=test_email.lower(),
                password_hash=hash_password("Pass123!"),
                role="owner"
            )
            db.add(existing_user)
            await db.commit()

        # 2. Firebase login token with mixed case email
        token_str = f"test_fb_token:google_uid_{self.suffix}:{test_email}:Google Brand"
        res = await self.client.post(
            "/api/auth/firebase-login",
            json={"id_token": token_str, "business_name": "New Google Name"}
        )
        self.assertEqual(res.status_code, 200, f"Google login must succeed without UniqueViolationError: {res.text}")
        data = res.json()
        self.assertTrue(data["access_token"])
        self.assertEqual(data["business_id"], biz.id)

        # 3. Clean up
        async with AsyncSessionLocal() as db:
            await db.execute(User.__table__.delete().where(User.business_id == biz.id))
            await db.execute(Business.__table__.delete().where(Business.id == biz.id))
            await db.commit()

    def test_06_pwa_native_prompt_contracts(self):
        """Verifies that index.html handles native deferredPrompt for direct 1-tap Chrome install."""
        html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "static", "index.html"))
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertIn("deferredPrompt.prompt()", html)
        self.assertIn("installPWA", html)
        self.assertIn("isFirebaseSyncing", html)
        self.assertIn("window.firebaseAuth.signOut()", html)
        self.assertIn("window.firebaseSignOut", html)
        self.assertIn("prompt: 'select_account'", html)
        self.assertNotIn("onAuthStateChanged(auth, async (user) => {", html)
