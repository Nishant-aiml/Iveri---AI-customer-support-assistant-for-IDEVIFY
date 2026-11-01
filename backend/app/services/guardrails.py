import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class PromptInjectionGuard:
    """Detects adversarial jailbreak and prompt injection directives before LLM invocation."""

    INJECTION_PATTERNS = [
        # Direct instruction override
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|prompts|directions)",
        r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|prompts)",
        r"forget\s+(all\s+)?(previous|prior|above)\s+(instructions|rules)",
        r"bypass\s+(all\s+)?(safety|security|content|guardrails|filters|rules)",
        
        # System prompt & secret exfiltration
        r"(what\s+is|show\s+me|reveal|output|print|display)\s+(your\s+)?(system\s+prompt|(initial\s+)?instructions|initial\s+prompt|rules|(secret\s+)?api\s+keys|credentials)",
        r"reveal\s+.*(instructions|prompt|api\s*key|secret)",
        r"repeat\s+the\s+words\s+above",
        r"system\s*:\s*",
        r"<\/?(system|instructions|prompt)>",
        
        # Roleplay / Jailbreak personas
        r"you\s+are\s+now\s+(dan|an?\s+unfiltered|jailbroken|unrestricted)",
        r"do\s+anything\s+now",
        r"jailbreak\s+mode",
        r"developer\s+mode\s+(enabled|on)",
        r"act\s+as\s+(an?\s+)?(unfiltered|unrestricted|hacker|dan|developer)",
        r"disregard\w*\s+.*(policies|rules|guidelines|store)"
    ]

    COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

    @classmethod
    def evaluate(cls, query: str) -> Dict[str, Any]:
        """Scans query for prompt injection heuristics.

        Returns safe fallback response if triggered.
        """
        clean = query.strip()

        for pattern in cls.COMPILED_PATTERNS:
            if pattern.search(clean):
                logger.warning(f"Inbound guardrail triggered: detected prompt injection pattern matching '{pattern.pattern}'")
                return {
                    "is_safe": False,
                    "violation": "prompt_injection",
                    "safe_reply": (
                        "I am an AI assistant designed to help answer customer questions strictly "
                        "regarding our products, services, and official store policies. "
                        "How can I assist you with those today?"
                    )
                }

        return {"is_safe": True, "violation": None, "safe_reply": None}


class PIIShield:
    """Redacts sensitive user data (credit cards, SSNs, raw API keys) before processing."""

    PATTERNS = [
        # Credit Card Numbers (13-16 digits with optional spaces or dashes)
        (re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"), "[REDACTED_CREDIT_CARD]"),
        # US Social Security Numbers (XXX-XX-XXXX)
        (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
        # Common API Key Formats (Gemini AIza..., Groq gsk_..., JWT tokens)
        (re.compile(r"\bAIza[0-9A-Za-z-_]{30,}\b"), "[REDACTED_API_KEY]"),
        (re.compile(r"\bgsk_[0-9A-Za-z]{20,}\b"), "[REDACTED_API_KEY]"),
        (re.compile(r"\beyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{30,}\b"), "[REDACTED_TOKEN]")
    ]

    @classmethod
    def redact(cls, text: str) -> str:
        """Masks detected PII and credential tokens."""
        redacted = text
        for pattern, replacement in cls.PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted


class OutboundGuardrail:
    """Verifies that generated model outputs do not leak internal secrets or configurations."""

    LEAK_PATTERNS = [
        re.compile(r"AIza[0-9A-Za-z-_]{30,}", re.IGNORECASE),
        re.compile(r"gsk_[0-9A-Za-z]{20,}", re.IGNORECASE),
        re.compile(r"sqlite\+aiosqlite:\/\/", re.IGNORECASE),
        re.compile(r"super-secret-jwt-key", re.IGNORECASE),
        re.compile(r"Strict Operational Rules:", re.IGNORECASE)
    ]

    @classmethod
    def sanitize(cls, response_text: str, fallback_message: str) -> str:
        """Inspects outbound answer; if secrets or internal prompt headers leaked, masks with fallback."""
        for pattern in cls.LEAK_PATTERNS:
            if pattern.search(response_text):
                logger.error("Outbound guardrail triggered: Model generated text containing internal credentials or prompt rules!")
                return fallback_message
        return response_text


class GuardrailsService:
    """Unified Guardrails entrypoint."""

    def __init__(self, max_query_length: int = 500):
        self.max_query_length = max_query_length
        self.injection_guard = PromptInjectionGuard
        self.pii_shield = PIIShield
        self.outbound_guard = OutboundGuardrail

    def sanitize_input(self, user_query: str) -> str:
        """Cleans control characters and bounds query length."""
        # Trim length
        bounded = user_query[:self.max_query_length].strip()
        # Redact any sensitive PII
        return self.pii_shield.redact(bounded)

    def check_inbound_safety(self, query: str) -> Dict[str, Any]:
        """Runs pre-retrieval safety scan."""
        return self.injection_guard.evaluate(query)

    def check_outbound_safety(self, text: str, fallback_message: str) -> str:
        """Runs post-generation output sanitation."""
        return self.outbound_guard.sanitize(text, fallback_message)

guardrails_service = GuardrailsService()
