import os
import sys
import unittest
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db
from app.services.vector_store import vector_store_service
from app.services.bm25_store import bm25_store_service


class TestLiveMultiTenantIsolationAttacks(unittest.IsolatedAsyncioTestCase):
    """Live Penetration Attack Suite: Empirical Verification of Multi-Tenant Isolation.

    Evaluates the 5 critical security attack vectors against live ASGI endpoints:
    1. Access B's document ID -> 404 Not Found (Tenant Scoped)
    2. Change business ID in API -> Rejected / Scoped exclusively to authenticated tenant
    3. Query B's chatbot data -> Isolated retrieval (Canary token 100% shielded)
    4. Access B's chat history -> 404 Not Found
    5. Delete B's documents -> 404 Not Found & Document remains intact
    """

    async def asyncSetUp(self):
        await init_db()
        self.transport = ASGITransport(app=app)
        self.client = AsyncClient(transport=self.transport, base_url="http://test")

        # 1. Register Business A (Attacker Tenant)
        reg_payload_a = {
            "business_name": "Alpha Corp",
            "email": f"tenant_a_{uuid.uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "role": "owner"
        }
        res_a = await self.client.post("/api/auth/register", json=reg_payload_a)
        self.assertEqual(res_a.status_code, 201)
        data_a = res_a.json()
        self.token_a = data_a["access_token"]
        self.headers_a = {"Authorization": f"Bearer {self.token_a}"}

        me_a = await self.client.get("/api/auth/me", headers=self.headers_a)
        self.biz_a_id = me_a.json()["business_id"]
        self.biz_a_slug = me_a.json()["business_slug"]

        # 2. Register Business B (Victim Tenant)
        reg_payload_b = {
            "business_name": "Beta Industries",
            "email": f"tenant_b_{uuid.uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "role": "owner"
        }
        res_b = await self.client.post("/api/auth/register", json=reg_payload_b)
        self.assertEqual(res_b.status_code, 201)
        data_b = res_b.json()
        self.token_b = data_b["access_token"]
        self.headers_b = {"Authorization": f"Bearer {self.token_b}"}

        me_b = await self.client.get("/api/auth/me", headers=self.headers_b)
        self.biz_b_id = me_b.json()["business_id"]
        self.biz_b_slug = me_b.json()["business_slug"]

        # 3. Tenant B indexes a confidential document with a unique Canary Secret
        self.canary_secret = f"BETA_VIP_PROMO_{uuid.uuid4().hex[:8]}"
        self.b_doc_content = (
            f"Beta Industries Executive Partnership Program 2026.\n"
            f"The exclusive enterprise discount code is {self.canary_secret}.\n"
            f"VIP enterprise partners receive 40% rebate using this promo code."
        )

        qa_res = await self.client.post(
            "/api/documents/manual-qa",
            headers=self.headers_b,
            json={
                "question": "What is the exclusive enterprise discount code for Beta Industries?",
                "answer": self.b_doc_content,
                "category": "Partner"
            }
        )
        self.assertEqual(qa_res.status_code, 201)
        self.doc_b_id = qa_res.json()["document_id"]

        # 4. Tenant B has an active customer conversation with private customer PII
        sess_res = await self.client.post("/api/chat/session", json={
            "business_slug_or_token": self.biz_b_slug,
            "channel": "public_link"
        })
        self.assertEqual(sess_res.status_code, 201)
        self.session_b_id = sess_res.json()["id"]

        msg_res = await self.client.post("/api/chat/message", json={
            "session_id": self.session_b_id,
            "message": "My confidential customer SSN is 999-00-1234 and order is ORD-BETA-7788."
        })
        self.assertEqual(msg_res.status_code, 200)

    async def asyncTearDown(self):
        await self.client.aclose()

    # =========================================================================
    # ATTACK 1: Business A attempts to access Business B's document ID
    # Expected Result: 404 Not Found (Strictly Scoped)
    # =========================================================================
    async def test_attack_01_access_b_document_id(self):
        """ATTACK 1: Business A attempts to access Business B's document metadata, chunks, and file."""
        # 1a. Attempt to get B's document metadata using A's JWT
        res_meta = await self.client.get(f"/api/documents/{self.doc_b_id}", headers=self.headers_a)
        self.assertEqual(res_meta.status_code, 404, "A should receive 404 when querying B's document ID")

        # 1b. Attempt to get B's document chunks using A's JWT
        res_chunks = await self.client.get(f"/api/documents/{self.doc_b_id}/chunks", headers=self.headers_a)
        self.assertEqual(res_chunks.status_code, 404, "A should receive 404 when querying B's document chunks")

        # 1c. Attempt to download B's physical document file using A's JWT
        res_file = await self.client.get(f"/api/documents/{self.doc_b_id}/file", headers=self.headers_a)
        self.assertEqual(res_file.status_code, 404, "A should receive 404 when downloading B's raw file")

        # 1d. Verify A's document list does NOT contain B's document
        res_list = await self.client.get("/api/documents", headers=self.headers_a)
        self.assertEqual(res_list.status_code, 200)
        docs_a = res_list.json()
        doc_ids_a = [d["id"] for d in docs_a]
        self.assertNotIn(self.doc_b_id, doc_ids_a, "B's document ID must not appear in A's document list")
        print("\n[PEN-TEST PASS] Attack 1: Accessing B's document ID cleanly rejected with 404 Not Found.")

    # =========================================================================
    # ATTACK 2: Business A attempts to change business ID in API (Parameter Tampering)
    # Expected Result: Rejected / Query scopes strictly to authenticated user's business
    # =========================================================================
    async def test_attack_02_change_business_id_in_api(self):
        """ATTACK 2: Business A attempts to manipulate query parameters or payloads with B's business_id."""
        # 2a. Attempt to pass B's business_id as query parameter to list documents
        res_tamper_docs = await self.client.get(
            f"/api/documents?business_id={self.biz_b_id}",
            headers=self.headers_a
        )
        self.assertEqual(res_tamper_docs.status_code, 200)
        tampered_docs = res_tamper_docs.json()
        doc_ids = [d["id"] for d in tampered_docs]
        self.assertNotIn(self.doc_b_id, doc_ids, "Tampering business_id in query parameter must NOT expose B's documents")

        # 2b. Attempt to modify B's business settings by injecting B's business_id in payload
        res_tamper_settings = await self.client.put(
            "/api/business/settings",
            headers=self.headers_a,
            json={
                "business_id": self.biz_b_id,
                "name": "HACKED_DEFACED_NAME_BY_TENANT_A",
                "brand_color": "#FF0000"
            }
        )
        self.assertEqual(res_tamper_settings.status_code, 200)
        # Verify Tenant B's settings remained untouched!
        b_profile = await self.client.get(f"/api/public/business/{self.biz_b_slug}")
        self.assertNotEqual(b_profile.json()["name"], "HACKED_DEFACED_NAME_BY_TENANT_A",
                            "Tenant B's business name must NOT be modified by Tenant A's request!")

        # 2c. Attempt to modify B's profile via PATCH with injected business_id
        await self.client.patch(
            "/api/business/profile",
            headers=self.headers_a,
            json={
                "business_id": self.biz_b_id,
                "whatsapp_number": "+999999999"
            }
        )
        b_profile_after = await self.client.get(f"/api/public/business/{self.biz_b_slug}")
        self.assertNotEqual(b_profile_after.json().get("whatsapp_number"), "+999999999",
                            "Tenant B's profile must NOT be modified by Tenant A's PATCH request!")
        print("[PEN-TEST PASS] Attack 2: Manipulating business_id in API parameters strictly rejected/scoped.")

    # =========================================================================
    # ATTACK 3: Query B's chatbot data / Cross-Tenant Vector & RAG Leakage
    # Expected Result: Isolated Retrieval (Zero canary leak)
    # =========================================================================
    async def test_attack_03_query_b_chatbot_data_isolated_retrieval(self):
        """ATTACK 3: Tenant A attempts to extract Tenant B's confidential canary secret via RAG."""
        # 3a. Direct ChromaDB search scoped to Tenant A for B's confidential secret
        dense_hits = await vector_store_service.search(
            business_id=self.biz_a_id,
            query=f"exclusive enterprise discount code {self.canary_secret}",
            top_k=10
        )
        for hit in dense_hits:
            self.assertNotIn(self.canary_secret, hit.get("content", ""),
                             "ChromaDB dense search for Tenant A MUST NEVER return Tenant B's chunks!")

        # 3b. Direct BM25 search scoped to Tenant A for B's confidential secret
        sparse_hits = bm25_store_service.search(
            business_id=self.biz_a_id,
            query=f"exclusive enterprise discount code {self.canary_secret}",
            top_k=10
        )
        for hit in sparse_hits:
            self.assertNotIn(self.canary_secret, hit.get("content", ""),
                             "BM25 sparse search for Tenant A MUST NEVER return Tenant B's chunks!")

        # 3c. Full Hybrid RAG Query through Tenant A's playground
        rag_res_a = await self.client.post(
            "/api/dashboard/playground",
            headers=self.headers_a,
            json={
                "query": f"What is the exclusive enterprise discount code {self.canary_secret}?"
            }
        )
        self.assertEqual(rag_res_a.status_code, 200)
        data_a = rag_res_a.json()
        self.assertNotIn(self.canary_secret, str(data_a.get("generated_answer", "")),
                         "Tenant A's RAG playground must NOT leak Tenant B's canary secret!")
        self.assertFalse(data_a.get("circuit_breaker_passed", True),
                         "RAG circuit breaker should trip for Tenant A when querying Tenant B's unknown knowledge")

        # 3d. Verify Tenant B querying the same secret SUCCEEDS with citation (proving it is indexed for B)
        rag_res_b = await self.client.post(
            "/api/dashboard/playground",
            headers=self.headers_b,
            json={
                "query": "What is the exclusive enterprise discount code for Beta Industries?"
            }
        )
        self.assertEqual(rag_res_b.status_code, 200)
        data_b = rag_res_b.json()
        self.assertTrue(data_b.get("circuit_breaker_passed"), "Tenant B querying its own document should succeed.")
        self.assertIn(self.canary_secret, str(data_b.get("generated_answer", "")),
                      "Tenant B should retrieve its own confidential promo code.")
        print("[PEN-TEST PASS] Attack 3: Cross-tenant RAG query completely isolated; canary token 100% shielded.")

    # =========================================================================
    # ATTACK 4: Business A attempts to access Business B's chat history
    # Expected Result: 404 Not Found
    # =========================================================================
    async def test_attack_04_access_b_chat_history(self):
        """ATTACK 4: Business A attempts to retrieve or inspect Business B's conversation transcripts."""
        # 4a. Attempt to get B's specific chat session transcript using A's JWT
        res_chat = await self.client.get(
            f"/api/dashboard/chats/{self.session_b_id}",
            headers=self.headers_a
        )
        self.assertEqual(res_chat.status_code, 404,
                         "Tenant A querying Tenant B's chat session ID must return 404 Not Found")

        # 4b. Verify Tenant A's conversation list does NOT include B's session
        res_chats_list = await self.client.get(
            "/api/dashboard/chats",
            headers=self.headers_a
        )
        self.assertEqual(res_chats_list.status_code, 200)
        chats_a = res_chats_list.json()
        session_ids_a = [c["id"] for c in chats_a]
        self.assertNotIn(self.session_b_id, session_ids_a,
                         "Tenant B's session ID must NOT appear in Tenant A's chat list")

        # 4c. Verify Tenant A attempting to delete Tenant B's session returns 404
        res_del_chat = await self.client.delete(
            f"/api/dashboard/chats/{self.session_b_id}",
            headers=self.headers_a
        )
        self.assertEqual(res_del_chat.status_code, 404,
                         "Tenant A deleting Tenant B's session must return 404 Not Found")
        print("[PEN-TEST PASS] Attack 4: Accessing B's chat history cleanly rejected with 404 Not Found.")

    # =========================================================================
    # ATTACK 5: Business A attempts to delete Business B's documents
    # Expected Result: 404 Not Found / Document remains intact
    # =========================================================================
    async def test_attack_05_delete_b_documents_rejected(self):
        """ATTACK 5: Business A attempts to execute unauthorized deletion of Business B's document."""
        # 5a. Tenant A sends DELETE for Tenant B's document
        res_del = await self.client.delete(
            f"/api/documents/{self.doc_b_id}",
            headers=self.headers_a
        )
        self.assertEqual(res_del.status_code, 404,
                         "Tenant A deleting Tenant B's document must return 404 Not Found")

        # 5b. Verify Tenant B's document STILL EXISTS and was NOT deleted
        res_b_verify = await self.client.get(
            f"/api/documents/{self.doc_b_id}",
            headers=self.headers_b
        )
        self.assertEqual(res_b_verify.status_code, 200,
                         "Tenant B's document must remain completely intact after Tenant A's deletion attempt")
        self.assertEqual(res_b_verify.json()["id"], self.doc_b_id)
        print("[PEN-TEST PASS] Attack 5: Deleting B's documents rejected with 404; document remains intact.")


if __name__ == "__main__":
    unittest.main()
