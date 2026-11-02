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
        """Starts the background ingestion worker loop and recovers unprocessed jobs."""
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._process_queue_loop())
            asyncio.create_task(self.recover_unprocessed_jobs())
            logger.info("IngestionWorkerQueue started background worker.")

    async def recover_unprocessed_jobs(self):
        """Scans database for documents that were QUEUED or interrupted during PROCESSING and enqueues them."""
        try:
            import os
            from app.database import AsyncSessionLocal
            from app.models.document import Document
            from sqlalchemy.future import select

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Document).where(Document.status.in_(["QUEUED", "PROCESSING"]))
                )
                pending_docs = result.scalars().all()
                for doc in pending_docs:
                    if doc.storage_path and os.path.exists(doc.storage_path):
                        await self.enqueue(IngestionJob(
                            document_id=doc.id,
                            business_id=doc.business_id,
                            file_path=doc.storage_path,
                            file_name=doc.file_name
                        ))
                        logger.info(f"Recovered pending document {doc.id} ('{doc.file_name}') on startup.")
        except Exception as e:
            logger.warning(f"Error during ingestion job recovery on startup: {str(e)}")

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
        """Executes streamed parsing, chunking, and indexing for an individual job (supports 1,000+ pages)."""
        import gc
        from app.utils.chunker import recursive_chunk_text
        from app.services.rag_engine import rag_engine

        logger.info(f"Beginning streamed ingestion for document {job.document_id} ('{job.file_name}')...")

        async with AsyncSessionLocal() as db:
            # 1. Update status to PROCESSING
            doc_query = select(Document).where(Document.id == job.document_id)
            doc = (await db.execute(doc_query)).scalar_one_or_none()
            if not doc:
                logger.error(f"Document {job.document_id} not found in database.")
                return

            doc.status = "PROCESSING"
            doc.processed_pages = 0
            doc.processing_progress = 0
            await db.commit()

            try:
                chunk_index = 0
                total_chunks_indexed = 0
                parser_used_final = "pending"

                # 2. Stream parse in memory-safe batches of 25 pages
                for page_batch, processed_count, total_count, parser_used in document_parser_service.stream_parse(
                    job.file_path, job.file_name, batch_size=25
                ):
                    parser_used_final = parser_used
                    batch_chunks = []

                    for page_item in page_batch:
                        p_num = page_item["page_number"]
                        p_text = page_item["text"]

                        t_chunks = recursive_chunk_text(p_text, chunk_size=600, overlap=60)
                        for text in t_chunks:
                            if not text.strip():
                                continue

                            meta = {
                                "document_name": job.file_name,
                                "page_number": p_num,
                                "chunk_index": chunk_index,
                                "business_id": job.business_id,
                                "document_id": job.document_id
                            }

                            c_id = str(uuid.uuid4())
                            db_chunk = DocumentChunk(
                                id=c_id,
                                document_id=job.document_id,
                                business_id=job.business_id,
                                chunk_index=chunk_index,
                                page_number=p_num,
                                content=text,
                                payload=meta
                            )
                            db.add(db_chunk)
                            batch_chunks.append({
                                "id": c_id,
                                "content": text,
                                "metadata": meta
                            })
                            chunk_index += 1

                    # 3. Commit chunks for this batch
                    await db.commit()

                    # 4. Streamed Indexing into Multi-Hybrid Engine (ChromaDB + BM25)
                    if batch_chunks:
                        await rag_engine.index_document_chunks(job.business_id, batch_chunks)
                        total_chunks_indexed += len(batch_chunks)

                    # 5. Progressive status update in database
                    progress_pct = int((processed_count / max(total_count, 1)) * 100)
                    doc.processed_pages = processed_count
                    doc.total_pages = total_count
                    doc.processing_progress = min(progress_pct, 99)
                    doc.chunk_count = total_chunks_indexed
                    doc.parser_used = parser_used_final
                    await db.commit()

                    # Explicit memory cleanup for 1,000-page stability
                    del batch_chunks
                    gc.collect()
                    # Yield event loop so concurrent HTTP chat & UI requests are never starved
                    await asyncio.sleep(0.02)

                # 6. Final completion state
                doc.status = "INDEXED"
                doc.processing_progress = 100
                doc.processed_pages = doc.total_pages
                doc.chunk_count = total_chunks_indexed
                doc.parser_used = parser_used_final
                await db.commit()

                logger.info(
                    f"Successfully indexed document {job.document_id} "
                    f"('{job.file_name}') with {total_chunks_indexed} chunks across {doc.total_pages} pages."
                )

            except Exception as err:
                logger.error(f"Failed to ingest document {job.document_id}: {str(err)}", exc_info=True)
                doc.status = "FAILED"
                doc.error_message = str(err)
                await db.commit()

ingestion_queue = IngestionWorkerQueue()
