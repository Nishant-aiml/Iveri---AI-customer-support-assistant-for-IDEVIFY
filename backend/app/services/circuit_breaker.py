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

    def __init__(self, default_threshold: float = 0.50):
        self.default_threshold = default_threshold

    def evaluate(
        self,
        fused_chunks: List[Dict[str, Any]],
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """Evaluates whether the retrieved context contains sufficient confidence to answer."""
        cutoff = threshold if threshold is not None else self.default_threshold

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

        # 2. Check if at least one engine had meaningful signal
        # Either RRF score exceeds threshold OR strong direct dense/sparse match
        has_confident_match = (
            top_score >= cutoff or 
            dense_sim >= 0.55 or 
            sparse_score >= 0.60
        )

        if not has_confident_match:
            logger.info(
                f"Circuit breaker tripped: Top score {top_score:.3f} (dense={dense_sim:.3f}, sparse={sparse_score:.3f}) "
                f"is below threshold {cutoff:.3f}."
            )
            return {
                "can_answer": False,
                "confidence": round(top_score, 4),
                "reason": "low_confidence_score"
            }

        return {
            "can_answer": True,
            "confidence": round(top_score, 4),
            "reason": "confident_match"
        }

circuit_breaker = PreLLMCircuitBreaker()
