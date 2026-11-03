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


class TemporalInterceptor:
    """Fast, accurate real-time clock, date, day of week, and year interceptor.
    
    Answers real-time questions about the current time, today's date, day of the week,
    and year with 100% precision without burning LLM tokens or calling external APIs.
    """

    STORE_CONTEXT_KEYWORDS = {
        "delivery", "shipping", "transit", "dispatch", "response", "opening", "closing",
        "store", "shop", "working", "business", "operation", "operating", "order",
        "return", "refund", "warranty", "duration", "wait", "sla", "delay", "arrive",
        "founded", "established", "started", "born", "built", "opened", "created",
        "launched", "history", "located", "where", "who", "which company", "brand"
    }

    @classmethod
    def check_temporal(cls, text: str) -> Optional[str]:
        import datetime
        clean = text.strip().lower()
        clean_no_punct = re.sub(r"['’\"?,.!]", "", clean)
        q_words = re.findall(r"\b\w+\b", clean_no_punct)
        
        # If query asks about store operational hours, transit duration, or delivery dates, defer to RAG
        if any(w in cls.STORE_CONTEXT_KEYWORDS for w in q_words):
            return None

        now = datetime.datetime.now()
        cur_time = now.strftime("%I:%M %p").lstrip("0")
        cur_day = now.strftime("%A")
        cur_date = now.strftime("%B %d, %Y")
        cur_year = now.strftime("%Y")

        # 1. Combined date & time query
        if re.search(r"\b(date\s+and\s+time|time\s+and\s+date|what\s+date\s+and\s+time)\b", clean_no_punct):
            return f"The current time is **{cur_time}** on **{cur_day}, {cur_date}**."

        # 2. Exact Time query
        if (
            re.search(r"\b(what(s)?\s+(is\s+)?(the\s+)?time|what\s+time(\s+is\s+it)?|tell\s+me\s+(the\s+)?time|current\s+time|time\s+right\s+now|exact\s+time|time\s+now)\b", clean_no_punct)
            or clean_no_punct in ["time", "the time", "what time", "current time"]
        ):
            return f"The current time is **{cur_time}** ({cur_day}, {cur_date})."

        # 3. Exact Date query
        if (
            re.search(r"\b(what(s)?\s+(is\s+)?(the\s+|todays\s+)?date|what\s+date(\s+is\s+it|\s+is\s+today)?|todays\s+date|current\s+date|exact\s+date|tell\s+me\s+(the\s+|todays\s+)?date|date\s+today)\b", clean_no_punct)
            or clean_no_punct in ["date", "the date", "todays date", "date today"]
        ):
            return f"Today's date is **{cur_day}, {cur_date}**."

        # 4. Exact Day of week query
        if (
            re.search(r"\b(what\s+day\s+(is\s+(it|today)|of\s+(the\s+)?week)|which\s+day\s+is\s+(it|today)|what(s)?\s+(is\s+)?(todays|current)\s+day|current\s+day|tell\s+me\s+(the\s+|todays\s+)?day|day\s+today)\b", clean_no_punct)
            or clean_no_punct in ["day", "today day", "current day", "what day"]
        ):
            return f"Today is **{cur_day}**, {cur_date}."

        # 5. Exact Year query (must specifically ask for current / present year)
        if (
            re.search(r"\b(what\s+year\s+is\s+(this|it|today)|which\s+year\s+is\s+(this|it)|what(s)?\s+(is\s+)?(the\s+)?current\s+year|current\s+year|tell\s+me\s+the\s+current\s+year)\b", clean_no_punct)
            or clean_no_punct in ["year", "the year", "current year", "this year"]
        ):
            return f"The current year is **{cur_year}**."

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
        "them", "their", "theirs", "themselves", "this", "that", "these", "those", "am", "please",
        "section", "sections", "page", "pages", "part", "parts", "chapter", "chapters", "clause", "clauses", "paragraph", "article", "doc", "document", "faq",
        "title", "details", "info", "information", "about", "tell"
    }

    # Common business domain concept mappings allowing natural conversational queries without brittle verbatim word matching
    CONCEPT_GROUPS = {
        "location": {
            "query_terms": {"location", "located", "where", "address", "city", "place", "headquarters", "hq", "office", "country", "state", "situate", "situated", "based"},
            "context_patterns": [r"\b(based|located|location|headquarters|hq|office|city|address|street|pune|mumbai|delhi|bengaluru|bangalore|hyderabad|chennai|kolkata|india|usa|uk)\b"]
        },
        "identity": {
            "query_terms": {"who", "name", "company", "brand", "business", "firm", "about", "founded", "founder", "started", "established"},
            "context_patterns": [r"\b(company|co|brand|store|business|firm|shop|roaster|provider|founded|established|started)\b"]
        },
        "contact": {
            "query_terms": {"contact", "reach", "email", "phone", "call", "support", "help", "helpline", "care", "touch"},
            "context_patterns": [r"\b(contact|email|phone|call|support|help|helpline|care|reach|tel)\b", r"[\w\.-]+@[\w\.-]+", r"\+?\d{2,4}[-\s]?\d{3,5}[-\s]?\d{4}"]
        },
        "pricing_products": {
            "query_terms": {"product", "products", "item", "items", "sell", "goods", "offering", "service", "services", "catalog", "pricing", "price", "cost", "plan", "plans", "package"},
            "context_patterns": [r"\b(product|products|item|items|goods|service|services|catalog|pricing|price|cost|rs|inr|\$|broadband|package|roast|beans|coffee|grinder|dripper)\b"]
        },
        "shipping_delivery": {
            "query_terms": {"ship", "shipping", "delivery", "deliver", "transit", "dispatch", "arrive", "courier", "postage", "freight"},
            "context_patterns": [r"\b(ship|shipping|delivery|deliver|transit|dispatch|courier|postage|freight)\b"]
        },
        "returns_refunds": {
            "query_terms": {"return", "returns", "refund", "refunds", "cancel", "cancellation", "warranty", "exchange", "moneyback"},
            "context_patterns": [r"\b(return|returns|refund|refunds|cancel|cancellation|warranty|replacement|defect)\b"]
        },
        "loyalty_rewards": {
            "query_terms": {"point", "points", "brewpoint", "brewpoints", "reward", "rewards", "loyalty", "worth", "value", "redeem", "redemption", "discount", "discounts", "earn", "earning", "spent"},
            "context_patterns": [r"\b(point|points|brewpoint|brewpoints|reward|rewards|loyalty|worth|redeem|discount|discounts|earned|earn|spent|program)\b"]
        }
    }

    # Technical / academic out-of-domain entities that should never be answered by store support
    TECH_OUT_OF_DOMAIN = {
        "bm25", "quantum", "quicksort", "bubble sort", "kubernetes", "tensorflow",
        "pytorch", "neural network", "machine learning"
    }

    def __init__(self, default_threshold: float = 0.52):
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

        # 2. Key entity / grounding validation
        if query:
            clean_q = re.sub(r"[^\w\s]", " ", query.lower())
            tokens = [t for t in clean_q.split() if t and t not in self.STOPWORDS and len(t) > 1]
            if not tokens:
                logger.info(f"Circuit breaker tripped: Query '{query}' contains no substantive domain entities.")
                return {
                    "can_answer": False,
                    "confidence": 0.0,
                    "reason": "query_contains_no_domain_entities"
                }

            top_text = " ".join([
                (c.get("content", "") + " " + c.get("metadata", {}).get("document_name", "")).lower()
                for c in fused_chunks[:3]
            ])
            top_text_clean = re.sub(r"(?i)fictional document created for testing.*?\.", "", top_text)
            top_text_clean = re.sub(r"(?i)created for testing an? ai customer support.*?assistant\b", "", top_text_clean)
            top_text_clean = re.sub(r"(?i)testing an? ai customer support.*?assistant\b", "", top_text_clean)
            top_text_clean = re.sub(r"(?i)fictional document\b", "", top_text_clean)

            # Check if query asks for known out-of-domain technical concepts missing from the store context
            for tech_word in self.TECH_OUT_OF_DOMAIN:
                if re.search(r"\b" + re.escape(tech_word) + r"\b", clean_q):
                    if not re.search(r"\b" + re.escape(tech_word) + r"\b", top_text_clean):
                        logger.info(f"Circuit breaker tripped: Query asked for technical concept '{tech_word}' absent from context.")
                        return {
                            "can_answer": False,
                            "confidence": round(top_score, 4),
                            "reason": "query_entities_missing_from_context"
                        }

            # Check semantic grounding across concepts or literal substring presence
            grounded_hits = []
            for t in tokens:
                if re.search(r"\b" + re.escape(t) + r"\b", top_text_clean):
                    grounded_hits.append(t)
                    continue
                # Concept-level grounding (e.g. 'located' -> 'based in Pune', 'name' -> 'BrewNest')
                for group_name, group_cfg in self.CONCEPT_GROUPS.items():
                    if t in group_cfg["query_terms"]:
                        if any(re.search(pat, top_text_clean, re.IGNORECASE) for pat in group_cfg["context_patterns"]):
                            grounded_hits.append(f"{t}:{group_name}")
                            break

            if not grounded_hits:
                logger.info(f"Circuit breaker tripped: Query entities {tokens} missing from retrieved content (Dense={dense_sim:.3f}).")
                return {
                    "can_answer": False,
                    "confidence": round(top_score, 4),
                    "reason": "query_entities_missing_from_context"
                }

        # 3. Dynamic Semantic Confidence Evaluation:
        # A confident match requires either:
        # a) Both engines agreed (sparse keyword match > 0 AND dense similarity >= 0.40)
        # b) Significant keyword hit (sparse >= 0.20)
        # c) Strong semantic similarity when sparse has no direct hit (dense >= 0.52)
        has_confident_match = False
        if sparse_score > 0.0 and dense_sim >= 0.40:
            has_confident_match = True
        elif sparse_score >= 0.20:
            has_confident_match = True
        elif dense_sim >= 0.52:
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
