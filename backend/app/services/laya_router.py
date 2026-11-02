import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class LayaClassifierService:
    """Non-autoregressive System 1 Semantic Router & Guardrail powered by Laya (convaiinnovations/laya).
    
    Provides sub-100ms deterministic zero-shot classification over structured question schemas.
    Serves as an upfront neural firewall before dense/sparse vector retrieval:
    1. Rejects out-of-scope queries (medical, coding, general trivia) with zero token cost.
    2. Identifies customer smalltalk/greetings for instant zero-latency responses.
    3. Categorizes domain support intents (plans, equipment, billing, outages, policies).
    """

    def __init__(self):
        self._router = None
        self._is_available = None
        self._schema = {
            "intent": {
                "type": "choice",
                "instructions": "Determine if the user query is about customer store support, a greeting, or completely out of scope.",
                "criteria": {
                    "store_support": "questions about broadband, internet, wifi, router, equipment, plans, pricing, fees, charges, gst, bills, installation, outage, speed, cancellation, returns, warranties, store policy, what is the product, about store",
                    "out_of_scope": "medical procedures like c-section, medical surgery, health, diseases, doctors, artificial intelligence, python programming, coding, weather, general trivia, politics, sports",
                    "greeting": "hello, hi, hey, good morning, thanks, thank you, bye, goodbye"
                }
            }
        }

    def _get_router(self):
        if self._is_available is False:
            return None
        if self._router is None:
            try:
                from laya import Router
                self._router = Router()
                self._is_available = True
                logger.info("LayaClassifierService initialized successfully.")
            except Exception as e:
                logger.warning(f"Laya router unavailable ({e}). Using rule-based fallback.")
                self._is_available = False
                self._router = None
        return self._router

    def classify_intent(self, query: str) -> Dict[str, Any]:
        """Classifies incoming query intent using Laya ModernBERT neural router."""
        router = self._get_router()
        if not router:
            return {"available": False, "intent": "unknown", "confidence": 0.0}

        try:
            res = router.predict(query, self._schema)
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
            logger.warning(f"Laya prediction failed for query '{query}': {e}")
            return {"available": False, "intent": "unknown", "confidence": 0.0}

laya_service = LayaClassifierService()
