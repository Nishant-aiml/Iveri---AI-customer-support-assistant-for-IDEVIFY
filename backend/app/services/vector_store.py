import os
import hashlib
import logging
import httpx
from typing import List, Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

class VectorStoreService:
    """Persistent dense vector store powered by ChromaDB with strict multi-tenant isolation.
    
    Generates embeddings via Google Gemini text-embedding-004 (or OpenAI/fallback)
    and queries with where={"business_id": tenant_id}.
    """

    def __init__(self, persist_directory: Optional[str] = None):
        self.persist_directory = persist_directory or settings.CHROMA_PERSIST_DIRECTORY
        os.makedirs(self.persist_directory, exist_ok=True)
        self._init_chroma()

    def _init_chroma(self):
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self.client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False, is_persistent=True)
        )
        self.collection = self.client.get_or_create_collection(
            name="idevify_knowledge_chunks",
            metadata={"hnsw:space": "cosine"}
        )

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Computes dense vector embeddings using Google Gemini (or local fallback) in batches of 50."""
        if not texts:
            return []

        # Batch texts into chunks of 50 to honor external API limits
        BATCH_SIZE = 50
        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), BATCH_SIZE):
            batch_texts = texts[i:i + BATCH_SIZE]
            batch_embeddings = await self._get_embeddings_batch(batch_texts)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def _get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        # 1. Local Semantic ONNX all-MiniLM-L6-v2 Embeddings (Deterministic 384-dim Cosine Space)
        # Keeps embeddings 100% matched with ChromaDB index and runs in-process with 0 external API calls
        try:
            from chromadb.utils import embedding_functions
            default_ef = embedding_functions.DefaultEmbeddingFunction()
            embeddings = default_ef(texts)
            return [list(map(float, emb)) for emb in embeddings]
        except Exception as e:
            logger.warning(f"Chroma ONNX embedding failed ({str(e)}). Trying Google Gemini embedding...")

        # 2. Google Gemini Embeddings (Cloud Fallback)
        if settings.GEMINI_API_KEY:
            try:
                embeddings = []
                emb_model = getattr(settings, "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
                if not emb_model.startswith("models/"):
                    model_path = f"models/{emb_model}"
                else:
                    model_path = emb_model
                url = f"https://generativelanguage.googleapis.com/v1beta/{model_path}:batchEmbedContents?key={settings.GEMINI_API_KEY}"
                
                requests_payload = [
                    {"model": model_path, "content": {"parts": [{"text": t[:2048]}]}}
                    for t in texts
                ]
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, json={"requests": requests_payload})
                    if resp.status_code == 200:
                        data = resp.json()
                        for emb_obj in data.get("embeddings", []):
                            embeddings.append(emb_obj["values"])
                        return embeddings
                    else:
                        logger.warning(f"Gemini embedding API returned {resp.status_code}. Using hash fallback embedding...")
            except Exception as e:
                logger.warning(f"Gemini embedding call failed ({str(e)}). Using hash fallback embedding...")

        # 3. Local Deterministic 384-dimensional Hash Embedding Fallback
        fallback_embeddings: List[List[float]] = []
        for text in texts:
            vec = [0.0] * 384
            words = text.lower().split()
            for word in words:
                h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
                idx = h % 384
                sign = 1.0 if (h % 2 == 0) else -1.0
                vec[idx] += sign
            
            # Normalize vector
            norm = sum(x * x for x in vec) ** 0.5
            if norm > 0:
                vec = [x / norm for x in vec]
            fallback_embeddings.append(vec)

        return fallback_embeddings

    async def add_chunks(self, business_id: str, chunks: List[Dict[str, Any]], batch_size: int = 50):
        """Generates embeddings and inserts chunks into ChromaDB with tenant metadata in batches."""
        if not chunks:
            return

        for i in range(0, len(chunks), batch_size):
            chunk_slice = chunks[i:i + batch_size]
            ids = [c["id"] for c in chunk_slice]
            texts = [c["content"] for c in chunk_slice]
            metadatas = []

            for c in chunk_slice:
                meta = c.get("metadata", {}).copy()
                meta["business_id"] = str(business_id)
                meta["document_id"] = str(meta.get("document_id", ""))
                meta["document_name"] = str(meta.get("document_name", "Unknown Document"))
                meta["page_number"] = int(meta.get("page_number", 1))
                metadatas.append(meta)

            embeddings = await self.get_embeddings(texts)

            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )
        logger.info(f"ChromaDB indexed {len(chunks)} chunks for business {business_id}.")

    async def delete_document(self, business_id: str, document_id: str):
        """Removes all chunks belonging to a document under the specified business."""
        try:
            self.collection.delete(
                where={
                    "$and": [
                        {"business_id": {"$eq": str(business_id)}},
                        {"document_id": {"$eq": str(document_id)}}
                    ]
                }
            )
            logger.info(f"ChromaDB deleted chunks for document {document_id} under business {business_id}.")
        except Exception as e:
            logger.error(f"Error deleting chunks from ChromaDB: {str(e)}")

    async def search(self, business_id: str, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Performs cosine vector similarity search strictly scoped to business_id."""
        query_embeddings = await self.get_embeddings([query])
        if not query_embeddings:
            return []

        try:
            results = self.collection.query(
                query_embeddings=query_embeddings,
                n_results=top_k,
                where={"business_id": {"$eq": str(business_id)}}
            )

            hits = []
            if results and results["ids"] and len(results["ids"][0]) > 0:
                ids = results["ids"][0]
                docs = results["documents"][0]
                metas = results["metadatas"][0]
                distances = results["distances"][0] if "distances" in results and results["distances"] else [0.0] * len(ids)

                for chunk_id, content, meta, dist in zip(ids, docs, metas, distances):
                    # Chroma cosine distance is in [0, 2], similarity is 1 - (dist / 2)
                    similarity = max(0.0, min(1.0, 1.0 - (dist / 2.0)))
                    hits.append({
                        "id": chunk_id,
                        "content": content,
                        "metadata": meta,
                        "score": similarity
                    })

            return hits
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {str(e)}", exc_info=True)
            return []

vector_store_service = VectorStoreService()
