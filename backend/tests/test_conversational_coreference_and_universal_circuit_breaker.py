import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import init_db
from app.services.circuit_breaker import circuit_breaker
from app.services.rag_engine import rag_engine

class TestUniversalCircuitBreakerAndConversationalCoreference(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()

    def test_01_circuit_breaker_is_domain_agnostic_and_universal(self):
        """Verifies circuit breaker does not require hardcoded domain keywords like brewpoint."""
        # 1. Retail / Loyalty query without 'brewpoint' in circuit breaker
        retail_chunks = [{
            "id": "rc-1",
            "content": "Rewards Program: 100 BrewPoints are worth a Rs. 50 discount on all bean orders.",
            "rrf_score": 0.045,
            "dense_similarity": 0.68,
            "sparse_score": 0.8,
            "metadata": {"document_name": "Store_Guide.pdf"}
        }]
        decision = circuit_breaker.evaluate(retail_chunks, query="how much are points worth")
        self.assertTrue(decision["can_answer"], f"Point inquiry should pass without hardcoded keywords: {decision}")

        # 2. Healthcare / Dental clinic query
        dental_chunks = [{
            "id": "dc-1",
            "content": "Lakeview Dental offers teeth whitening for $250 and routine cleaning for $90.",
            "rrf_score": 0.050,
            "dense_similarity": 0.72,
            "sparse_score": 1.2,
            "metadata": {"document_name": "Lakeview_Dental.pdf"}
        }]
        decision_dental = circuit_breaker.evaluate(dental_chunks, query="what is the cost of cleaning")
        self.assertTrue(decision_dental["can_answer"], f"Dental inquiry should pass: {decision_dental}")

        # 3. SaaS / Tech support query
        saas_chunks = [{
            "id": "sc-1",
            "content": "Cloud API Rate Limits: Standard plan permits 10,000 requests per minute with 99.9% uptime.",
            "rrf_score": 0.048,
            "dense_similarity": 0.70,
            "sparse_score": 0.9,
            "metadata": {"document_name": "API_Documentation.pdf"}
        }]
        decision_saas = circuit_breaker.evaluate(saas_chunks, query="what is the rate limit")
        self.assertTrue(decision_saas["can_answer"], f"SaaS rate limit inquiry should pass: {decision_saas}")

        # 4. Out-of-domain tech query must still be blocked
        blocked_decision = circuit_breaker.evaluate(retail_chunks, query="explain quantum computing algorithms")
        self.assertFalse(blocked_decision["can_answer"], "Irrelevant tech query must be blocked.")

    async def test_02_conversational_coreference_followup_query(self):
        """Verifies that follow-up queries like 'how much is this worth' use previous chat history."""
        test_chunks = [{
            "id": "test-c1",
            "content": (
                "BrewPoints Loyalty Program:\n"
                "You earn 1 BrewPoint for every Rs. 10 spent on your orders.\n"
                "100 BrewPoints are worth a Rs. 50 discount.\n"
                "Points expire 12 months after the date they are earned."
            ),
            "metadata": {
                "document_name": "BrewNest_Help_Guide.pdf",
                "page_number": 2,
                "document_id": "doc-test-1",
                "business_id": "test-biz-uuid"
            }
        }]
        await rag_engine.index_document_chunks("test-biz-uuid", test_chunks)

        # Multi-turn history: customer previously asked about points/rewards
        chat_history = [
            {"role": "customer", "content": "Do you have a rewards program?"},
            {"role": "assistant", "content": "Yes! You earn 1 BrewPoint for every Rs. 10 spent, and 100 BrewPoints are worth a Rs. 50 discount."}
        ]

        # Follow-up question with pronoun: "how much is this worth"
        res = await rag_engine.query(
            business_id="test-biz-uuid",
            user_query="how much is this worth",
            business_settings={
                "name": "BrewNest Coffee",
                "fallback_message": "Sorry, information not found."
            },
            chat_history=chat_history
        )

        self.assertTrue(res["is_answered"], "Follow-up question should be answered successfully.")
        self.assertTrue(
            "50" in res["answer"] or "brewpoint" in res["answer"].lower() or "point" in res["answer"].lower(),
            f"Answer should contain the points valuation: {res['answer']}"
        )
        self.assertTrue(
            "different" in res["answer"].lower() or "referring" in res["answer"].lower() or "let me know" in res["answer"].lower(),
            f"Answer should include polite disambiguation offer: {res['answer']}"
        )

    async def test_03_standalone_vague_pronoun_prompts_clarification(self):
        """Verifies that a vague pronoun query without history asks for clarification rather than cold failing."""
        test_chunks = [{
            "id": "test-c2",
            "content": "BrewNest Coffee: Highland Roast 250g Rs. 450, Espresso Blend 1kg Rs. 1,400.",
            "metadata": {
                "document_name": "BrewNest_Help_Guide.pdf",
                "page_number": 1,
                "document_id": "doc-test-2",
                "business_id": "test-biz-standalone"
            }
        }]
        await rag_engine.index_document_chunks("test-biz-standalone", test_chunks)

        # Standalone vague query with no prior history
        res = await rag_engine.query(
            business_id="test-biz-standalone",
            user_query="how much is this worth",
            business_settings={"name": "BrewNest Coffee"},
            chat_history=[]
        )

        self.assertTrue(res["is_answered"], "Standalone inquiry should return an answered clarification.")
        self.assertTrue(
            "specify" in res["answer"].lower() or "which" in res["answer"].lower() or "product" in res["answer"].lower() or "item" in res["answer"].lower(),
            f"Answer should prompt user to specify the item: {res['answer']}"
        )

if __name__ == "__main__":
    unittest.main()
