import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import init_db
from app.services.rag_engine import rag_engine

class TestPhase3RAG(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.tenant_1_id = "test-tenant-boutique-101"
        self.tenant_2_id = "test-tenant-electronics-202"

        # Index test documents for Tenant 1
        chunks_tenant_1 = [
            {
                "id": "chunk-ship-1",
                "content": (
                    "SHIPPING POLICY:\n"
                    "Standard delivery takes 3 to 5 business days and costs $5.99.\n"
                    "Express delivery takes 1 to 2 business days and costs $14.99.\n"
                    "All orders over $50 qualify for free standard shipping."
                ),
                "metadata": {
                    "document_name": "Shipping_Policy_2026.pdf",
                    "page_number": 1,
                    "document_id": "doc-ship-1",
                    "business_id": self.tenant_1_id
                }
            },
            {
                "id": "chunk-return-1",
                "content": (
                    "REFUND AND RETURN POLICY:\n"
                    "Items in original condition can be returned within 30 days for a full refund.\n"
                    "Items returned between 31 and 60 days receive store credit only.\n"
                    "No returns are accepted after 60 days."
                ),
                "metadata": {
                    "document_name": "Return_Policy_2026.pdf",
                    "page_number": 2,
                    "document_id": "doc-return-1",
                    "business_id": self.tenant_1_id
                }
            }
        ]

        await rag_engine.index_document_chunks(self.tenant_1_id, chunks_tenant_1)

    async def test_01_greeting_interceptor(self):
        res = await rag_engine.query(
            business_id=self.tenant_1_id,
            user_query="Hi, good morning!",
            business_settings={"name": "Maria Boutique"}
        )
        self.assertTrue(res["is_answered"])
        self.assertEqual(res["llm_provider"], "greeting_rule")
        self.assertIn("Maria Boutique", res["answer"])
        self.assertEqual(len(res["citations"]), 0)
        print("\n[PASS] RAG-01: Greeting interceptor returned instant rule-based reply.")

    async def test_02_grounded_answer_with_citations(self):
        res = await rag_engine.query(
            business_id=self.tenant_1_id,
            user_query="How much does express delivery cost and how long does it take?",
            business_settings={"name": "Maria Boutique"}
        )
        self.assertTrue(res["is_answered"])
        self.assertIn("14.99", res["answer"])
        self.assertTrue(len(res["citations"]) > 0)
        self.assertEqual(res["citations"][0]["document_name"], "Shipping_Policy_2026.pdf")
        print(f"[PASS] RAG-02: Grounded answer retrieved with source citation: {res['citations'][0]['document_name']}.")

    async def test_03_circuit_breaker_on_out_of_domain_query(self):
        # Out-of-scope question that has no business context
        res = await rag_engine.query(
            business_id=self.tenant_1_id,
            user_query="Can you book me a flight ticket to New York for tomorrow?",
            business_settings={
                "name": "Maria Boutique",
                "fallback_message": "Sorry, I don't have this in my documents."
            }
        )
        self.assertFalse(res["is_answered"])
        self.assertEqual(res["llm_provider"], "circuit_breaker")
        self.assertEqual(res["answer"], "Sorry, I don't have this in my documents.")
        self.assertEqual(len(res["citations"]), 0)
        print("[PASS] RAG-03: Pre-LLM circuit breaker successfully tripped on irrelevant query (Zero hallucinations!).")

    async def test_04_tenant_data_isolation(self):
        # Tenant 2 asks for shipping policy (only uploaded to Tenant 1)
        res = await rag_engine.query(
            business_id=self.tenant_2_id,
            user_query="What is your shipping policy?",
            business_settings={"name": "Apex Electronics"}
        )
        # Must fail to retrieve Tenant 1's documents
        self.assertFalse(res["is_answered"])
        self.assertEqual(res["llm_provider"], "circuit_breaker")
        print("[PASS] RAG-04: Tenant isolation verified (Tenant 2 cannot query Tenant 1's knowledge base).")

if __name__ == "__main__":
    unittest.main()
