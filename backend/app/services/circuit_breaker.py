import re
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class GreetingInterceptor:
    """Fast regex-based filter for conversational small talk.
    
    Prevents burning expensive LLM tokens or running heavy RAG on simple greetings
    like 'hello', 'hi', or 'thank you'.
    """

    GREETING_PATTERNS = [
        r"^(hi|hello|hey|hola|namaste|good\s+(morning|afternoon|evening)|howdy)\b",
        r"^(thanks|thank\s+you|thx|much\s+appreciated)\b",
        r"^(bye|goodbye|see\s+you|take\s+care)\b"
    ]

    @classmethod
    def check_greeting(cls, text: str, business_name: str = "our store") -> Optional[str]:
        clean = text.strip().lower()

        # Check general greetings
        if re.search(cls.GREETING_PATTERNS[0], clean):
            return f"Hello! Welcome to {business_name}. How can I assist you today with our products, policies, or services?"

        # Check gratitude
        if re.search(cls.GREETING_PATTERNS[1], clean):
            return f"You're very welcome! Let me know if you have any other questions about {business_name}."

        # Check farewells
        if re.search(cls.GREETING_PATTERNS[2], clean):
            return f"Thank you for contacting {business_name}! Have a wonderful day ahead."

        return None


class PreLLMCircuitBreaker:
    """Deterministic Pre-LLM confidence gate.
    
    Evaluates fused retrieval scores before invoking an LLM API.
    If match confidence is below the threshold, the LLM call is bypassed entirely:
    - 0 LLM tokens consumed
    - Response returned in <10ms
    - 0% risk of AI hallucination
    """

    STOPWORDS = {
        "tell", "show", "give", "what", "when", "where", "which", "who", "why", "how",
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
        "did", "can", "could", "will", "would", "shall", "should", "may", "might", "must",
        "the", "a", "an", "and", "or", "but", "if", "because", "as", "until", "while", "of",
        "at", "by", "for", "with", "about", "against", "between", "into", "through", "during",
        "before", "after", "above", "below", "to", "from", "up", "down", "in", "out", "on",
        "off", "over", "under", "again", "further", "then", "once", "here", "there", "all",
        "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor",
        "not", "only", "own", "same", "so", "than", "too", "very", "me", "my", "myself", "we",
        "our", "ours", "ourselves", "you", "your", "yours", "yourself", "yourselves", "he",
        "him", "his", "himself", "she", "her", "hers", "herself", "it", "its", "itself", "they",
        "them", "their", "theirs", "themselves", "this", "that", "these", "those", "am", "please"
    }

    PRODUCT_SYNONYMS = {
        "product", "products", "item", "items", "plan", "plans", "package", "packages",
        "service", "services", "catalog", "pricing", "broadband"
    }

    def __init__(self, default_threshold: float = 0.55):
        self.default_threshold = default_threshold

    def evaluate(
        self,
        fused_chunks: List[Dict[str, Any]],
        threshold: Optional[float] = None,
        query: Optional[str] = None
    ) -> Dict[str, Any]:
        """Evaluates whether the retrieved context contains sufficient confidence to answer."""
        # 1. Zero chunks found
        if not fused_chunks:
            logger.info("Circuit breaker tripped: Zero matching chunks found across Dense and Sparse indices.")
            return {
                "can_answer": False,
                "confidence": 0.0,
                "reason": "no_matching_chunks"
            }

        top_chunk = fused_chunks[0]
        top_score = top_chunk.get("rrf_score", 0.0)
        dense_sim = top_chunk.get("dense_similarity", 0.0)
        sparse_score = top_chunk.get("sparse_score", 0.0)

        # 2. Key entity / keyword grounding validation
        if query:
            clean_q = re.sub(r"[^\w\s]", " ", query.lower())
            tokens = [t for t in clean_q.split() if t and t not in self.STOPWORDS and len(t) > 1]
            if tokens:
                top_text = " ".join([c.get("content", "").lower() for c in fused_chunks[:3]])
                # Filter out boilerplate test disclaimers from entity matching
                top_text_clean = re.sub(r"(?i)fictional document created for testing.*?\.", "", top_text)
                
                entity_hits = []
                for t in tokens:
                    if t in self.PRODUCT_SYNONYMS and any(re.search(r"\b" + re.escape(syn) + r"\b", top_text_clean) for syn in self.PRODUCT_SYNONYMS):
                        entity_hits.append(t)
                    elif re.search(r"\b" + re.escape(t) + r"\b", top_text_clean):
                        entity_hits.append(t)

                # If query entities (e.g. 'ai', 'bm25') have 0 genuine mentions in retrieved chunks
                if not entity_hits:
                    logger.info(f"Circuit breaker tripped: Query entities {tokens} missing from retrieved content (Dense={dense_sim:.3f}).")
                    return {
                        "can_answer": False,
                        "confidence": round(top_score, 4),
                        "reason": "query_entities_missing_from_context"
                    }

        # 3. Strict Confidence Evaluation:
        # A confident match requires either:
        # a) Both engines agreed (sparse keyword match > 0 AND dense similarity >= 0.44)
        # b) Significant keyword hit (sparse >= 0.20)
        # c) High semantic similarity when sparse has no direct hit (dense >= 0.62)
        has_confident_match = False
        if sparse_score > 0.0 and dense_sim >= 0.44:
            has_confident_match = True
        elif sparse_score >= 0.20:
            has_confident_match = True
        elif dense_sim >= 0.62:
            has_confident_match = True

        if not has_confident_match:
            logger.info(
                f"Circuit breaker tripped: Dense={dense_sim:.3f}, Sparse={sparse_score:.3f}, "
                f"RRF={top_score:.3f} failed confidence criteria."
            )
            return {
                "can_answer": False,
                "confidence": round(top_score, 4),
                "reason": "insufficient_confidence_and_keyword_overlap"
            }

        return {
            "can_answer": True,
            "confidence": round(top_score, 4),
            "reason": "confident_match"
        }

circuit_breaker = PreLLMCircuitBreaker()
