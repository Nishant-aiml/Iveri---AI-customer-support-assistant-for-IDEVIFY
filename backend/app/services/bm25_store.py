import re
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class BM25StoreService:
    """In-memory sparse lexical search engine powered by rank-bm25 (BM25Plus).
    
    BM25Plus prevents negative IDF penalties on small corpuses, providing
    reliable keyword, SKU, pricing, and acronym retrieval per business tenant.
    """

    def __init__(self):
        # business_id -> List of chunk dicts
        self._corpus: Dict[str, List[Dict[str, Any]]] = {}
        # business_id -> BM25Plus instance
        self._bm25_models: Dict[str, Any] = {}
        # business_id -> Cached vocabulary set
        self._vocab_cache: Dict[str, set] = {}

    ENGLISH_STOPWORDS = {
        "a", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
        "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
        "by", "can", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for",
        "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
        "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
        "me", "more", "most", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only",
        "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should",
        "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves", "then",
        "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up",
        "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why",
        "will", "with", "you", "your", "yours", "yourself", "yourselves"
    }

    SYNONYM_MAP = {
        "company": ["co", "brand", "store", "business", "brewnest", "zephyr"],
        "co": ["company", "business"],
        "subscription": ["club", "membership"],
        "damaged": ["defect", "broken", "wrong"],
        "pricing": ["price", "cost", "rates"],
        "product": ["plan", "plans", "broadband", "service", "services", "package", "packages", "item", "items", "pricing", "catalog"],
        "products": ["plan", "plans", "broadband", "service", "services", "package", "packages", "items", "pricing", "catalog"],
        "equipment": ["router", "modem", "device", "hardware", "cable", "cables", "installation"],
        "plan": ["product", "broadband", "package", "service"],
        "plans": ["products", "broadband", "packages", "services"],
    }

    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        """Stopword-filtered lowercase tokenization for high-fidelity lexical matching."""
        words = re.findall(r"\w+", text.lower())
        meaningful = [w for w in words if w not in cls.ENGLISH_STOPWORDS and len(w) > 1]
        return meaningful if meaningful else words

    def add_chunks(self, business_id: str, chunks: List[Dict[str, Any]]):
        """Adds chunks to the business's BM25 corpus and updates the index."""
        from rank_bm25 import BM25Plus

        if business_id not in self._corpus:
            self._corpus[business_id] = []

        # Avoid duplicates
        existing_ids = {c["id"] for c in self._corpus[business_id]}
        for chunk in chunks:
            if chunk["id"] not in existing_ids:
                self._corpus[business_id].append(chunk)

        # Invalidate vocabulary cache
        self._vocab_cache.pop(business_id, None)

        # Rebuild index using BM25Plus
        tokenized_corpus = [self._tokenize(c["content"]) for c in self._corpus[business_id]]
        if tokenized_corpus:
            self._bm25_models[business_id] = BM25Plus(tokenized_corpus)
            logger.info(f"BM25Plus index updated for business {business_id} with {len(self._corpus[business_id])} documents.")

    def delete_document(self, business_id: str, document_id: str):
        """Removes all chunks of a specific document and rebuilds the BM25 index."""
        from rank_bm25 import BM25Plus

        if business_id not in self._corpus:
            return

        self._corpus[business_id] = [
            c for c in self._corpus[business_id] 
            if c.get("metadata", {}).get("document_id") != document_id
        ]

        tokenized_corpus = [self._tokenize(c["content"]) for c in self._corpus[business_id]]
        if tokenized_corpus:
            self._bm25_models[business_id] = BM25Plus(tokenized_corpus)
        else:
            self._bm25_models.pop(business_id, None)

        logger.info(f"BM25 chunks pruned for document {document_id} in business {business_id}.")

    def delete_business(self, business_id: str):
        """Purges all corpus records and BM25 index for a deleted business."""
        self._corpus.pop(business_id, None)
        self._bm25_models.pop(business_id, None)
        self._vocab_cache.pop(business_id, None)
        logger.info(f"BM25 pruned all records for deleted business {business_id}.")

    def search(self, business_id: str, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Searches the business corpus using BM25Plus lexical ranking."""
        if business_id not in self._bm25_models or business_id not in self._corpus:
            return []

        tokenized_query = self._tokenize(query)
        if not tokenized_query:
            return []

        # Add domain synonyms to query tokens
        expanded_query = list(tokenized_query)
        for tok in tokenized_query:
            if tok in self.SYNONYM_MAP:
                expanded_query.extend(self.SYNONYM_MAP[tok])

        bm25 = self._bm25_models[business_id]
        corpus = self._corpus[business_id]

        scores = bm25.get_scores(expanded_query)
        
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

    def get_vocabulary(self, business_id: str) -> set:
        """Returns cached set of unique words in business corpus for sub-millisecond query typo correction."""
        if business_id not in self._corpus:
            return set()
        if business_id in self._vocab_cache:
            return self._vocab_cache[business_id]
        words = set()
        for c in self._corpus[business_id]:
            for w in re.findall(r"[a-zA-Z]{3,}", c.get("content", "").lower()):
                words.add(w)
        self._vocab_cache[business_id] = words
        return words

    async def warmup_from_db(self):
        """Hydrates in-memory BM25Plus models from relational database on server startup."""
        try:
            from app.database import AsyncSessionLocal
            from app.models.document import DocumentChunk
            from sqlalchemy.future import select

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(DocumentChunk))
                chunks = result.scalars().all()

            biz_map: Dict[str, List[Dict[str, Any]]] = {}
            for c in chunks:
                bid = c.business_id
                if bid not in biz_map:
                    biz_map[bid] = []
                biz_map[bid].append({
                    "id": c.id,
                    "content": c.content,
                    "metadata": {
                        "document_id": c.document_id,
                        "chunk_index": c.chunk_index,
                        "page_number": c.page_number
                    }
                })

            for bid, c_list in biz_map.items():
                self.add_chunks(bid, c_list)

            logger.info(f"BM25StoreService warmed up {len(chunks)} chunks across {len(biz_map)} businesses from database.")
        except Exception as e:
            logger.warning(f"BM25StoreService warmup failed: {str(e)}")

bm25_store_service = BM25StoreService()
