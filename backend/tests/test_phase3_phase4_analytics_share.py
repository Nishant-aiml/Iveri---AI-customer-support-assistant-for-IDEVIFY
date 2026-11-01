import unittest
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import AsyncSessionLocal, init_db
from app.models.business import Business
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage
from app.models.unanswered import UnansweredQuestion
from app.utils.security import create_access_token, hash_password
from app.services.sentiment_analyzer import sentiment_analyzer
from app.services.topic_analyzer import topic_analyzer

class TestPhase3Phase4AnalyticsAndShare(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        self.transport = ASGITransport(app=app)
        self.client = AsyncClient(transport=self.transport, base_url="http://test")

        self.business_id = f"biz_test_{uuid.uuid4().hex[:6]}"
        self.user_id = f"user_test_{uuid.uuid4().hex[:6]}"
        self.user_email = f"owner_{uuid.uuid4().hex[:6]}@example.com"
        self.session_id = f"sess_test_{uuid.uuid4().hex[:6]}"
        self.unanswered_id = f"unans_test_{uuid.uuid4().hex[:6]}"

        async with AsyncSessionLocal() as db:
            biz = Business(
                id=self.business_id,
                name="Analytics Test Corp",
                slug=f"analytics-test-{uuid.uuid4().hex[:6]}",
                share_token=uuid.uuid4().hex,
                avatar_url="https://example.com/avatar.png",
                brand_color="#4F46E5"
            )
            db.add(biz)

            user = User(
                id=self.user_id,
                business_id=self.business_id,
                email=self.user_email,
                password_hash=hash_password("password123"),
                role="owner"
            )
            db.add(user)

            chat_sess = ChatSession(
                id=self.session_id,
                business_id=self.business_id,
                channel="widget",
                customer_email="buyer@test.com",
                sentiment="positive",
                primary_topic="pricing"
            )
            db.add(chat_sess)

            msg1 = ChatMessage(
                session_id=self.session_id,
                sender="customer",
                content="How much does the Highland Roast 1kg cost?",
                sentiment="neutral",
                topic="pricing",
                is_answered=True
            )
            msg2 = ChatMessage(
                session_id=self.session_id,
                sender="assistant",
                content="Highland Roast (medium) 1 kg is Rs. 1,600.",
                sentiment="neutral",
                topic="pricing",
                is_answered=True,
                latency_ms=45,
                llm_provider_used="extractive_synthesis"
            )
            msg3 = ChatMessage(
                session_id=self.session_id,
                sender="customer",
                content="Thank you, that is amazing!",
                sentiment="positive",
                topic="general",
                feedback="up",
                is_answered=True
            )
            db.add_all([msg1, msg2, msg3])

            unans = UnansweredQuestion(
                id=self.unanswered_id,
                business_id=self.business_id,
                session_id=self.session_id,
                question_text="Do you ship to Antarctica?",
                customer_email="buyer@test.com",
                is_resolved=False
            )
            db.add(unans)
            await db.commit()

        self.token = create_access_token({"sub": self.user_id, "role": "owner", "business_id": self.business_id})
        self.headers = {"Authorization": f"Bearer {self.token}"}

    async def asyncTearDown(self):
        await self.client.aclose()
        async with AsyncSessionLocal() as db:
            biz = (await db.execute(Business.__table__.select().where(Business.id == self.business_id))).first()
            if biz:
                u_del = User.__table__.delete().where(User.business_id == self.business_id)
                await db.execute(u_del)
                b_del = Business.__table__.delete().where(Business.id == self.business_id)
                await db.execute(b_del)
                await db.commit()

    def test_sentiment_analyzer(self):
        """Verifies deterministic sentiment labels."""
        self.assertEqual(sentiment_analyzer.analyze("Thank you for your wonderful help!")[0], "positive")
        self.assertEqual(sentiment_analyzer.analyze("This is the worst scam ever, very disappointed")[0], "negative")
        self.assertEqual(sentiment_analyzer.analyze("What time are you open?", feedback="down")[0], "negative")
        self.assertEqual(sentiment_analyzer.analyze("Standard question without sentiment")[0], "neutral")

    def test_topic_analyzer(self):
        """Verifies inquiry classification into business topics."""
        self.assertEqual(topic_analyzer.classify("What is the price of cold brew in rupees?"), "pricing")
        self.assertEqual(topic_analyzer.classify("How fast is courier delivery to Pune?"), "shipping")
        self.assertEqual(topic_analyzer.classify("My grinder was damaged and broken, need refund"), "returns")
        self.assertEqual(topic_analyzer.classify("Do you sell single-origin dark roast beans?"), "products")
        self.assertEqual(topic_analyzer.classify("What is your support email and phone number?"), "support")

    async def test_dashboard_analytics_endpoint(self):
        """Verifies GET /api/dashboard/analytics computes executive metrics."""
        res = await self.client.get("/api/dashboard/analytics?days=7", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_queries", data)
        self.assertIn("sentiment_breakdown", data)
        self.assertIn("top_topics", data)
        self.assertIn("daily_trend", data)
        self.assertIn("funnel", data)
        self.assertIn("latency_metrics", data)
        self.assertGreaterEqual(data["total_queries"], 2)

    async def test_powerbi_dataset_export(self):
        """Verifies GET /api/dashboard/export/powerbi generates CSV with correct headers."""
        res = await self.client.get("/api/dashboard/export/powerbi?format=csv", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "text/csv; charset=utf-8")
        csv_text = res.text
        self.assertIn("SessionID,Timestamp,CustomerEmail", csv_text)
        self.assertIn("Highland Roast", csv_text)

    async def test_public_share_endpoints(self):
        """Verifies public unauthenticated share permalinks for session and unanswered inquiry."""
        # 1. Share Session
        s_res = await self.client.get(f"/api/public/share/session/{self.session_id}")
        self.assertEqual(s_res.status_code, 200)
        s_data = s_res.json()
        self.assertEqual(s_data["type"], "session")
        self.assertEqual(s_data["business_name"], "Analytics Test Corp")
        self.assertEqual(len(s_data["messages"]), 3)

        # 2. Share Unanswered
        u_res = await self.client.get(f"/api/public/share/unanswered/{self.unanswered_id}")
        self.assertEqual(u_res.status_code, 200)
        u_data = u_res.json()
        self.assertEqual(u_data["type"], "unanswered")
        self.assertIn("Antarctica", u_data["question_text"])
