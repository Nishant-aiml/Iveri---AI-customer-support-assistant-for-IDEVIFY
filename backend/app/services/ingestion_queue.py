import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from sqlalchemy.future import select
from app.database import AsyncSessionLocal
from app.models.document import Document, DocumentChunk
from app.services.document_parser import document_parser_service

logger = logging.getLogger(__name__)

@dataclass
class IngestionJob:
    document_id: str
    business_id: str
    file_path: str
    file_name: str
    submitted_at: datetime = datetime.utcnow()

class IngestionWorkerQueue:
    """Asynchronous queue manager with a dedicated worker pool for non-blocking document processing.
    
    Ensures that document uploads return HTTP 202 immediately to the user,
    while extraction, chunking, and dual-indexing run in the background.
    """

    def __init__(self, max_workers: int = 3):
        self.queue: asyncio.Queue[IngestionJob] = asyncio.Queue()
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ingest-worker")
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

    def start(self):
        """Starts the background ingestion worker loop."""
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._process_queue_loop())
            logger.info("IngestionWorkerQueue started background worker.")

    async def shutdown(self):
        """Gracefully shuts down the background worker and thread pool."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
        self.executor.shutdown(wait=False)
        logger.info("IngestionWorkerQueue shutdown complete.")

    async def enqueue(self, job: IngestionJob):
        """Pushes a new document processing job into the queue."""
        await self.queue.put(job)
        logger.info(f"Enqueued document {job.document_id} ('{job.file_name}') for processing.")

    async def _process_queue_loop(self):
        """Continuous consumer loop picking up and processing queued ingestion jobs."""
        while self._running:
            try:
                job = await self.queue.get()
                await self._process_single_job(job)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in ingestion worker loop: {str(e)}", exc_info=True)
                await asyncio.sleep(1.0)

    async def _process_single_job(self, job: IngestionJob):
        """Executes parsing, chunking, and indexing for an individual job."""
        from app.utils.chunker import recursive_chunk_text
        from app.services.rag_engine import rag_engine

        logger.info(f"Beginning ingestion for document {job.document_id} ('{job.file_name}')...")

        async with AsyncSessionLocal() as db:
            # 1. Update status to PROCESSING
            doc_query = select(Document).where(Document.id == job.document_id)
            doc = (await db.execute(doc_query)).scalar_one_or_none()
            if not doc:
                logger.error(f"Document {job.document_id} not found in database.")
                return

            doc.status = "PROCESSING"
            await db.commit()

            try:
                # 2. Parse document (Sarvam AI with PyMuPDF fallback)
                pages, parser_used = await document_parser_service.parse(job.file_path, job.file_name)
                doc.parser_used = parser_used

                # 3. Chunk text recursively per page
                all_chunks = []
                chunk_index = 0

                for page_item in pages:
                    page_num = page_item["page_number"]
                    page_text = page_item["text"]

                    text_chunks = recursive_chunk_text(page_text, chunk_size=600, overlap=60)
                    for text in text_chunks:
                        if not text.strip():
                            continue

                        meta = {
                            "document_name": job.file_name,
                            "page_number": page_num,
                            "chunk_index": chunk_index,
                            "business_id": job.business_id,
                            "document_id": job.document_id
                        }

                        chunk_id = str(uuid.uuid4())
                        db_chunk = DocumentChunk(
                            id=chunk_id,
                            document_id=job.document_id,
                            business_id=job.business_id,
                            chunk_index=chunk_index,
                            page_number=page_num,
                            content=text,
                            payload=meta
                        )
                        db.add(db_chunk)
                        all_chunks.append({
                            "id": chunk_id,
                            "content": text,
                            "metadata": meta
                        })
                        chunk_index += 1

                # 4. Save chunks to relational database
                doc.chunk_count = len(all_chunks)
                doc.status = "INDEXED"
                await db.commit()

                # 5. Index into Multi-Hybrid Engine (ChromaDB Vector + BM25 Lexical)
                await rag_engine.index_document_chunks(job.business_id, all_chunks)

                logger.info(
                    f"Successfully indexed document {job.document_id} "
                    f"('{job.file_name}') with {len(all_chunks)} chunks using '{parser_used}'."
                )

            except Exception as err:
                logger.error(f"Failed to ingest document {job.document_id}: {str(err)}", exc_info=True)
                doc.status = "FAILED"
                doc.error_message = str(err)
                await db.commit()

ingestion_queue = IngestionWorkerQueue()
