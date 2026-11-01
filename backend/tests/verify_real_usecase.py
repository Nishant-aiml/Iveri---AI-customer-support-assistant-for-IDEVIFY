import asyncio
import os
import sys
import httpx

# Ensure backend directory is in python path
sys.path.insert(0, os.path.abspath("backend"))

from app.main import app, lifespan
from app.services.ingestion_queue import ingestion_queue

async def run_live_verification():
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
            # 1. Register Genuine Company
            uid = os.getpid()
            reg_resp = await client.post("/api/auth/register", json={
                "business_name": "Idevify Solutions Enterprise",
                "email": f"contact_{uid}_{int(asyncio.get_event_loop().time())}@idevify-enterprise.com",
                "password": "SecureEnterprisePassword2026!",
                "role": "owner"
            })
            print(f"1. Business Registration Status: {reg_resp.status_code}")
            reg_data = reg_resp.json()
            token = reg_data["access_token"]
            slug = reg_data["business_slug"]
            print(f"   Registered Business: '{reg_data['business_name']}'")
            print(f"   Unique Public Slug: {slug}")

            # 2. Upload Real Document (AI Customer Support.pdf)
            pdf_path = "AI Customer Support.pdf"
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            upload_resp = await client.post(
                "/api/documents/upload",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("AI Customer Support.pdf", pdf_bytes, "application/pdf")}
            )
            print(f"2. PDF Document Upload Status: {upload_resp.status_code}")
            doc_data = upload_resp.json()
            doc_id = doc_data["document_id"]
            print(f"   Indexed Document ID: '{doc_id}'")
            print(f"   Status: {doc_data['status']}")

            # Await async ingestion pipeline to process and vectorize chunks
            print("   Waiting for background ingestion queue...")
            for _ in range(15):
                await asyncio.sleep(1.0)
                list_resp = await client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})
                docs = list_resp.json()
                matching = next((d for d in docs if d["id"] == doc_id), None)
                if matching and matching["status"] == "INDEXED":
                    print(f"   [OK] Document Ingested & Vectorized! Total chunks: {matching['chunk_count']}")
                    break

            # 3. Create Customer Chat Session
            session_resp = await client.post("/api/chat/session", json={
                "business_slug_or_token": slug,
                "channel": "public_link"
            })
            print(f"3. Customer Session Status: {session_resp.status_code}")
            session_id = session_resp.json()["id"]

            # 4. Ask Grounded Question from the PDF
            q1_resp = await client.post("/api/chat/message", json={
                "session_id": session_id,
                "message": "What is the time limit for candidates to complete the project?"
            })
            print("4. Grounded Question Response:")
            q1_data = q1_resp.json()
            print(f"   Answer: {q1_data['content']}")
            print(f"   Is Grounded & Answered: {q1_data['is_answered']}")
            print(f"   Verified Citation Source: {[c['document_name'] for c in q1_data['citations']]}")

            # 5. Ask Missing / Out-of-Domain Question
            q2_resp = await client.post("/api/chat/message", json={
                "session_id": session_id,
                "message": "Do you have round-trip flight tickets to London?"
            })
            print("5. Out-of-Domain Question Response (Circuit Breaker):")
            q2_data = q2_resp.json()
            print(f"   Answer: {q2_data['content']}")
            print(f"   Is Answered: {q2_data['is_answered']} (False = Safe Fallback)")

            # 6. Verify Unanswered Question in Owner Dashboard
            unans_resp = await client.get("/api/dashboard/unanswered", headers={"Authorization": f"Bearer {token}"})
            unans_list = unans_resp.json()
            print(f"6. Unanswered Queue in Owner Console: {len(unans_list)} question(s) logged")
            if unans_list:
                print(f"   Unanswered Query: '{unans_list[0]['question_text']}'")

if __name__ == "__main__":
    asyncio.run(run_live_verification())
