import re
from typing import Dict, Set

class TopicAnalyzer:
    """Classifies customer inquiries into core business topics for dashboard intelligence."""

    TOPIC_KEYWORDS: Dict[str, Set[str]] = {
        "pricing": {
            "price", "prices", "pricing", "cost", "costs", "rs", "rupees", "rate", "rates",
            "discount", "discounts", "offer", "coupon", "gst", "expensive", "cheap", "charge", "fees"
        },
        "shipping": {
            "shipping", "ship", "deliver", "delivery", "courier", "dispatch", "track", "tracking",
            "transit", "arrive", "arrival", "pune", "speed", "freight", "express"
        },
        "returns": {
            "return", "returns", "refund", "refunds", "exchange", "replacement", "replace",
            "damaged", "broken", "wrong", "cancel", "cancellation", "warranty", "policy"
        },
        "products": {
            "product", "products", "item", "items", "catalog", "coffee", "roast", "beans",
            "cold brew", "grinder", "dripper", "blend", "size", "weight", "medium", "dark", "ceramic"
        },
        "support": {
            "support", "contact", "email", "phone", "call", "help", "helpline", "timings",
            "hours", "address", "location", "office", "headquarters", "customer care"
        }
    }

    @classmethod
    def classify(cls, text: str) -> str:
        """Classifies text into primary topic: pricing, shipping, returns, products, support, or general."""
        clean_text = text.lower()
        words = set(re.findall(r"\b[a-z0-9]+\b", clean_text))

        scores = {topic: 0 for topic in cls.TOPIC_KEYWORDS}
        for topic, keywords in cls.TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in words or (len(kw) > 4 and kw in clean_text):
                    scores[topic] += 1

        top_topic = max(scores, key=scores.get)
        if scores[top_topic] > 0:
            return top_topic

        return "general"

topic_analyzer = TopicAnalyzer()
