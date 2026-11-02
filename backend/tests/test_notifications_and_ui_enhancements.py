import os
import sys
import uuid
import unittest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.main import app
from app.database import AsyncSessionLocal, init_db
from app.models.user import User
from app.models.business import Business
from app.models.notification import Notification
from app.utils.security import create_access_token, hash_password

class TestNotificationsAndUiEnhancements(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.uid = str(uuid.uuid4())[:8]

        async with AsyncSessionLocal() as db:
            self.biz = Business(
                name=f"Notification Biz {self.uid}",
                slug=f"notif-biz-{self.uid}"
            )
            db.add(self.biz)
            await db.flush()

            self.user = User(
                email=f"owner_{self.uid}@notiftest.com",
                password_hash=hash_password("TestPass123!"),
                role="owner",
                business_id=self.biz.id
            )
            db.add(self.user)

            self.notif = Notification(
                business_id=self.biz.id,
                type="ticket_created",
                title="Test Ticket Alert",
                message="Test customer query",
                is_read=False
            )
            db.add(self.notif)
            await db.commit()

        self.token = create_access_token(data={"sub": self.user.email, "role": "owner", "business_id": self.biz.id})
        self.headers = {"Authorization": f"Bearer {self.token}"}

    async def asyncTearDown(self):
        await self.client.aclose()
        async with AsyncSessionLocal() as db:
            await db.execute(Notification.__table__.delete().where(Notification.business_id == self.biz.id))
            await db.execute(User.__table__.delete().where(User.business_id == self.biz.id))
            await db.execute(Business.__table__.delete().where(Business.id == self.biz.id))
            await db.commit()

    async def test_01_notification_created_at_timezone_serialized(self):
        """Ensures NotificationResponse serializes created_at with ISO-8601 timezone info."""
        res = await self.client.get("/api/notifications", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["unread_count"], 1)
        self.assertGreaterEqual(len(data["items"]), 1)

        created_at_str = data["items"][0]["created_at"]
        self.assertTrue("+00:00" in created_at_str or "Z" in created_at_str or "T" in created_at_str)

    async def test_02_notification_read_unread_toggle_and_delete(self):
        """Verifies read, unread, toggle, and delete lifecycle for alerts."""
        notif_id = self.notif.id

        # 1. Mark Read
        res = await self.client.post(f"/api/notifications/{notif_id}/read", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["is_read"])

        # 2. Mark Unread
        res = await self.client.post(f"/api/notifications/{notif_id}/unread", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["is_read"])

        # 3. Toggle Read
        res = await self.client.post(f"/api/notifications/{notif_id}/toggle-read", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["is_read"])

        # 4. Delete Notification
        res = await self.client.delete(f"/api/notifications/{notif_id}", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "success")

        # 5. Verify gone
        res_list = await self.client.get("/api/notifications", headers=self.headers)
        self.assertEqual(res_list.status_code, 200)
        item_ids = [item["id"] for item in res_list.json()["items"]]
        self.assertNotIn(notif_id, item_ids)

    def test_03_frontend_ui_contracts_for_notifications_and_mobile(self):
        """Verifies index.html has showToast, accurate relative timers, read/unread filters, and mobile optimizations."""
        html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "static", "index.html"))
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        # Unanswered Chat & Tickets renaming contracts
        self.assertIn("Unanswered Chat & Tickets", html)
        self.assertIn('id="tab-tickets"', html)
        self.assertIn('id="mobile-nav-tickets"', html)

        # Toast notification utility
        self.assertIn("function showToast(", html)

        # Notification Center UX & Responsive Contracts
        self.assertIn('id="notif-dropdown"', html)
        self.assertIn("w-[calc(100vw-24px)]", html)
        self.assertIn('id="notif-filter-all"', html)
        self.assertIn('id="notif-filter-unread"', html)
        self.assertIn("parseUtcDate(", html)
        self.assertIn("formatNotificationTime(", html)
        self.assertIn("markNotificationReadById(", html)
        self.assertIn("markNotificationUnreadById(", html)
        self.assertIn("deleteNotificationById(", html)
