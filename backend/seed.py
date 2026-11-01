import os
import sys
import uuid
import asyncio
import logging
from datetime import datetime, timedelta

# Ensure backend directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete

from app.database import AsyncSessionLocal, init_db
from app.models.business import Business
from app.models.user import User
from app.models.document import Document, DocumentChunk
from app.models.chat import ChatSession, ChatMessage
from app.models.unanswered import UnansweredQuestion
from app.utils.security import hash_password
from app.utils.chunker import recursive_chunk_text
from app.services.vector_store import vector_store_service
from app.services.bm25_store import bm25_store_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed")

DOCS_DIR = os.path.join(os.path.dirname(__file__), "data", "demo_docs")

DEMO_DOC_FILES = [
    {
        "filename": "returns_and_refunds.txt",
        "title": "Iveri Return and Refund Policy",
        "type": "txt"
    },
    {
        "filename": "shipping_and_delivery.txt",
        "title": "Iveri Shipping and Delivery Guidelines",
        "type": "txt"
    },
    {
        "filename": "warranty_and_repairs.txt",
        "title": "Iveri Hardware Warranty and Service Terms",
        "type": "txt"
    }
]

async def seed_demo_data():
    logger.info("Initializing database schema...")
    await init_db()

    async with AsyncSessionLocal() as db:
        # 1. Clean existing demo business if present
        existing_biz = (await db.execute(
            select(Business).where(Business.slug == "iveri-retail")
        )).scalar_one_or_none()

        if existing_biz:
            logger.info("Purging existing demo business data for clean reseed...")
            await db.delete(existing_biz)
            await db.commit()

        # 2. Create Demo Business
        business = Business(
            name="Iveri Retail & Electronics",
            slug="iveri-retail",
            share_token="iveri-demo-token-2026",
            tone="friendly",
            brand_color="#3b82f6",
            fallback_message="I apologize, but I do not have enough information about that in our store policies. I have notified our support team to help you directly."
        )
        business.starter_questions = [
            "What is your return window for refunds?",
            "How much is express shipping and how fast is it?",
            "Does your 1-year warranty cover battery degradation?",
            "What items are non-returnable final sale?"
        ]
        db.add(business)
        await db.flush()
        logger.info(f"Created Business: {business.name} (ID: {business.id}, Slug: {business.slug})")

        # 3. Create Business Owner User
        owner_user = User(
            business_id=business.id,
            email="owner@iveri-demo.com",
            password_hash=hash_password("IveriDemo2026!"),
            role="owner"
        )
        db.add(owner_user)
        await db.flush()
        logger.info("Created Business Owner: owner@iveri-demo.com / IveriDemo2026!")

        # 4. Ingest and Vectorize Demo Documents
        total_chunks_indexed = 0

        for doc_info in DEMO_DOC_FILES:
            file_path = os.path.join(DOCS_DIR, doc_info["filename"])
            if not os.path.exists(file_path):
                logger.warning(f"File not found: {file_path}")
                continue

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            raw_chunks = recursive_chunk_text(content, chunk_size=400, overlap=60)
            
            doc_record = Document(
                business_id=business.id,
                file_name=doc_info["title"],
                file_type=doc_info["type"],
                storage_path=file_path,
                file_size_bytes=len(content.encode("utf-8")),
                chunk_count=len(raw_chunks),
                status="INDEXED",
                parser_used="txt"
            )
            db.add(doc_record)
            await db.flush()

            service_chunks = []
            for i, c_text in enumerate(raw_chunks):
                chunk_row = DocumentChunk(
                    document_id=doc_record.id,
                    business_id=business.id,
                    chunk_index=i,
                    page_number=1,
                    content=c_text
                )
                chunk_row.payload = {
                    "document_name": doc_info["title"],
                    "document_id": doc_record.id,
                    "page_number": 1,
                    "chunk_id": chunk_row.id
                }
                db.add(chunk_row)
                await db.flush()

                service_chunks.append({
                    "id": chunk_row.id,
                    "content": c_text,
                    "metadata": {
                        "document_name": doc_info["title"],
                        "document_id": doc_record.id,
                        "page_number": 1,
                        "chunk_id": chunk_row.id
                    }
                })

            # Index into ChromaDB & BM25
            await vector_store_service.add_chunks(business.id, service_chunks)
            bm25_store_service.add_chunks(business.id, service_chunks)
            total_chunks_indexed += len(service_chunks)
            logger.info(f"Indexed document '{doc_info['title']}' ({len(service_chunks)} chunks).")

        # 5. Seed Historical Chat Sessions and Conversations
        # Session A: Answered Return Inquiry with Positive Feedback
        session_a = ChatSession(
            business_id=business.id,
            channel="public_link",
            customer_email="sarah.jenkins@example.com",
            last_message_at=datetime.utcnow() - timedelta(hours=2)
        )
        db.add(session_a)
        await db.flush()

        msg_a1 = ChatMessage(
            session_id=session_a.id,
            sender="customer",
            content="Hi! What is your return window for a full refund?",
            is_answered=True
        )
        db.add(msg_a1)

        msg_a2 = ChatMessage(
            session_id=session_a.id,
            sender="assistant",
            content="Hello! According to our return policy, customers may return any eligible product within 30 days of the original delivery date for a 100% full refund to their original payment method. Items returned between 31 and 60 days receive store credit or exchange.",
            is_answered=True,
            feedback="up",
            confidence_score=0.96,
            latency_ms=184,
            llm_provider_used="gemini_flash"
        )
        msg_a2.source_citations = [
            {"document_name": "Iveri Return and Refund Policy", "page_number": 1, "excerpt": "Customers may return any eligible product within 30 days..."}
        ]
        db.add(msg_a2)

        # Session B: Answered Shipping Inquiry
        session_b = ChatSession(
            business_id=business.id,
            channel="widget",
            last_message_at=datetime.utcnow() - timedelta(minutes=45)
        )
        db.add(session_b)
        await db.flush()

        msg_b1 = ChatMessage(
            session_id=session_b.id,
            sender="customer",
            content="How much is express 2-day delivery?",
            is_answered=True
        )
        db.add(msg_b1)

        msg_b2 = ChatMessage(
            session_id=session_b.id,
            sender="assistant",
            content="Express 2-Day Delivery is available at a flat rate of $12.99 per order. If placed before 2:00 PM EST Monday through Friday, delivery takes 1 to 2 business days via FedEx 2Day or UPS 2nd Day Air.",
            is_answered=True,
            feedback="up",
            confidence_score=0.98,
            latency_ms=152,
            llm_provider_used="gemini_flash"
        )
        msg_b2.source_citations = [
            {"document_name": "Iveri Shipping and Delivery Guidelines", "page_number": 1, "excerpt": "Express 2-Day Delivery: 1 to 2 business days... Flat Rate: $12.99"}
        ]
        db.add(msg_b2)

        # Session C: Unanswered Out-of-Domain Inquiry with Captured Lead
        session_c = ChatSession(
            business_id=business.id,
            channel="widget",
            customer_email="michael.baker@consulting.org",
            last_message_at=datetime.utcnow() - timedelta(minutes=10)
        )
        db.add(session_c)
        await db.flush()

        msg_c1 = ChatMessage(
            session_id=session_c.id,
            sender="customer",
            content="Do you offer corporate bulk leasing discounts on laptop rentals?",
            is_answered=False
        )
        db.add(msg_c1)

        msg_c2 = ChatMessage(
            session_id=session_c.id,
            sender="assistant",
            content="I apologize, but I do not have enough information about that in our store policies. I have notified our support team to help you directly.",
            is_answered=False,
            confidence_score=0.22,
            latency_ms=8,
            llm_provider_used="circuit_breaker"
        )
        db.add(msg_c2)
        await db.flush()

        unanswered_c = UnansweredQuestion(
            business_id=business.id,
            session_id=session_c.id,
            message_id=msg_c2.id,
            question_text="Do you offer corporate bulk leasing discounts on laptop rentals?",
            customer_email="michael.baker@consulting.org",
            top_retrieval_score=0.22,
            is_resolved=False
        )
        db.add(unanswered_c)

        await db.commit()
        logger.info("Demo database successfully seeded!")
        logger.info("---------------------------------------------------------")
        logger.info("Demo Business Owner Credentials:")
        logger.info("  Email:    owner@iveri-demo.com")
        logger.info("  Password: IveriDemo2026!")
        logger.info("  Dashboard URL:   http://localhost:8000/dashboard")
        logger.info(f"  Public Chat URL: http://localhost:8000/chat/{business.slug}")
        logger.info(f"  Total Indexed Chunks: {total_chunks_indexed}")
        logger.info("---------------------------------------------------------")

if __name__ == "__main__":
    asyncio.run(seed_demo_data())
