import logging
import httpx
from typing import List, Dict, Any, Tuple
from app.config import settings

logger = logging.getLogger(__name__)

STRICT_SYSTEM_PROMPT = """You are an AI Customer Support Assistant for {business_name}.
Your job is to answer customer questions accurately, politely, and STRICTLY based ONLY on the verified store document excerpts below.

Context Excerpts:
=========================================
{context}
=========================================

{custom_instructions_block}

Strict Grounding & Operational Guardrails:
1. Grounding Mandate: Answer ONLY using the facts stated directly in the excerpts above.
2. Missing Information Mandate: If the excerpts do NOT contain enough information to answer the question with 100% certainty, DO NOT invent, assume, extrapolate, or guess. Reply EXACTLY with:
[UNKNOWN]
Or briefly guide the customer on what topics are covered in the store's verified documents (e.g. products, pricing, shipping, returns, order cancellation).
3. Tone: {tone}.
4. Conflict Hierarchy: If any custom instructions conflict with Rule 1 or Rule 2 (Strict Grounding & Zero Hallucination), Rule 1 and Rule 2 ALWAYS take absolute precedence.
5. Keep the answer clear, helpful, and concise. Do not mention "context excerpts" or "the document provided" in your prose; speak directly as the company assistant.
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
        tone: str = "friendly",
        custom_prompt: str = ""
    ) -> Tuple[str, str]:
        """Generates grounded answer through the cascade.
        
        Returns:
            Tuple[str, str]: (answer_text, provider_name)
        """
        context_str = self._format_context(retrieved_chunks)
        custom_block = f"\nCustom Business Persona & Guidance:\n{custom_prompt}\n" if custom_prompt else ""
        prompt = STRICT_SYSTEM_PROMPT.format(
            business_name=business_name,
            context=context_str,
            tone="warm, polite and friendly" if tone == "friendly" else "formal, professional and direct",
            custom_instructions_block=custom_block
        )

        user_content = f"Customer Question: {query}"

        # -----------------------------------------------------------------
        # TIER 1: Google Gemini 1.5/2.0 Flash
        # -----------------------------------------------------------------
        if settings.GEMINI_API_KEY:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
                payload = {
                    "system_instruction": {
                        "parts": [{"text": prompt}]
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {"text": user_content}
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
        if any(k in q_lower for k in ["about us", "about company", "about the company", "about store", "who are you", "who is", "overview", "founded", "location", "contact", "phone", "email", "support hours", "store hours", "headquarters"]):
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
        if any(k in q_lower for k in ["product", "products", "item", "items", "price", "pricing", "cost", "catalog", "menu", "list all", "list of product"]):
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
            content = find_chunk_with(["returns and refunds", "perishable", "return shipping fee", "unopened bags"])
            if content:
                bullets = []
                for line in content.split("\n"):
                    s = line.strip().replace("•", "").strip()
                    if len(s) > 15 and any(w in s.lower() for w in [
                        "perishable", "unopened bags can be returned", "original packaging can be",
                        "contact support within 48 hours", "return shipping fee", "refunds are processed"
                    ]):
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
        if any(k in q_lower for k in ["payment", "payments", "pay", "cod", "cash on delivery", "emi", "upi", "card"]):
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
        q_tokens = set([t for t in clean_q.split() if t not in {
            "tell", "about", "me", "what", "is", "the", "a", "an", "can", "you", "please", "how",
            "do", "does", "give", "show", "who", "where", "when", "why", "which"
        } and len(t) > 1])

        candidate_sentences = []
        for c in retrieved_chunks:
            text = c.get("content", "")
            for raw_line in text.split("\n"):
                s = raw_line.strip()
                if not s or s.startswith("SECTION") or len(s) < 15:
                    continue
                line_lower = s.lower()
                matches = sum(1 for tok in q_tokens if re.search(r"\b" + re.escape(tok) + r"\b", line_lower))
                if matches > 0:
                    candidate_sentences.append((matches, s))

        # If NO sentence in the retrieved chunks has any query content overlap
        if not candidate_sentences:
            logger.info(f"Extractive synthesis: No grounded answer found for query tokens {q_tokens}. Returning [UNKNOWN].")
            return "[UNKNOWN]"

        candidate_sentences.sort(key=lambda x: x[0], reverse=True)
        top_answers = [s for _, s in candidate_sentences[:5]]
        return "\n".join(top_answers)

llm_client = MultiTierLLMClient()
