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
        """Computes dense vector embeddings using Google Gemini (or local fallback)."""
        if not texts:
            return []

        # 1. Google Gemini Embeddings (Primary Free Tier)
        if settings.GEMINI_API_KEY:
            try:
                embeddings = []
                url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents?key={settings.GEMINI_API_KEY}"
                
                requests_payload = [
                    {"model": "models/text-embedding-004", "content": {"parts": [{"text": t[:2048]}]}}
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
                        logger.warning(f"Gemini embedding API returned {resp.status_code}. Using fallback embedding...")
            except Exception as e:
                logger.warning(f"Gemini embedding call failed ({str(e)}). Using fallback embedding...")

        # 2. Local Semantic ONNX all-MiniLM-L6-v2 Embeddings (True Cosine Similarity)
        try:
            from chromadb.utils import embedding_functions
            default_ef = embedding_functions.DefaultEmbeddingFunction()
            embeddings = default_ef(texts)
            return [list(map(float, emb)) for emb in embeddings]
        except Exception as e:
            logger.warning(f"Chroma ONNX embedding failed ({str(e)}). Using deterministic fallback...")

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

    async def add_chunks(self, business_id: str, chunks: List[Dict[str, Any]]):
        """Generates embeddings and inserts chunks into ChromaDB with tenant metadata."""
        if not chunks:
            return

        ids = [c["id"] for c in chunks]
        texts = [c["content"] for c in chunks]
        metadatas = []

        for c in chunks:
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
        logger.info(f"ChromaDB indexed {len(ids)} chunks for business {business_id}.")

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
