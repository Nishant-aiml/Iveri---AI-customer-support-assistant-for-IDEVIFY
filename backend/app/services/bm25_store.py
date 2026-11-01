import re
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class BM25StoreService:
    """In-memory sparse lexical search engine powered by rank-bm25.
    
    Provides ultra-fast exact keyword, SKU, pricing, and acronym retrieval
    partitioned strictly per business tenant.
    """

    def __init__(self):
        # business_id -> List of chunk dicts
        self._corpus: Dict[str, List[Dict[str, Any]]] = {}
        # business_id -> BM25Okapi instance
        self._bm25_models: Dict[str, Any] = {}

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple lowercase word tokenization."""
        return re.findall(r"\w+", text.lower())

    def add_chunks(self, business_id: str, chunks: List[Dict[str, Any]]):
        """Adds chunks to the business's BM25 corpus and updates the index."""
        from rank_bm25 import BM25Okapi

        if business_id not in self._corpus:
            self._corpus[business_id] = []

        # Avoid duplicates
        existing_ids = {c["id"] for c in self._corpus[business_id]}
        for chunk in chunks:
            if chunk["id"] not in existing_ids:
                self._corpus[business_id].append(chunk)

        # Rebuild index
        tokenized_corpus = [self._tokenize(c["content"]) for c in self._corpus[business_id]]
        if tokenized_corpus:
            self._bm25_models[business_id] = BM25Okapi(tokenized_corpus)
            logger.info(f"BM25 index updated for business {business_id} with {len(self._corpus[business_id])} documents.")

    def delete_document(self, business_id: str, document_id: str):
        """Removes all chunks of a specific document and rebuilds the BM25 index."""
        from rank_bm25 import BM25Okapi

        if business_id not in self._corpus:
            return

        self._corpus[business_id] = [
            c for c in self._corpus[business_id] 
            if c.get("metadata", {}).get("document_id") != document_id
        ]

        tokenized_corpus = [self._tokenize(c["content"]) for c in self._corpus[business_id]]
        if tokenized_corpus:
            self._bm25_models[business_id] = BM25Okapi(tokenized_corpus)
        else:
            self._bm25_models.pop(business_id, None)

        logger.info(f"BM25 chunks pruned for document {document_id} in business {business_id}.")

    def search(self, business_id: str, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Searches the business corpus using BM25 lexical ranking."""
        if business_id not in self._bm25_models or business_id not in self._corpus:
            return []

        tokenized_query = self._tokenize(query)
        if not tokenized_query:
            return []

        bm25 = self._bm25_models[business_id]
        corpus = self._corpus[business_id]

        scores = bm25.get_scores(tokenized_query)
        
        # Rank by score descending
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results = []

        max_score = max(scores) if any(s > 0 for s in scores) else 1.0

        for idx in ranked_indices[:top_k]:
            raw_score = scores[idx]
            if raw_score <= 0.0:
                continue

            chunk = corpus[idx]
            results.append({
                "id": chunk["id"],
                "content": chunk["content"],
                "metadata": chunk.get("metadata", {}),
                "score": float(raw_score / max_score)  # Normalized 0..1
            })

        return results

bm25_store_service = BM25StoreService()
