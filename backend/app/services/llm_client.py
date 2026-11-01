import time
import logging
import httpx
from typing import List, Dict, Any, Tuple, Optional
from app.config import settings

logger = logging.getLogger(__name__)

STRICT_SYSTEM_PROMPT = """You are an AI Customer Support Assistant for {business_name}.
Your job is to answer customer questions accurately, politely, and STRICTLY based ONLY on the provided document excerpts below.

Context Excerpts:
=========================================
{context}
=========================================

Strict Operational Rules:
1. Answer ONLY using the facts stated directly in the excerpts above.
2. If the excerpts do NOT contain enough information to answer the question with 100% certainty, DO NOT invent, assume, extrapolate, or guess. Reply EXACTLY with:
[UNKNOWN]
3. Tone: {tone}.
4. Keep the answer clear, helpful, and concise. Do not mention "context excerpts" or "the document provided" in your prose; speak directly as the company assistant.
"""

class MultiTierLLMClient:
    """Multi-Tier LLM Cascade engineered for Render Free Tier (512MB RAM safe).
    
    Tier 1 (Primary): Google Gemini 1.5/2.0 Flash (Free 15 RPM, 1M TPM)
    Tier 2 (Fallback): Groq LPUs with Llama 3.1 8B Instant (Free 30 RPM, 300+ tok/s)
    Tier 3 (Local/Offline): Extractive synthesis fallback
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
        tone: str = "friendly"
    ) -> Tuple[str, str]:
        """Generates grounded answer through the cascade.
        
        Returns:
            Tuple[str, str]: (answer_text, provider_name)
        """
        context_str = self._format_context(retrieved_chunks)
        prompt = STRICT_SYSTEM_PROMPT.format(
            business_name=business_name,
            context=context_str,
            tone="warm, polite and friendly" if tone == "friendly" else "formal, professional and direct"
        )

        user_content = f"Customer Question: {query}"

        # -----------------------------------------------------------------
        # TIER 1: Google Gemini 1.5/2.0 Flash
        # -----------------------------------------------------------------
        if settings.GEMINI_API_KEY:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
                payload = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {"text": f"{prompt}\n\n{user_content}"}
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.1,  # Low temperature to suppress hallucinations
                        "maxOutputTokens": 600
                    }
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates and "content" in candidates[0]:
                            parts = candidates[0]["content"].get("parts", [])
                            if parts and "text" in parts[0]:
                                text = parts[0]["text"].strip()
                                logger.info("Answer generated successfully via Tier 1 (Gemini Flash).")
                                return text, "gemini"
                    logger.warning(f"Tier 1 (Gemini) returned HTTP {resp.status_code}. Falling back to Tier 2 (Groq)...")
            except Exception as e:
                logger.warning(f"Tier 1 (Gemini) encountered error: {str(e)}. Falling back to Tier 2 (Groq)...")

        # -----------------------------------------------------------------
        # TIER 2: Groq LPUs with Llama 3.1 8B
        # -----------------------------------------------------------------
        if settings.GROQ_API_KEY:
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": settings.GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 600
                }
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices and "message" in choices[0]:
                            text = choices[0]["message"].get("content", "").strip()
                            logger.info("Answer generated successfully via Tier 2 (Groq Llama).")
                            return text, "groq"
                    logger.warning(f"Tier 2 (Groq) returned HTTP {resp.status_code}.")
            except Exception as e:
                logger.warning(f"Tier 2 (Groq) encountered error: {str(e)}.")

        # -----------------------------------------------------------------
        # TIER 3: OpenAI (GPT-4o-mini / GPT-3.5-turbo)
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
                    "max_tokens": 600
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices and "message" in choices[0]:
                            text = choices[0]["message"].get("content", "").strip()
                            logger.info("Answer generated successfully via Tier 3 (OpenAI).")
                            return text, "openai"
                    logger.warning(f"Tier 3 (OpenAI) returned HTTP {resp.status_code}.")
            except Exception as e:
                logger.warning(f"Tier 3 (OpenAI) encountered error: {str(e)}.")

        # -----------------------------------------------------------------
        # TIER 4: Local Extractive Synthesis (Zero-API / Deterministic Grounding)
        # -----------------------------------------------------------------
        logger.info("Using Tier 4 deterministic extractive synthesis from grounded chunks...")
        if retrieved_chunks:
            answer = self._synthesize_grounded_extractive(query, retrieved_chunks)
            if answer and answer.strip():
                return answer.strip(), "extractive_synthesis"

        return "[UNKNOWN]", "none"

    def _synthesize_grounded_extractive(self, query: str, retrieved_chunks: List[Dict[str, Any]]) -> str:
        """Intelligently identifies the exact relevant section across chunks and formats a structured response."""
        import re

        q_lower = query.lower()

        # 1. Check for Q&A pair chunk
        for c in retrieved_chunks:
            content = c.get("content", "")
            if "Answer:" in content:
                return content.split("Answer:", 1)[1].strip()

        # 2. Product Catalog & Pricing Intent
        if any(k in q_lower for k in ["product", "products", "item", "items", "price", "pricing", "cost", "catalog"]):
            for c in retrieved_chunks:
                content = c.get("content", "")
                if "products and pricing" in content.lower() or ("product" in content.lower() and "price" in content.lower() and ("rs." in content.lower() or "$" in content)):
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

        # 3. Shipping & Delivery Charges Intent (Priority over return shipping)
        if any(k in q_lower for k in ["shipping", "delivery", "dispatch", "charge", "fee", "rate", "cost", "transit"]) and not any(k in q_lower for k in ["return shipping", "refund fee"]):
            shipping_bullets = []
            for c in retrieved_chunks:
                content = c.get("content", "")
                if "shipping" in content.lower() or "delivery" in content.lower():
                    for line in content.split("\n"):
                        s = line.strip().replace("\ufffd", "").replace("•", "").strip()
                        if s.startswith("-"):
                            s = s[1:].strip()
                        if len(s) > 15 and any(w in s.lower() for w in ["free shipping", "delivery takes", "express delivery", "orders placed", "cash on delivery", "flat shipping", "tracking link", "ship internationally"]):
                            if not any(s[:25].lower() in b.lower() for b in shipping_bullets):
                                shipping_bullets.append(f"- {s}")
            if shipping_bullets:
                return "**Shipping & Delivery Guidelines:**\n\n" + "\n".join(shipping_bullets[:6])

        # 4. Returns & Refunds Intent
        if any(k in q_lower for k in ["return", "returns", "refund", "refunds", "exchange", "damaged", "warranty"]):
            for c in retrieved_chunks:
                content = c.get("content", "")
                if "returns and refunds" in content.lower() or "return policy" in content.lower() or "damaged or wrong" in content.lower():
                    idx = content.lower().find("returns and refunds")
                    if idx == -1:
                        idx = content.lower().find("return policy")
                    if idx == -1:
                        idx = content.lower().find("damaged or wrong")
                    if idx != -1:
                        sec_text = content[idx:]
                        for next_sec in ["5. order", "6. payment"]:
                            s_idx = sec_text.lower().find(next_sec)
                            if s_idx != -1:
                                sec_text = sec_text[:s_idx]
                        return sec_text[:500].strip()

        # 5. Fallback: Find chunk with highest term density & clean leading fragments
        best_content = retrieved_chunks[0].get("content", "").strip()
        lines = best_content.split("\n")
        clean_lines = []
        skip_noise = True
        for l in lines:
            s = l.strip()
            if not s:
                continue
            if re.match(r"^(\d+\.|\b[A-Z][a-zA-Z\s]{3,30}:|#|\*\*|\b[A-Z])", s) and "..." not in s:
                skip_noise = False
            if not skip_noise:
                clean_lines.append(s)

        if clean_lines:
            return "\n".join(clean_lines[:8]).strip()[:500]

        return best_content[:500].strip()

llm_client = MultiTierLLMClient()
