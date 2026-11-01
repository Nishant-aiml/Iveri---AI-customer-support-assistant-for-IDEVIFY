from typing import Optional, Tuple

class SentimentAnalyzer:
    """Deterministic sentiment and frustration analysis engine for customer support conversations."""

    POSITIVE_PHRASES = {
        "thank you", "thanks", "great", "awesome", "excellent", "amazing",
        "love", "loved", "superb", "helpful", "wonderful", "perfect",
        "appreciate", "fast delivery", "good job", "best", "satisfied", "pleased"
    }

    NEGATIVE_PHRASES = {
        "scam", "fraud", "worst", "broken", "damaged", "angry", "bad",
        "terrible", "horrible", "disappointed", "useless", "pathetic",
        "complaint", "late", "delay", "waiting for days", "money back",
        "cheated", "ridiculous", "never buy", "cancel order", "refund my money",
        "hate", "sucks", "awful", "failed", "unacceptable", "wrong item"
    }

    @classmethod
    def analyze(cls, text: str, feedback: Optional[str] = None) -> Tuple[str, float]:
        """Analyzes text sentiment and returns (label, score).
        
        Args:
            text: Customer message text
            feedback: Optional explicit customer reaction ('up' or 'down')
            
        Returns:
            Tuple[str, float]: (sentiment_label: 'positive' | 'neutral' | 'negative', score: -1.0 to 1.0)
        """
        if feedback == "down":
            return "negative", -0.85
        if feedback == "up":
            return "positive", 0.85

        clean_text = text.lower()

        pos_matches = 0
        neg_matches = 0

        # Check multi-word phrases and single words
        for phrase in cls.POSITIVE_PHRASES:
            if phrase in clean_text:
                pos_matches += 1

        for phrase in cls.NEGATIVE_PHRASES:
            if phrase in clean_text:
                neg_matches += 1.5

        if neg_matches > 0 and neg_matches >= pos_matches:
            score = -min(1.0, 0.4 + (neg_matches * 0.2))
            return "negative", round(score, 2)
        elif pos_matches > 0 and pos_matches > neg_matches:
            score = min(1.0, 0.4 + (pos_matches * 0.2))
            return "positive", round(score, 2)
        else:
            return "neutral", 0.0

sentiment_analyzer = SentimentAnalyzer()
