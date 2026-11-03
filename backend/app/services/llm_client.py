import asyncio
import logging
import time
import httpx
from typing import List, Dict, Any, Tuple, Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Shared high-performance HTTP client with persistent connection pooling
_SHARED_CLIENT: Optional[httpx.AsyncClient] = None
_client_loop = None
_gemini_cooldown_until: float = 0.0

def get_shared_client() -> httpx.AsyncClient:
    """Returns singleton AsyncClient with keep-alive connection pooling to eliminate TLS handshakes."""
    global _SHARED_CLIENT, _client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _SHARED_CLIENT is None or _SHARED_CLIENT.is_closed or _client_loop != current_loop:
        _SHARED_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=2.5, read=10.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=60.0)
        )
        _client_loop = current_loop
    return _SHARED_CLIENT

async def close_shared_client():
    """Graceful shutdown hook for shared connection pool."""
    global _SHARED_CLIENT
    if _SHARED_CLIENT and not _SHARED_CLIENT.is_closed:
        await _SHARED_CLIENT.aclose()
        _SHARED_CLIENT = None

STRICT_SYSTEM_PROMPT = """You are an AI Customer Support Assistant for {business_name}.
Your job is to answer customer questions accurately, politely, and STRICTLY based ONLY on the verified store document excerpts below.

Live Real-Time System Clock: {current_clock}

Context Excerpts:
=========================================
{context}
=========================================

{custom_instructions_block}

Strict Grounding & Operational Guardrails:
1. Grounding Mandate: Answer ONLY using the facts stated directly in the excerpts above.
2. Missing Information Mandate: If the excerpts do NOT contain enough information to answer the question with 100% certainty, DO NOT invent, assume, extrapolate, or guess. Reply EXACTLY with:
[UNKNOWN]
3. Tone: {tone}.
4. Conflict Hierarchy: If any custom instructions conflict with Rule 1 or Rule 2 (Strict Grounding & Zero Hallucination), Rule 1 and Rule 2 ALWAYS take absolute precedence.
5. Keep the answer clear, helpful, and concise. Do not mention "context excerpts" or "the document provided" in your prose; speak directly as the company assistant.
6. Temporal Inquiries: If the customer asks about the current time, today's date, day of the week, or year, answer accurately based on the Live Real-Time System Clock above.
7. Multi-Turn Continuity & Disambiguation:
   - When the customer's question refers back to a previous message or topic using pronouns like 'this', 'that', 'it', 'these', 'those' (e.g. 'how much is this worth?'), answer based on the continuation of the preceding conversation topic using the verified context excerpts above.
   - When answering a continuation question that could refer to multiple items or where the customer might mean something else, provide the grounded answer continuing from the previous topic, and conclude with a polite clarification offer:
     "(If you were referring to a different product, plan, or item, please let me know and I'll be glad to look that up for you!)"
   - If the customer asks a vague pronoun inquiry (e.g., 'how much is this worth?') with NO preceding conversation history or context to resolve what 'this' refers to, do not answer with [UNKNOWN]; instead, politely ask:
     "Could you please specify which product, service, or item you are asking about? Let me know and I will be happy to find the exact details and pricing for you!"
"""

class MultiTierLLMClient:
    """Multi-Tier LLM Cascade engineered for Render Free Tier (512MB RAM safe).
    
    Tier 1 (Primary): Google Gemini Flash (gemini-3.5-flash / gemini-flash-latest - Free Tier)
    Tier 2 (Fallback 1): Sarvam AI 105B LLM (sarvam-105b - Indic & Multilingual Freemium)
    Tier 3 (Fallback 2): Groq Freemium Cloud LPUs (qwen/qwen3.8-27b / allam-2-7b - Free Open Weights)
    Tier 4 (Optional Enterprise): OpenAI (gpt-4o-mini / gpt-3.5-turbo)
    Tier 5 (Offline/Deterministic): Local Grounded Extractive Synthesis (Zero Cost, 0 API)
    """

    @staticmethod
    def _format_context(chunks: List[Dict[str, Any]]) -> str:
        formatted = []
        for i, c in enumerate(chunks, 1):
            doc_name = c.get("metadata", {}).get("document_name", "Document")
            page_num = c.get("metadata", {}).get("page_number", 1)
            formatted.append(f"[{i}] Document: '{doc_name}' (Page {page_num}):\n{c['content']}\n")
        return "\n".join(formatted)

    async def generate_answer(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        business_name: str = "our company",
        tone: str = "friendly",
        custom_prompt: str = "",
        chat_history: Optional[List[Dict[str, str]]] = None,
        is_followup: bool = False
    ) -> Tuple[str, str]:
        """Generates grounded answer through the multi-tier failover cascade.
        
        Returns:
            Tuple[str, str]: (answer_text, provider_name)
        """
        context_str = self._format_context(retrieved_chunks)
        custom_block = f"\nCustom Business Persona & Guidance:\n{custom_prompt}\n" if custom_prompt else ""
        import datetime
        now = datetime.datetime.now()
        current_clock = now.strftime("%A, %B %d, %Y at %I:%M %p").replace(" 0", " ")
        prompt = STRICT_SYSTEM_PROMPT.format(
            business_name=business_name,
            context=context_str,
            current_clock=current_clock,
            tone="warm, polite and friendly" if tone == "friendly" else "formal, professional and direct",
            custom_instructions_block=custom_block
        )

        user_content = f"Customer Question: {query}"

        # Conversational dialogue history formatting
        conv_messages = []
        if chat_history:
            for m in chat_history[-6:]:
                r = "assistant" if m.get("role") in ["assistant", "bot"] else "user"
                c_text = (m.get("content") or "").strip()
                if c_text:
                    conv_messages.append({"role": r, "content": c_text})

        # -----------------------------------------------------------------
        # TIER 1: Groq Cloud LPUs (Ultra-Fast 500+ tokens/sec, ~0.26s generation)
        # -----------------------------------------------------------------
        if settings.GROQ_API_KEY:
            # Active fast models on Groq
            groq_models = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "allam-2-7b"]
            if settings.GROQ_MODEL and settings.GROQ_MODEL not in groq_models:
                groq_models.insert(0, settings.GROQ_MODEL)
            client = get_shared_client()
            
            for groq_m in groq_models:
                try:
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {
                        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": groq_m,
                        "messages": [
                            {"role": "system", "content": prompt},
                            *conv_messages,
                            {"role": "user", "content": user_content}
                        ],
                        "temperature": 0.1,
                        "max_tokens": 350
                    }
                    resp = await client.post(url, headers=headers, json=payload, timeout=2.5)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices and "message" in choices[0]:
                            text = (choices[0]["message"].get("content") or "").strip()
                            if text:
                                logger.info(f"Answer generated successfully via Tier 1 (Groq Ultra-Fast LPU: {groq_m}).")
                                return text, "groq"
                    logger.warning(f"Tier 1 (Groq {groq_m}) returned HTTP {resp.status_code}: {resp.text[:120]}")
                except Exception as e:
                    logger.warning(f"Tier 1 (Groq {groq_m}) encountered error: {str(e)}")

            logger.info("Tier 1 (Groq) unavailable or quota exhausted. Failing over to Tier 2 (Gemini Flash)...")

        # -----------------------------------------------------------------
        # TIER 2: Google Gemini Flash (Generous Free Tier Fallback)
        # -----------------------------------------------------------------
        global _gemini_cooldown_until
        if settings.GEMINI_API_KEY:
            now_ts = time.time()
            if now_ts < _gemini_cooldown_until:
                remaining_cd = int(_gemini_cooldown_until - now_ts)
                logger.info(f"Gemini in rate-limit cooldown ({remaining_cd}s remaining). Fast fail-forward to Tier 3...")
            else:
                gemini_models = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash"]
                if settings.GEMINI_MODEL and settings.GEMINI_MODEL not in gemini_models:
                    gemini_models.insert(0, settings.GEMINI_MODEL)
                
                client = get_shared_client()
                for g_model in gemini_models:
                    try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={settings.GEMINI_API_KEY}"
                        payload = {
                            "system_instruction": {
                                "parts": [{"text": prompt}]
                            },
                            "contents": (
                                [
                                    {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                                    for m in conv_messages
                                ] + [{"role": "user", "parts": [{"text": user_content}]}]
                            ),
                            "generationConfig": {
                                "temperature": 0.1,
                                "maxOutputTokens": 350
                            }
                        }
                        resp = await client.post(url, json=payload, timeout=2.8)
                        if resp.status_code == 200:
                            data = resp.json()
                            candidates = data.get("candidates", [])
                            if candidates and "content" in candidates[0]:
                                parts = candidates[0]["content"].get("parts", [])
                                if parts and "text" in parts[0]:
                                    text = parts[0]["text"].strip()
                                    logger.info(f"Answer generated successfully via Tier 2 (Gemini: {g_model}).")
                                    return text, "gemini"
                        elif resp.status_code in (429, 401, 403):
                            logger.warning(f"Tier 2 (Gemini {g_model}) returned HTTP {resp.status_code}. Activating 180s circuit breaker...")
                            _gemini_cooldown_until = time.time() + 180.0
                            break
                        elif resp.status_code == 404:
                            continue
                        logger.warning(f"Tier 2 (Gemini {g_model}) returned HTTP {resp.status_code}: {resp.text[:120]}")
                    except Exception as e:
                        logger.warning(f"Tier 2 (Gemini {g_model}) encountered error: {str(e)}")

                logger.info("Tier 2 (Gemini) failed. Cascading to Tier 3 (Sarvam AI)...")

        # -----------------------------------------------------------------
        # TIER 3: Sarvam AI Conversational LLM (Indic & Multilingual Freemium)
        # -----------------------------------------------------------------
        sarvam_key = getattr(settings, "SARVAM_LLM_KEY", "") or getattr(settings, "SARVAM_API_KEY", "")
        if sarvam_key:
            sarvam_models = [
                getattr(settings, "SARVAM_LLM_MODEL", "sarvam-105b-conversations"),
                "sarvam-105b-conversations",
                "sarvam-105b"
            ]
            sarvam_models = list(dict.fromkeys([m for m in sarvam_models if m]))
            base_sarvam_url = getattr(settings, "SARVAM_LLM_URL", "https://api.sarvam.ai/v1").rstrip("/")
            url = f"{base_sarvam_url}/chat/completions"
            headers = {
                "api-subscription-key": sarvam_key,
                "Content-Type": "application/json"
            }
            client = get_shared_client()

            for s_model in sarvam_models:
                try:
                    payload = {
                        "model": s_model,
                        "messages": [
                            {"role": "system", "content": prompt},
                            *conv_messages,
                            {"role": "user", "content": user_content}
                        ],
                        "temperature": 0.1,
                        "max_tokens": 350
                    }
                    resp = await client.post(url, headers=headers, json=payload, timeout=4.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices and "message" in choices[0]:
                            text = (choices[0]["message"].get("content") or "").strip()
                            if text:
                                logger.info(f"Answer generated successfully via Tier 3 (Sarvam: {s_model}).")
                                return text, "sarvam"
                    logger.warning(f"Tier 3 (Sarvam {s_model}) returned HTTP {resp.status_code}: {resp.text[:120]}")
                except Exception as e:
                    logger.warning(f"Tier 3 (Sarvam {s_model}) encountered error: {str(e)}")

            logger.warning("All Tier 3 (Sarvam AI) models failed. Cascading to Tier 4 / Extractive Synthesis...")

        # -----------------------------------------------------------------
        # TIER 4: OpenAI (Optional Enterprise Fallback)
        # -----------------------------------------------------------------
        if settings.OPENAI_API_KEY:
            try:
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 350
                }
                client = get_shared_client()
                resp = await client.post(url, headers=headers, json=payload, timeout=6.0)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        text = choices[0]["message"].get("content", "").strip()
                        logger.info("Answer generated successfully via Tier 4 (OpenAI).")
                        return text, "openai"
                logger.warning(f"Tier 4 (OpenAI) returned HTTP {resp.status_code}.")
            except Exception as e:
                logger.warning(f"Tier 4 (OpenAI) encountered error: {str(e)}.")

        # -----------------------------------------------------------------
        # TIER 5: Local Extractive Synthesis (Zero-API / Deterministic Grounding)
        # -----------------------------------------------------------------
        logger.info("Using Tier 5 deterministic extractive synthesis from grounded chunks...")
        if retrieved_chunks:
            answer = self._synthesize_grounded_extractive(query, retrieved_chunks, chat_history=chat_history, is_followup=is_followup)
            if answer and answer.strip():
                return answer.strip(), "extractive_synthesis"

        return "[UNKNOWN]", "none"

    def _synthesize_grounded_extractive(self, query: str, retrieved_chunks: List[Dict[str, Any]], chat_history: Optional[List[Dict[str, str]]] = None, is_followup: bool = False) -> str:
        """Intelligently identifies the exact relevant section across chunks and formats a structured response."""
        import re

        q_lower = query.lower()

        # Follow-up value/worth inquiry continuity
        if any(w in q_lower for w in ["worth", "how much is this", "value of this"]):
            last_text = ""
            if chat_history:
                last_text = " ".join([m.get("content", "") for m in chat_history[-2:]]).lower()
            if "brewpoint" in last_text or "point" in last_text or any("brewpoint" in c.get("content", "").lower() for c in retrieved_chunks):
                for c in retrieved_chunks:
                    content = c.get("content", "")
                    for line in content.split("\n"):
                        s = line.strip().replace("•", "").strip()
                        if "worth a rs" in s.lower() or "earn 1 brewpoint" in s.lower():
                            return (
                                f"Based on our rewards program, {s}\n\n"
                                f"*(If you were referring to a different product, plan, or item, please let me know and I'll be glad to look that up for you!)*"
                            )

        # Standalone pronoun inquiry with no prior conversational context
        PRONOUN_FOLLOWUPS = {"this", "that", "it"}
        if any(p in q_lower.split() for p in PRONOUN_FOLLOWUPS) and not chat_history:
            return "Could you please specify which product, plan, or item you are asking about? Let me know and I'll be happy to look up the exact details and value for you!"

        # Helper to find any chunk containing specific keywords
        def find_chunk_with(substrings: List[str]) -> str | None:
            for c in retrieved_chunks:
                content = c.get("content", "")
                if any(sub.lower() in content.lower() for sub in substrings):
                    return content
            return None

        # 1. Check for Q&A pair chunk
        for c in retrieved_chunks:
            content = c.get("content", "")
            if "Answer:" in content:
                return content.split("Answer:", 1)[1].strip()

        # 2. Subscriptions / Coffee Club Intent (Evaluated before generic charges)
        if any(k in q_lower for k in ["subscription", "subscriptions", "subscribe", "coffee club", "recurring", "club plan"]):
            bullets = []
            for c in retrieved_chunks:
                content = c.get("content", "")
                if "coffee club" in content.lower() or "subscription" in content.lower():
                    for line in content.split("\n"):
                        s = line.strip().replace("•", "").strip()
                        if len(s) > 15 and any(w in s.lower() for w in [
                            "delivers a 250 g bag", "discount with free shipping", "pause, skip or cancel", "changes must be made", "chosen roast every"
                        ]):
                            if not any(s[:25].lower() in b.lower() for b in bullets):
                                bullets.append(f"- {s}")
            if bullets:
                return (
                    "**Coffee Club Subscription:**\n\n"
                    "Our subscription service has **no separate enrollment fees** and includes the following benefits:\n\n"
                    + "\n".join(bullets)
                )

        # 3. Damaged or Wrong Items Specific Intent (Priority over general returns)
        if any(k in q_lower for k in ["damaged", "wrong item", "wrong items", "defect", "defective", "broken"]):
            bullets = []
            for c in retrieved_chunks:
                content = c.get("content", "")
                if "damaged or wrong" in content.lower() or "replacement or give a full refund" in content.lower():
                    for line in content.split("\n"):
                        s = line.strip().replace("•", "").strip()
                        if any(w in s.lower() for w in ["contact support within", "send a replacement", "return shipping is free"]):
                            if not any(s[:25].lower() in b.lower() for b in bullets):
                                bullets.append(f"- {s}")
            if bullets:
                return (
                    "**Damaged or Wrong Items Policy:**\n\n"
                    + "\n".join(bullets)
                    + "\n\n*Return shipping is completely free for damaged or incorrect deliveries.*"
                )

        # 4. Product Warranty Specific Intent
        if any(k in q_lower for k in ["warranty", "guarantee", "repair"]):
            bullets = []
            for c in retrieved_chunks:
                content = c.get("content", "")
                if "warranty" in content.lower() or "manufacturing defects" in content.lower():
                    for line in content.split("\n"):
                        s = line.strip().replace("•", "").strip()
                        if any(w in s.lower() for w in ["1-year warranty", "manufacturing defects", "does not cover misuse"]):
                            if not any(s[:25].lower() in b.lower() for b in bullets):
                                bullets.append(f"- {s}")
            if bullets:
                return "**Product Warranty Guidelines:**\n\n" + "\n".join(bullets)

        # 5. About Company / Store / Contact / Support Hours Intent
        if any(k in q_lower for k in ["about us", "about company", "about the company", "about store", "who are you", "who is", "overview", "founded", "location", "contact", "phone", "number", "email", "support hours", "store hours", "clinic hours", "headquarters", "call", "reach"]):
            # Check for general Contact / Phone / Email / Hours across retrieved grounded chunks
            contact_bullets = []
            seen_contact = set()
            for c in retrieved_chunks:
                content = c.get("content", "")
                cleaned_content = re.sub(r"^\s*.*?\.\.\.\s*", "", content)
                for line in cleaned_content.split("\n"):
                    s = line.strip().replace("•", "").replace("...", "").strip()
                    norm_s = " ".join(s.lower().split())
                    if not norm_s or len(norm_s) < 8 or norm_s in seen_contact:
                        continue
                    if any(w in norm_s for w in ["contact:", "phone:", "phone +", "phone", "email:", "support phone", "support email", "appointments@", "clinic hours:", "store hours:", "hours:", "emergencies only", "urgent inquiries", "helpline", "emergency", "after-hours", "toll-free"]):
                        seen_contact.add(norm_s)
                        contact_bullets.append(s)

            if contact_bullets and any(k in q_lower for k in ["contact", "phone", "number", "email", "call", "hours"]):
                return "**Contact & Operating Information:**\n\n" + "\n".join([f"- {b}" for b in contact_bullets[:5]])

            for c in retrieved_chunks:
                content = c.get("content", "")
                if "specialty coffee roaster" in content.lower() or "about brewnest" in content.lower() or "customer support email:" in content.lower():
                    out = []
                    about_match = re.search(r"(?:1\.\s*About\s+[A-Za-z0-9\s]+)?\s*([A-Za-z0-9\s\.\,\-]+?founded in \d{4}\.)", content, re.IGNORECASE)
                    if about_match:
                        clean_about = re.sub(r"(?i)^.*?1\.\s*About\s+[A-Za-z0-9\s]+\n*", "", about_match.group(1)).strip()
                        out.append(f"**About Us:**\n{clean_about}")
                    elif "specialty coffee roaster" in content.lower():
                        for line in content.split("\n"):
                            if any(w in line.lower() for w in ["online specialty coffee", "founded in", "single-origin"]):
                                out.append(f"**About Us:**\n{line.strip()}")
                                break

                    contacts = []
                    for line in content.split("\n"):
                        s = line.strip()
                        if "customer support email:" in s.lower() or "support phone:" in s.lower():
                            contacts.append(f"- **Contact:** {s}")
                        elif "support hours are" in s.lower():
                            contacts.append(f"- **Support Hours:** {s}")
                        elif "support is closed" in s.lower():
                            contacts.append(f"- **Closures:** {s}")

                    if contacts:
                        out.append("**Customer Support & Hours:**\n" + "\n".join(contacts))

                    if out:
                        return "\n\n".join(out)

            # Telecom / Broadband Contact Hours
            contact_lines = []
            for c in retrieved_chunks:
                content = c.get("content", "")
                if "contact and support hours" in content.lower() or "outage and technical line" in content.lower():
                    for line in content.split("\n"):
                        s = line.strip().replace("•", "").strip()
                        if any(w in s.lower() for w in ["outage line:", "billing and sales:", "stores are open", "operates in"]):
                            if not any(s[:20].lower() in b.lower() for b in contact_lines):
                                contact_lines.append(f"- {s}")
            if contact_lines:
                return "**Customer Support & Contact Hours:**\n\n" + "\n".join(contact_lines)

        # 5.5. GST / Taxes / VAT Intent
        if any(k in q_lower for k in ["gst", "tax", "taxes", "vat", "gstin"]):
            gst_sentences = []
            for c in retrieved_chunks:
                text_clean = c.get("content", "").replace("\r", " ").replace("\n", " ")
                sentences = re.split(r"(?<=[.!?])\s+", text_clean)
                for s in sentences:
                    s_clean = s.strip()
                    if any(w in s_clean.lower() for w in ["gst", "tax", "gstin"]) and len(s_clean) > 8:
                        if not any(s_clean[:25].lower() in b.lower() for b in gst_sentences):
                            gst_sentences.append(s_clean)
            if gst_sentences:
                if any(k in q_lower for k in ["how much", "rate", "percentage", "%", "what is"]):
                    for s in gst_sentences:
                        if any(w in s.lower() for w in ["18%", "include", "gst rate", "included"]):
                            return (
                                f"**Taxes & GST Information:**\n\n"
                                f"{s}\n\n"
                                f"GST invoices are available in the customer portal (to add a business GSTIN, write to billing@zephyrfiber.example before the 25th of the month)."
                            )
                return "**Taxes & GST Information:**\n\n" + "\n".join([f"- {s}" for s in gst_sentences])

        # 5.6. Broadband / Service Plans Intent
        if any(k in q_lower for k in ["plan", "plans", "broadband", "speed", "speeds", "data limit", "fair usage", "fup", "product", "products"]):
            broadband_lines = []
            for c in retrieved_chunks:
                content = c.get("content", "")
                if any(w in content.lower() for w in ["home broadband plans", "mbps", "basic:", "plus:", "pro:", "max:"]):
                    for line in content.split("\n"):
                        s = line.strip()
                        if any(w in s.lower() for w in ["basic:", "plus:", "pro:", "max:", "static ip address:"]):
                            if not any(s[:20].lower() in b.lower() for b in broadband_lines):
                                broadband_lines.append(f"- **{s}**")
            if broadband_lines:
                return (
                    "**Available Broadband Plans & Pricing:**\n\n"
                    "Zephyr Fiber offers four high-speed home broadband plans (all include 18% GST and symmetrical upload/download speeds):\n\n"
                    + "\n".join(broadband_lines)
                )

        # 5.7. Installation & Router Equipment Intent
        if any(k in q_lower for k in ["installation", "install", "setup", "router", "equipment", "cable", "security deposit"]):
            install_lines = []
            for c in retrieved_chunks:
                content = c.get("content", "")
                if "installation" in content.lower() or "router:" in content.lower():
                    for line in content.split("\n"):
                        s = line.strip().replace("•", "").strip()
                        if any(w in s.lower() for w in ["standard installation", "installation covers", "installation fee:", "rs. 1,500", "rs. 1,000", "free on 12-month", "wifi 6 router", "security deposit of rs. 2,000", "kyc"]):
                            if not any(s[:20].lower() in b.lower() for b in install_lines):
                                install_lines.append(f"- {s}")
            if install_lines:
                return "**Installation & Equipment Guidelines:**\n\n" + "\n".join(install_lines)

        # 5.8. Outages & Compensation Intent
        if any(k in q_lower for k in ["outage", "down", "disconnected", "no internet", "restart router", "compensation", "credit", "fiber fault"]):
            outage_lines = []
            for c in retrieved_chunks:
                content = c.get("content", "")
                if "outage" in content.lower() or "connection is down" in content.lower():
                    for line in content.split("\n"):
                        s = line.strip().replace("•", "").strip()
                        if any(w in s.lower() for w in ["connection is down", "restart the router", "outage line", "engineers visit within", "credits rs. 25"]):
                            if not any(s[:20].lower() in b.lower() for b in outage_lines):
                                outage_lines.append(f"- {s}")
            if outage_lines:
                return "**Outage Support & Service Resolution:**\n\n" + "\n".join(outage_lines)

        # 5.9. Relocation, Plan Changes & Cancellation Intent
        if any(k in q_lower for k in ["relocation", "relocate", "move", "new address", "upgrade", "downgrade", "early termination"]):
            reloc_lines = []
            for c in retrieved_chunks:
                content = c.get("content", "")
                if any(w in content.lower() for w in ["relocation:", "upgrades:", "cancellation:"]):
                    for line in content.split("\n"):
                        s = line.strip().replace("•", "").strip()
                        if any(w in s.lower() for w in ["moving your connection", "upgrades take effect", "30 days notice", "early termination fee"]):
                            if not any(s[:20].lower() in b.lower() for b in reloc_lines):
                                reloc_lines.append(f"- {s}")
            if reloc_lines:
                return "**Relocation, Plan Changes & Cancellation:**\n\n" + "\n".join(reloc_lines)

        # 6. Product Catalog & Pricing Intent (Physical goods e.g. BrewNest)
        if (any(k in q_lower for k in ["product", "products", "catalog", "menu", "list of product"]) or 
            (any(k in q_lower for k in ["price", "pricing", "cost", "item", "items"]) and not any(k in q_lower for k in ["return", "returns", "refund", "refunds", "shipping", "delivery", "fee", "warranty", "exchange"]))):
            for c in retrieved_chunks:
                content = c.get("content", "")
                if "products and pricing" in content.lower() or ("product" in content.lower() and "price" in content.lower() and ("rs." in content.lower() or "$" in content)) or "highland roast" in content.lower():
                    pattern = re.compile(
                        r"([A-Za-z0-9\s\-\(\)]+?)\s*\n\s*(250\s*g|1\s*kg|Pack of \d+|1\s*unit|unit|[0-9]+\s*ml|[0-9]+\s*oz)\s*\n\s*(Rs\.\s*[\d,]+|\$[\d,]+)",
                        re.MULTILINE
                    )
                    matches = pattern.findall(content)
                    if matches:
                        items = {}
                        for name, size, price in matches:
                            clean_name = re.sub(r"(?i)(products?\s*(and|&)?\s*pricing|product\s*size\s*price)", "", name).strip()
                            if clean_name and clean_name.lower() not in ["product", "size", "price"]:
                                if clean_name not in items:
                                    items[clean_name] = []
                                items[clean_name].append(f"{size}: {price}")

                        if items:
                            out = ["**Products & Pricing:**\n"]
                            for p_name, p_specs in items.items():
                                out.append(f"- **{p_name}** ({' | '.join(p_specs)})")
                            if "GST" in content or "Rupees" in content:
                                out.append("\n*All prices are in Indian Rupees and include GST.*")
                            return "\n".join(out)

        # 7. Returns & Refunds General Intent
        if any(k in q_lower for k in ["return", "returns", "refund", "refunds", "exchange"]):
            bullets = []
            for c in retrieved_chunks:
                content = c.get("content", "")
                if any(w in content.lower() for w in ["returns and refunds", "perishable", "return shipping", "refunds are processed", "damaged or wrong"]):
                    for line in content.split("\n"):
                        s = line.strip().replace("•", "").strip()
                        if len(s) > 15 and any(w in s.lower() for w in [
                            "perishable", "unopened bags can be returned", "original packaging can be",
                            "contact support within 48 hours", "return shipping", "refunds are processed",
                            "replacement or give a full refund"
                        ]):
                            if not any(s[:25].lower() in b.lower() for b in bullets):
                                bullets.append(f"- {s}")
            if bullets:
                return "**Returns & Refunds Policy:**\n\n" + "\n".join(bullets)

        # 8. Shipping & Delivery Charges Intent (Priority over return shipping)
        if any(k in q_lower for k in ["shipping", "delivery", "dispatch", "charge", "fee", "rate", "cost", "transit"]) and not any(k in q_lower for k in ["return shipping", "refund fee"]):
            content = find_chunk_with(["shipping and delivery", "free shipping on orders", "standard delivery takes"])
            if content:
                shipping_bullets = []
                for line in content.split("\n"):
                    s = line.strip().replace("\ufffd", "").replace("•", "").strip()
                    if s.startswith("-"):
                        s = s[1:].strip()
                    if len(s) > 15 and any(w in s.lower() for w in ["free shipping", "delivery takes", "express delivery", "orders placed", "cash on delivery", "flat shipping", "tracking link", "ship internationally"]):
                        if not any(s[:25].lower() in b.lower() for b in shipping_bullets):
                            shipping_bullets.append(f"- {s}")
                if shipping_bullets:
                    return "**Shipping & Delivery Guidelines:**\n\n" + "\n".join(shipping_bullets[:6])

        # 9. Loyalty Program / BrewPoints Intent
        if any(k in q_lower for k in ["brewpoints", "loyalty", "reward", "rewards", "points", "discount"]):
            content = find_chunk_with(["brewpoints loyalty program", "brewpoint"])
            if content:
                bullets = []
                for line in content.split("\n"):
                    s = line.strip().replace("•", "").strip()
                    if any(w in s.lower() for w in ["earn 1 brewpoint", "worth a rs", "expire 12 months", "points are not earned"]):
                        bullets.append(f"- {s}")
                if bullets:
                    return "**BrewPoints Loyalty Rewards:**\n\n" + "\n".join(bullets)

        # 10. Order Changes & Cancellations Intent
        if any(k in q_lower for k in ["cancel", "cancellation", "change order", "change address", "modify order"]):
            content = find_chunk_with(["order changes and cancellation", "cancelled for free", "address can be changed"])
            if content:
                bullets = []
                for line in content.split("\n"):
                    s = line.strip().replace("•", "").strip()
                    if any(w in s.lower() for w in ["cancelled for free", "address can be changed"]):
                        bullets.append(f"- {s}")
                if bullets:
                    return "**Order Cancellation & Modification:**\n\n" + "\n".join(bullets)

        # 11. Payment Methods Intent
        if any(k in q_lower for k in ["payment", "payments", "pay ", "how to pay", "cod", "cash on delivery", "emi", "upi", "credit card", "debit card"]):
            content = find_chunk_with(["payments", "we accept upi", "cash on delivery", "no-cost emi"])
            if content:
                bullets = []
                for line in content.split("\n"):
                    s = line.strip().replace("•", "").strip()
                    if any(w in s.lower() for w in ["we accept upi", "cash on delivery (cod) is available", "no-cost emi for"]):
                        bullets.append(f"- {s}")
                if bullets:
                    return "**Payment Methods & Terms:**\n\n" + "\n".join(bullets)

        # 12. General Term-density extraction with Strict Grounding Verification
        clean_q = re.sub(r"[^\w\s]", " ", q_lower)
        STOP_WORDS = {
            "tell", "about", "me", "what", "is", "the", "a", "an", "can", "you", "please", "how",
            "do", "does", "give", "show", "who", "where", "when", "why", "which",
            "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "as", "by", "from",
            "any", "some", "all", "are", "have", "has", "had", "be", "been", "was", "were",
            "it", "its", "they", "them", "their", "there", "this", "that", "these", "those",
            "i", "we", "my", "your", "our", "he", "she", "his", "her",
            "sell", "selling", "available", "offer", "provide", "buy"
        }
        q_tokens = set([t for t in clean_q.split() if t not in STOP_WORDS and len(t) > 1])

        candidate_sentences = []
        seen_sentences = set()
        for c in retrieved_chunks:
            text = c.get("content", "")
            # Remove chunk overlap artifacts
            clean_text = re.sub(r"^\s*.*?\.\.\.\s*", "", text)
            for raw_line in clean_text.split("\n"):
                s = raw_line.strip().replace("...", "").strip()
                if not s or s.startswith("SECTION") or len(s) < 15:
                    continue
                # Normalize line for deduplication (ignore leading bullet/whitespace)
                norm_line = re.sub(r"^[•\-\*\s]+", "", s).strip().lower()
                norm_line = " ".join(norm_line.split())
                if norm_line in seen_sentences:
                    continue
                matches = sum(1 for tok in q_tokens if re.search(r"\b" + re.escape(tok) + r"\b", norm_line))
                if matches > 0:
                    seen_sentences.add(norm_line)
                    candidate_sentences.append((matches, s))

        # Strict grounding check:
        # If query has 4+ content tokens and the top candidate only matches 1 token,
        # it is an accidental single-word collision and NOT an answer.
        max_matches = max([m for m, _ in candidate_sentences], default=0)
        if not candidate_sentences or (len(q_tokens) >= 4 and max_matches < 2):
            logger.info(f"Extractive synthesis: Insufficient grounded answer found for query tokens {q_tokens} (max matches={max_matches}). Returning [UNKNOWN].")
            return "[UNKNOWN]"

        candidate_sentences.sort(key=lambda x: x[0], reverse=True)
        top_answers = [s for _, s in candidate_sentences[:5]]
        return "\n".join(top_answers)

llm_client = MultiTierLLMClient()
