import os
import sys
import time
import uuid
import httpx

BASE_URL = "http://127.0.0.1:8000"

def log_step(title):
    print(f"\n{'='*70}\n[STEP] {title}\n{'='*70}")

def log_success(msg):
    print(f"  [PASS] {msg}")

def log_info(msg):
    print(f"  [INFO] {msg}")

def log_error(msg):
    print(f"  [FAIL] {msg}")

def run_e2e_evaluation():
    print("\n" + "#"*70)
    print(" IDEVIFY AI CUSTOMER SUPPORT ASSISTANT - COMPREHENSIVE E2E AUDIT ")
    print("#"*70)

    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    # 0. Health Check
    log_step("0. System Health Check")
    health_res = client.get("/api/health")
    assert health_res.status_code == 200, f"Health check failed: {health_res.text}"
    log_success(f"System is healthy: {health_res.json()}")

    # 1. Business Registration & Authentication
    log_step("1. User Registration & Authentication (Role: Business Owner)")
    uid = uuid.uuid4().hex[:6]
    owner_email = f"owner_audit_{uid}@brewnestcoffee.com"
    owner_pw = "SecureAuditPass123!"
    biz_name = f"BrewNest Coffee Roasters {uid.upper()}"

    reg_res = client.post("/api/auth/register", json={
        "email": owner_email,
        "password": owner_pw,
        "business_name": biz_name
    })
    assert reg_res.status_code in (200, 201), f"Registration failed: {reg_res.text}"
    reg_data = reg_res.json()
    token = reg_data.get("access_token")
    assert token, "No access token in registration response"
    log_success(f"Owner registered: {owner_email}")

    headers = {"Authorization": f"Bearer {token}"}
    profile_res = client.get("/api/business/settings", headers=headers)
    assert profile_res.status_code == 200, f"Failed to get profile: {profile_res.text}"
    profile = profile_res.json()
    biz_slug = profile["slug"]
    biz_id = profile["id"]
    log_success(f"Business Profile retrieved: Name='{profile['name']}', Slug='{biz_slug}', ID='{biz_id}'")
    log_info(f"Public Chat URL: {BASE_URL}/chat/{biz_slug}")

    # 2. Knowledge Base Upload (Real PDF from Test pdfs folder)
    log_step("2. Knowledge Base: Uploading Test PDF (BrewNest_Customer_Help_Guide.pdf)")
    test_pdf_path = os.path.abspath("Test pdfs/BrewNest_Customer_Help_Guide.pdf")
    assert os.path.exists(test_pdf_path), f"Test PDF not found at {test_pdf_path}"

    with open(test_pdf_path, "rb") as f:
        upload_res = client.post(
            "/api/documents/upload",
            headers=headers,
            files={"files": ("BrewNest_Customer_Help_Guide.pdf", f, "application/pdf")}
        )
    assert upload_res.status_code in (200, 201, 202), f"Document upload failed: {upload_res.text}"
    upload_data = upload_res.json()
    doc_id = upload_data.get("document_id") or upload_data.get("id") or (upload_data[0]["id"] if isinstance(upload_data, list) else None)
    log_success(f"Document uploaded successfully! Doc ID: {doc_id}")

    # Wait for background ingestion worker (PyMuPDF / Sarvam chunking & vector indexing)
    log_info("Waiting for background ingestion worker to parse, chunk, and index...")
    max_wait = 25
    indexed = False
    for i in range(max_wait):
        time.sleep(1)
        docs_list = client.get("/api/documents", headers=headers).json()
        target_doc = next((d for d in docs_list if d["id"] == doc_id), None)
        if target_doc and target_doc.get("status") == "INDEXED":
            indexed = True
            log_success(f"Document indexed in {i+1}s! Chunks: {target_doc.get('total_chunks', 'N/A')}, Pages: {target_doc.get('total_pages', 'N/A')}")
            break
    assert indexed, "Document was not indexed in time!"

    # 3. Public Customer Chat & In-Domain Question (Evaluation Criteria: Relevant retrieval & Source shown)
    log_step("3. Customer Public Chat: In-Domain Question Answering with Citations")
    # Start session as public visitor/customer
    sess_res = client.post("/api/chat/session", json={
        "business_slug_or_token": biz_slug,
        "channel": "widget",
        "customer_name": "Rohan Coffee Enthusiast",
        "customer_phone": "+919876543210",
        "customer_email": "rohan@example.com"
    })
    assert sess_res.status_code == 201, f"Failed to start chat session: {sess_res.text}"
    session_id = sess_res.json()["id"]
    log_success(f"Customer chat session started. Session ID: {session_id}")

    # Ask question 1: Fact explicitly in document
    q1 = "Where is BrewNest located and what year was it founded?"
    log_info(f"Customer Question: '{q1}'")
    ans_res1 = client.post("/api/chat/message", json={
        "session_id": session_id,
        "message": q1
    })
    assert ans_res1.status_code == 200, f"Failed to send message: {ans_res1.text}"
    ans_data1 = ans_res1.json()
    log_info(f"AI Answer: {ans_data1.get('content')}")
    log_info(f"Is Answered: {ans_data1.get('is_answered')}")
    citations1 = ans_data1.get("citations") or ans_data1.get("source_citations") or []
    log_info(f"Citations: {citations1}")

    assert ans_data1.get("is_answered") is True, "Expected is_answered=True for in-domain question"
    assert "pune" in ans_data1.get("content", "").lower() or "2019" in ans_data1.get("content", ""), "Answer did not contain Pune or 2019"
    assert len(citations1) > 0, "Expected source citations in response"
    log_success(f"In-domain question answered accurately from document chunks with citation to '{citations1[0].get('document_name')}' (Page {citations1[0].get('page_number')})!")

    # Ask question 2: Another fact from page 2 (refund fee)
    q2 = "What is the return shipping fee for items?"
    log_info(f"Customer Question: '{q2}'")
    ans_res2 = client.post("/api/chat/message", json={
        "session_id": session_id,
        "message": q2
    })
    assert ans_res2.status_code == 200
    ans_data2 = ans_res2.json()
    log_info(f"AI Answer: {ans_data2.get('content')}")
    assert ans_data2.get("is_answered") is True
    assert "100" in ans_data2.get("content", ""), "Answer did not contain Rs. 100 return fee"
    log_success("Second in-domain question answered with exact ground-truth fee (Rs. 100)!")

    # 4. Unknown Handling & Hallucination Prevention (Evaluation Criteria: No made-up answers)
    log_step("4. Unknown Handling: Asking Out-of-Domain Question (No Hallucination)")
    q_unknown = "Do you sell NVIDIA RTX 5090 graphics cards and gaming laptops?"
    log_info(f"Customer Question: '{q_unknown}'")
    ans_res_unk = client.post("/api/chat/message", json={
        "session_id": session_id,
        "message": q_unknown
    })
    assert ans_res_unk.status_code == 200
    ans_unk = ans_res_unk.json()
    log_info(f"AI Answer: {ans_unk.get('content')}")
    log_info(f"Is Answered: {ans_unk.get('is_answered')}")

    assert ans_unk.get("is_answered") is False, "Expected is_answered=False for unanswerable question"
    assert "not have this information" in ans_unk.get("content", "").lower() or "don't have" in ans_unk.get("content", "").lower(), "Expected polite unknown fallback message"
    # Ensure zero hallucinated graphics card specs
    assert "rtx" not in ans_unk.get("content", "").lower() or "not have" in ans_unk.get("content", "").lower()
    log_success("Polite unknown fallback returned without hallucination!")

    # 5. Unanswered Questions Queue & Support Ticket Escalation
    log_step("5. Unanswered Questions & Auto-Generated Support Ticket")
    # Verify owner sees the question in unanswered queue
    unans_res = client.get("/api/dashboard/unanswered", headers=headers)
    assert unans_res.status_code == 200
    unans_items = unans_res.json()
    found_unans = any(q_unknown in item.get("question_text", "") for item in unans_items)
    assert found_unans, "Unanswered question was not logged to owner's unanswered queue!"
    log_success(f"Unanswered question logged for owner review. Total queued: {len(unans_items)}")

    # Verify auto-generated ticket
    tickets_res = client.get("/api/tickets", headers=headers)
    assert tickets_res.status_code == 200
    tickets = tickets_res.json()
    found_ticket = any(q_unknown in (t.get("description") or t.get("subject") or "") for t in tickets)
    assert found_ticket, "Support ticket was not automatically created for unanswered question!"
    matched_ticket = next(t for t in tickets if q_unknown in (t.get("description") or t.get("subject") or ""))
    log_success(f"Auto-generated ticket verified: Ticket #{matched_ticket['ticket_number']} (Priority: {matched_ticket['priority']}, Channel: {matched_ticket['channel']})")

    # 6. Chat History (Owner 2-Pane View)
    log_step("6. Chat History: Owner Transcript Inspection")
    chats_res = client.get("/api/dashboard/chats?limit=10", headers=headers)
    assert chats_res.status_code == 200
    chats = chats_res.json()
    found_chat = any((c.get("session_id") or c.get("id")) == session_id for c in chats)
    assert found_chat, "Session not found in owner's chat history list!"
    
    # Inspect detailed transcript
    detail_res = client.get(f"/api/dashboard/chats/{session_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    messages = detail.get("messages", [])
    assert len(messages) >= 6, f"Expected at least 6 messages (3 user + 3 assistant), found {len(messages)}"
    log_success(f"Owner can view full chat transcript ({len(messages)} messages recorded).")

    # 7. Dashboard Analytics & Summary Metrics
    log_step("7. Dashboard Analytics: Verification of Chats, Questions, Answered vs Unanswered")
    stats_res = client.get("/api/dashboard/stats", headers=headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    log_info(f"Dashboard Stats: {stats}")
    assert stats["total_chats"] >= 1, "Expected total_chats >= 1"
    assert stats["total_questions"] >= 3, "Expected total_questions >= 3"
    answered_q = stats.get("answered_count", stats.get("answered_questions", 0))
    unanswered_q = stats.get("unanswered_count", stats.get("unanswered_questions", 0))
    assert answered_q >= 2, "Expected answered_questions >= 2"
    assert unanswered_q >= 1, "Expected unanswered_questions >= 1"
    log_success(f"Dashboard statistics verified accurately! (Total: {stats['total_questions']}, Answered: {answered_q}, Unanswered: {unanswered_q})")

    # 8. Manage Documents (Deletion and Dynamic Sync)
    log_step("8. Manage Documents: Deleting Document & Confirming Dynamic Answer Sync")
    del_res = client.delete(f"/api/documents/{doc_id}", headers=headers)
    assert del_res.status_code == 200, f"Delete failed: {del_res.text}"
    log_success(f"Document {doc_id} deleted by owner.")

    # Re-ask the question that previously succeeded: "What is the return shipping fee for items?"
    # Since the document was deleted, the system should no longer know the answer!
    ans_res_after_del = client.post("/api/chat/message", json={
        "session_id": session_id,
        "message": "What is the return shipping fee for items?"
    })
    assert ans_res_after_del.status_code == 200
    ans_after = ans_res_after_del.json()
    log_info(f"AI Answer after document deletion: '{ans_after.get('content')}'")
    assert ans_after.get("is_answered") is False, "Expected is_answered=False after document was deleted!"
    log_success("Confirmed dynamic memory synchronization: Deleted document facts immediately become unknown!")

    # 9. Multi-Tenant Isolation
    log_step("9. Multi-Tenant Isolation: Verifying Complete Data Separation between Businesses")
    # Register Business B (SparkFix)
    uid_b = uuid.uuid4().hex[:6]
    owner_b_email = f"owner_sparkfix_{uid_b}@sparkfixelectronics.com"
    reg_b = client.post("/api/auth/register", json={
        "email": owner_b_email,
        "password": "Password123!",
        "business_name": f"SparkFix Electronics {uid_b.upper()}"
    })
    token_b = reg_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Business B checks docs, chats, tickets
    docs_b = client.get("/api/documents", headers=headers_b).json()
    chats_b = client.get("/api/dashboard/chats", headers=headers_b).json()
    tickets_b = client.get("/api/tickets", headers=headers_b).json()
    stats_b = client.get("/api/dashboard/stats", headers=headers_b).json()

    assert len(docs_b) == 0, f"Multi-tenant violation: Business B saw {len(docs_b)} documents!"
    assert len(chats_b) == 0, f"Multi-tenant violation: Business B saw {len(chats_b)} chats!"
    assert len(tickets_b) == 0, f"Multi-tenant violation: Business B saw {len(tickets_b)} tickets!"
    assert stats_b["total_chats"] == 0, "Multi-tenant violation: Business B stats not zero!"
    log_success("Multi-tenant isolation verified: Zero cross-tenant data leakage between businesses!")

    print("\n" + "#"*70)
    print(" ALL 9 EVALUATION CRITERIA & PROBLEM STATEMENT FEATURES PASSED 100%! ")
    print("#"*70 + "\n")

if __name__ == "__main__":
    run_e2e_evaluation()
