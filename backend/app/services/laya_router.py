import logging
import os
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)

class LayaClassifierService:
    """Non-autoregressive System 1 Semantic Router & Guardrail.
    
    Optimized for Render Free Tier (512MB RAM ceiling; memory footprint < 1MB).
    Provides sub-millisecond deterministic intent classification and out-of-scope filtering.
    """

    def __init__(self):
        # Neural weights disabled by default to keep container memory ~120MB (well below 512MB limit)
        self._enable_neural = os.getenv("ENABLE_LAYA_NEURAL", "false").lower() in ("true", "1", "yes")
        self._router = None
        self._is_available = False

        # Fast deterministic regex patterns for zero-shot intent routing
        self._out_of_scope_patterns = [
            re.compile(r"\b(what\s+is\s+ai|artificial\s+intelligence|machine\s+learning|deep\s+learning)\b", re.IGNORECASE),
            re.compile(r"\b(tell\s+(me\s+)?about\s+(ai|bm25|quantum|neural|blockchain|crypto))\b", re.IGNORECASE),
            re.compile(r"\b(write\s+(a\s+)?(python|javascript|code|script|essay|poem|sql))\b", re.IGNORECASE),
            re.compile(r"\b(c-section|surgery|medical\s+procedure|diagnose|prescription|symptoms)\b", re.IGNORECASE),
            re.compile(r"\b(weather\s+in|who\s+won|president\s+of|capital\s+of|tell\s+a\s+joke)\b", re.IGNORECASE),
            re.compile(r"\b(book\s+(me\s+)?(a\s+)?(flight|hotel|ticket\s+to))\b", re.IGNORECASE),
        ]

        self._greeting_patterns = [
            re.compile(r"^(hello|hi|hey|good\s+(morning|afternoon|evening)|greetings|howdy)\b", re.IGNORECASE),
            re.compile(r"^(thanks|thank\s+you|bye|goodbye|see\s+ya)\b", re.IGNORECASE),
        ]

        if self._enable_neural:
            self._init_neural_router()
        else:
            logger.info("LayaClassifierService running in high-speed deterministic pattern mode (<1MB RAM).")

    def _init_neural_router(self):
        try:
            from laya import Router
            self._router = Router()
            self._is_available = True
            logger.info("Laya neural ModernBERT router loaded successfully.")
        except Exception as e:
            logger.warning(f"Laya neural router unavailable ({e}). Falling back to pattern mode.")
            self._is_available = False
            self._router = None

    def classify_intent(self, query: str) -> Dict[str, Any]:
        """Classifies incoming query intent with zero token cost and sub-millisecond latency."""
        if not query or not query.strip():
            return {"available": True, "intent": "store_support", "confidence": 0.5}

        clean_q = query.strip().lower()

        # Check out-of-scope queries
        for pattern in self._out_of_scope_patterns:
            if pattern.search(clean_q):
                return {
                    "available": True,
                    "intent": "out_of_scope",
                    "confidence": 0.95,
                    "probabilities": {"out_of_scope": 0.95, "store_support": 0.05}
                }

        # Check conversational greetings (guarding against interrogatives)
        if not any(clean_q.startswith(w) for w in ["what", "how", "why", "who", "where", "which", "when", "can you explain", "explain"]):
            for pattern in self._greeting_patterns:
                if pattern.search(clean_q):
                    return {
                        "available": True,
                        "intent": "greeting",
                        "confidence": 0.95,
                        "probabilities": {"greeting": 0.95, "store_support": 0.05}
                    }

        # If neural router explicitly enabled and initialized
        if self._router and self._is_available:
            try:
                schema = {
                    "intent": {
                        "type": "choice",
                        "instructions": "Determine if the user query is about store support, greeting, or out of scope.",
                        "criteria": {
                            "store_support": "questions specifically about store policies, products, catalogs, broadband, equipment, plans, pricing, fees, charges, bills, outages, cancellation, returns, refunds, warranties, shipping, hours, contact info",
                            "out_of_scope": "what is ai, coding, medical procedures, weather, general trivia, politics, sports",
                            "greeting": "conversational greetings like hello, hi, hey, good morning, thanks, bye"
                        }
                    }
                }
                res = self._router.predict(query, schema)
                answers = res.get("answers", {}).get("intent", {})
                choice = answers.get("choice", "store_support")
                confidence = answers.get("answer_confidence", 0.0)
                return {
                    "available": True,
                    "intent": choice,
                    "confidence": float(confidence),
                    "probabilities": answers.get("probabilities", {})
                }
            except Exception as e:
                logger.warning(f"Laya neural prediction failed: {e}")

        # Default: domain store support query
        return {
            "available": True,
            "intent": "store_support",
            "confidence": 0.85,
            "probabilities": {"store_support": 0.85, "out_of_scope": 0.15}
        }

laya_service = LayaClassifierService()
