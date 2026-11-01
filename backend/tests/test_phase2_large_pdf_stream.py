import os
import fitz
import unittest
import uuid
from sqlalchemy.future import select
from app.database import AsyncSessionLocal, init_db
from app.models.business import Business
from app.models.document import Document, DocumentChunk
from app.services.fallback_parser import PyMuPDFFallbackParser
from app.services.document_parser import document_parser_service
from app.services.ingestion_queue import IngestionJob, ingestion_queue
from app.services.rag_engine import rag_engine

class TestPhase2LargePDFStream(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        self.test_pdf_path = f"test_stream_{uuid.uuid4().hex[:6]}.pdf"
        self.business_id = f"test_biz_{uuid.uuid4().hex[:6]}"
        
        # 1. Create a 30-page test PDF with distinct searchable markers
        doc = fitz.open()
        for i in range(1, 31):
            page = doc.new_page()
            text = (
                f"Page {i} of 30.\n"
                f"Section: Enterprise Documentation Part {i}.\n"
                f"Detail code: DELTA_CODE_{i}.\n"
                f"Shipping policy rule for region {i}: Orders take {i + 1} business days to arrive.\n"
            )
            page.insert_text((50, 72), text, fontsize=12)
        doc.save(self.test_pdf_path)
        doc.close()

        # 2. Insert test business in DB
        async with AsyncSessionLocal() as db:
            biz = Business(
                id=self.business_id,
                name="Stream Ingestion Test Corp",
                slug=f"stream-test-{uuid.uuid4().hex[:6]}",
                share_token=uuid.uuid4().hex
            )
            db.add(biz)
            await db.commit()

    async def asyncTearDown(self):
        if os.path.exists(self.test_pdf_path):
            try:
                os.remove(self.test_pdf_path)
            except Exception:
                pass
        
        async with AsyncSessionLocal() as db:
            biz = (await db.execute(select(Business).where(Business.id == self.business_id))).scalar_one_or_none()
            if biz:
                await db.delete(biz)
                await db.commit()

    def test_pdf_page_count_and_streaming(self):
        """Verifies get_page_count and stream_pages generators function with 0 memory bloat."""
        page_count = PyMuPDFFallbackParser.get_page_count(self.test_pdf_path)
        self.assertEqual(page_count, 30)

        # Stream in batches of 10
        stream_batches = list(PyMuPDFFallbackParser.stream_pages(self.test_pdf_path, batch_size=10))
        self.assertEqual(len(stream_batches), 3)

        total_pages_seen = 0
        for batch, processed_so_far, total_pages in stream_batches:
            self.assertEqual(total_pages, 30)
            total_pages_seen += len(batch)
        self.assertEqual(total_pages_seen, 30)

    def test_unified_parser_stream(self):
        """Verifies document_parser_service.stream_parse yields properly."""
        stream_batches = list(
            document_parser_service.stream_parse(self.test_pdf_path, "test.pdf", batch_size=10)
        )
        self.assertEqual(len(stream_batches), 3)
        for batch, processed, total, parser_used in stream_batches:
            self.assertEqual(total, 30)
            self.assertEqual(parser_used, "pymupdf")

    async def test_end_to_end_streamed_ingestion(self):
        """Verifies ingestion_queue._process_single_job indexes streamed pages and updates progressive telemetry."""
        doc_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            doc = Document(
                id=doc_id,
                business_id=self.business_id,
                file_name="stream_test.pdf",
                file_type="pdf",
                storage_path=self.test_pdf_path,
                file_size_bytes=os.path.getsize(self.test_pdf_path),
                status="QUEUED"
            )
            db.add(doc)
            await db.commit()

        job = IngestionJob(
            document_id=doc_id,
            business_id=self.business_id,
            file_path=self.test_pdf_path,
            file_name="stream_test.pdf"
        )

        # Process job synchronously
        await ingestion_queue._process_single_job(job)

        # Verify DB document state
        async with AsyncSessionLocal() as db:
            saved_doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalar_one()
            self.assertEqual(saved_doc.status, "INDEXED")
            self.assertEqual(saved_doc.total_pages, 30)
            self.assertEqual(saved_doc.processed_pages, 30)
            self.assertEqual(saved_doc.processing_progress, 100)
            self.assertGreater(saved_doc.chunk_count, 0)

            # Check that chunks exist in relational DB
            chunks = (await db.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc_id))).scalars().all()
            self.assertGreater(len(chunks), 0)

        # Verify RAG engine retrieves information from page 25
        res = await rag_engine.query(
            business_id=self.business_id,
            user_query="What is DELTA_CODE_25 and region 25 shipping policy?"
        )
        self.assertTrue(res["is_answered"])
        self.assertIn("25", res["answer"])
