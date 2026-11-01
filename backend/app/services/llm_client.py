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
            top = retrieved_chunks[0]
            content = top["content"].strip()
            
            # If Q&A chunk format
            if "Answer:" in content:
                ans_part = content.split("Answer:", 1)[1].strip()
                return ans_part, "extractive_synthesis"

            # Direct grounded passage from document
            clean_text = content[:600].strip()
            return clean_text, "extractive_synthesis"

        return "[UNKNOWN]", "none"

llm_client = MultiTierLLMClient()
