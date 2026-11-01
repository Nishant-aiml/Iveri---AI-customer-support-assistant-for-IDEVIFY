import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class HybridRAGEngine:
    """Multi-Hybrid Retrieval-Augmented Generation Engine.
    
    Combines:
    1. Dense Vector Store (ChromaDB with tenant metadata filtering)
    2. Sparse Lexical Search (rank-bm25 index per business)
    3. Reciprocal Rank Fusion (RRF)
    4. Deterministic Pre-LLM Confidence Circuit Breaker
    5. Multi-Tier LLM Cascade (Gemini Flash -> Groq Llama 3.1 8B)
    """

    def __init__(self):
        self._bm25_indices: Dict[str, Any] = {}
        self._bm25_corpus: Dict[str, List[Dict[str, Any]]] = {}

    async def index_document_chunks(self, business_id: str, chunks: List[Dict[str, Any]]):
        """Indexes extracted document chunks into both Dense (ChromaDB) and Sparse (BM25) stores."""
        if not chunks:
            return

        # 1. Index into ChromaDB Vector Store
        try:
            from app.services.vector_store import vector_store_service
            await vector_store_service.add_chunks(business_id, chunks)
        except Exception as e:
            logger.error(f"Error indexing chunks in vector store: {str(e)}", exc_info=True)

        # 2. Index into Sparse BM25 Store
        try:
            from app.services.bm25_store import bm25_store_service
            bm25_store_service.add_chunks(business_id, chunks)
        except Exception as e:
            logger.error(f"Error indexing chunks in BM25 store: {str(e)}", exc_info=True)

        logger.info(f"RAG Engine indexed {len(chunks)} chunks for business {business_id}.")

    async def delete_document_chunks(self, business_id: str, document_id: str):
        """Removes a document's chunks from both vector and BM25 indices."""
        try:
            from app.services.vector_store import vector_store_service
            await vector_store_service.delete_document(business_id, document_id)
        except Exception as e:
            logger.error(f"Error deleting chunks from vector store: {str(e)}", exc_info=True)

        try:
            from app.services.bm25_store import bm25_store_service
            bm25_store_service.delete_document(business_id, document_id)
        except Exception as e:
            logger.error(f"Error deleting chunks from BM25 store: {str(e)}", exc_info=True)

    async def query(
        self, 
        business_id: str, 
        user_query: str, 
        business_settings: Optional[Dict[str, Any]] = None,
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Processes customer query through Hybrid RAG pipeline."""
        # Will be fully fleshed out in Phase 3
        return {
            "answer": "RAG pipeline initialized.",
            "is_answered": True,
            "confidence_score": 1.0,
            "citations": [],
            "llm_provider": "gemini",
            "latency_ms": 100
        }

rag_engine = HybridRAGEngine()
