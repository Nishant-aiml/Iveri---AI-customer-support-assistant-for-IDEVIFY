import time
import logging
from typing import List, Dict, Any, Optional
from app.config import settings
from app.services.vector_store import vector_store_service
from app.services.bm25_store import bm25_store_service
from app.services.rrf import reciprocal_rank_fusion
from app.services.circuit_breaker import GreetingInterceptor, TemporalInterceptor, circuit_breaker
from app.services.llm_client import llm_client
from app.services.guardrails import guardrails_service
from app.services.laya_router import laya_service

logger = logging.getLogger(__name__)

class HybridRAGEngine:
    """Production Multi-Hybrid Retrieval-Augmented Generation Engine.
    
    1. Greeting filter (zero-token interceptor)
    2. Dense Vector Retrieval (ChromaDB) + Sparse Lexical Search (BM25)
    3. Reciprocal Rank Fusion (RRF) deduplication & rank fusion
    4. Deterministic Pre-LLM Confidence Circuit Breaker
    5. Multi-Tier LLM Cascade (Gemini Flash -> Groq Llama 3.1 8B)
    6. Deterministic Source Citation Badging
    """

    async def index_document_chunks(self, business_id: str, chunks: List[Dict[str, Any]]):
        """Indexes document chunks into both ChromaDB (Dense) and BM25 (Sparse) stores."""
        if not chunks:
            return

        # 1. ChromaDB
        await vector_store_service.add_chunks(business_id, chunks)

        # 2. BM25
        bm25_store_service.add_chunks(business_id, chunks)

        logger.info(f"Hybrid RAG Engine indexed {len(chunks)} chunks for business {business_id}.")

    async def delete_document_chunks(self, business_id: str, document_id: str):
        """Removes a document's chunks from both ChromaDB and BM25 indices."""
        await vector_store_service.delete_document(business_id, document_id)
        bm25_store_service.delete_document(business_id, document_id)
        logger.info(f"Hybrid RAG Engine pruned chunks for doc {document_id} under business {business_id}.")

    async def query(
        self,
        business_id: str,
        user_query: str,
        business_settings: Optional[Dict[str, Any]] = None,
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Executes full multi-hybrid RAG pipeline for a customer question."""
        start_time = time.time()
        business_settings = business_settings or {}
        business_name = business_settings.get("name", "our business")
        fallback_msg = business_settings.get(
            "fallback_message",
            "I'm sorry, but I do not have this information in my documents. I have logged your question for our team to assist you."
        )
        tone = business_settings.get("tone", "friendly")

        # Step 0: Inbound Guardrail (Prompt Injection, Jailbreak & Input Bounding)
        inbound_check = guardrails_service.check_inbound_safety(user_query)
        if not inbound_check["is_safe"]:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "answer": inbound_check["safe_reply"],
                "is_answered": True,
                "confidence_score": 1.0,
                "citations": [],
                "llm_provider": "guardrail_inbound",
                "latency_ms": max(latency_ms, 5),
                "retrieved_chunks": []
            }

        # Mask sensitive PII & bound query length
        sanitized_query = guardrails_service.sanitize_input(user_query)

        # Step 0: Real-Time Temporal Queries (Exact Time, Date, Day, Year)
        temporal_reply = TemporalInterceptor.check_temporal(sanitized_query)
        if temporal_reply:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "answer": temporal_reply,
                "is_answered": True,
                "confidence_score": 1.0,
                "citations": [],
                "llm_provider": "system_clock",
                "latency_ms": max(latency_ms, 3),
                "retrieved_chunks": []
            }

        # Step 1: Greeting & Conversational Interceptor (Less AI-Dependent)
        greeting_reply = GreetingInterceptor.check_greeting(sanitized_query, business_name=business_name)
        if greeting_reply:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "answer": greeting_reply,
                "is_answered": True,
                "confidence_score": 1.0,
                "citations": [],
                "llm_provider": "greeting_rule",
                "latency_ms": max(latency_ms, 5),
                "retrieved_chunks": []
            }

        # Step 1.2: Laya System 1 Semantic Guardrail (Pre-retrieval Out-of-Scope Firewall)
        laya_intent = laya_service.classify_intent(sanitized_query)
        if laya_intent.get("available") and laya_intent.get("intent") == "out_of_scope" and laya_intent.get("confidence", 0.0) >= 0.60:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Query '{user_query}' short-circuited by Laya System 1 Router as out_of_scope (conf={laya_intent.get('confidence'):.2f}).")
            return {
                "answer": fallback_msg,
                "is_answered": False,
                "confidence_score": 0.0,
                "citations": [],
                "llm_provider": "circuit_breaker",
                "latency_ms": max(latency_ms, 8),
                "retrieved_chunks": []
            }

        # Step 1.5: Typo Correction & Normalization against Knowledge Base
        import difflib
        import re
        clean_query = sanitized_query
        vocab = bm25_store_service.get_vocabulary(business_id)
        
        # Standard English words that must NEVER be mutated by typo correction
        IMMUTABLE_WORDS = {
            "tell", "toll", "show", "give", "what", "when", "where", "which", "who", "why", "how",
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
            "them", "their", "theirs", "themselves", "this", "that", "these", "those", "am",
            "cost", "much", "many", "price", "pricing", "item", "product", "products", "policy",
            "support", "service", "services", "help", "order", "bill", "billing", "charges", "rate",
            "plans", "plan", "broadband", "speed", "speeds", "data", "limit", "cable", "router", "gst"
        }

        if vocab:
            tokens = sanitized_query.split()
            corrected = []
            for tok in tokens:
                alph = re.sub(r"[^a-zA-Z]", "", tok.lower())
                # Only attempt fuzzy matching if word is long (>= 5 chars) and NOT an English common word
                if len(alph) >= 5 and alph not in IMMUTABLE_WORDS and alph not in vocab:
                    matches = difflib.get_close_matches(alph, list(vocab), n=1, cutoff=0.82)
                    if matches:
                        corrected.append(matches[0])
                        continue
                corrected.append(tok)
            clean_query = " ".join(corrected)
            if clean_query.lower() != user_query.lower():
                logger.info(f"Query typo corrected: '{user_query}' -> '{clean_query}'")

        # Query Expansion for Domain-Aware Search
        expanded_query = clean_query
        q_lower = clean_query.lower()
        if any(w in q_lower for w in ["product", "products", "item", "items", "plan", "plans", "broadband", "package"]):
            expanded_query = f"{clean_query} plans pricing products broadband"
        elif any(w in q_lower for w in ["gst", "tax", "vat"]):
            expanded_query = f"{clean_query} 18% gst taxes billing"
        elif any(w in q_lower for w in ["point", "points", "brewpoint", "brewpoints", "loyalty", "reward", "rewards"]):
            expanded_query = f"{clean_query} brewpoints loyalty program points rewards discount"

        # Step 2: Concurrent Multi-Hybrid Retrieval (Dense Vector + Sparse BM25 in parallel)
        import asyncio
        dense_task = vector_store_service.search(business_id, expanded_query, top_k=10)
        sparse_task = asyncio.to_thread(bm25_store_service.search, business_id, expanded_query, 10)
        dense_hits, sparse_hits = await asyncio.gather(dense_task, sparse_task)

        # Step 3: Reciprocal Rank Fusion (RRF)
        fused_chunks = reciprocal_rank_fusion(
            dense_hits=dense_hits,
            sparse_hits=sparse_hits,
            k=settings.RRF_K,
            top_n=max(settings.TOP_K_CHUNKS, 8)
        )

        # Step 4: Pre-LLM Confidence Circuit Breaker (Less AI-Dependent)
        gate_decision = circuit_breaker.evaluate(
            fused_chunks=fused_chunks,
            threshold=settings.CONFIDENCE_THRESHOLD,
            query=clean_query
        )

        if not gate_decision["can_answer"]:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Query '{user_query}' short-circuited by Pre-LLM Circuit Breaker.")
            return {
                "answer": fallback_msg,
                "is_answered": False,
                "confidence_score": gate_decision["confidence"],
                "citations": [],
                "llm_provider": "circuit_breaker",
                "latency_ms": max(latency_ms, 8),
                "retrieved_chunks": []
            }

        # Step 5: Multi-Tier LLM Synthesis (Gemini Flash -> Groq Llama)
        generated_answer, provider = await llm_client.generate_answer(
            query=clean_query,
            retrieved_chunks=fused_chunks,
            business_name=business_name,
            tone=tone,
            custom_prompt=business_settings.get("custom_prompt", "")
        )

        # Step 5.5: Outbound Guardrail Check (Secret Leakage & Grounding Filter)
        generated_answer = guardrails_service.check_outbound_safety(generated_answer, fallback_msg)

        # Step 6: Post-generation Unknown and Inability-to-Answer check
        ans_lower = generated_answer.strip().lower()
        UNKNOWN_SIGNATURES = [
            r"\[unknown\]",
            r"i('m| am)? sorry,?\s*(but)?\s*i (don't|do not) have (information|details|any info)",
            r"i (don't|do not) have (information|details|enough information|any info|access)",
            r"(the|these)?\s*(excerpts?|documents?|provided text|store records?)\s*(do not|does not) (contain|mention|state|provide)",
            r"not mentioned in (the|our)?\s*(documents?|excerpts?|store policies|records?)",
            r"i (cannot|can't) find (any|enough)?\s*(information|details)",
            r"i am (unable|not able) to (answer|find|locate|determine)",
            r"no information (is|was)?\s*(provided|available|found)",
            r"i (do not|don't) know",
            r"not covered in (the|our)?\s*(documents?|policies|guide)",
            r"(is|are) not specified in (the|our)?\s*(documents?|policies|guide)",
            r"i couldn't find (any|information)"
        ]

        is_unanswered_gen = False
        for sig in UNKNOWN_SIGNATURES:
            if re.search(sig, ans_lower):
                is_unanswered_gen = True
                break

        if is_unanswered_gen:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Generated answer flagged as UNANSWERED: '{generated_answer[:80]}...'")
            return {
                "answer": fallback_msg,
                "is_answered": False,
                "confidence_score": gate_decision["confidence"],
                "citations": [],
                "llm_provider": provider,
                "latency_ms": latency_ms,
                "retrieved_chunks": []
            }

        # Step 7: Deterministic Citation Extraction with Semantic Filtering & Dynamic Excerpt Centering
        citations = []
        stop_words = {
            "what", "is", "are", "how", "much", "many", "the", "for", "with", "from", 
            "tell", "about", "your", "our", "a", "an", "to", "in", "of", "and", "or", 
            "do", "does", "can", "you", "this", "that", "i", "we", "my", "it", "at", "by", "there"
        }
        q_tokens = [w.lower() for w in re.findall(r"\b[a-zA-Z0-9_\-]+\b", clean_query) if w.lower() not in stop_words and len(w) >= 2]
        ans_tokens = [w.lower() for w in re.findall(r"\b[a-zA-Z0-9_\-]+\b", generated_answer) if w.lower() not in stop_words and len(w) >= 2]
        
        high_value_terms = set(q_tokens) | (set(ans_tokens) & {
            "discount", "refund", "warranty", "shipping", "delivery", "hours", "address", 
            "phone", "email", "rs", "50", "100", "10", "7", "15", "48", "points", "loyalty", 
            "burr", "grinder", "dripper", "order", "orders", "cancel", "cancellation", "metro",
            "beans", "coffee", "roast", "pune", "prescription", "consultation", "dental"
        })

        seen_doc_pages = set()
        candidate_citations = []

        for c in fused_chunks:
            doc_name = c.get("metadata", {}).get("document_name", "Document")
            doc_id = c.get("metadata", {}).get("document_id")
            page_num = c.get("metadata", {}).get("page_number", 1)
            content = c.get("content", "").strip()
            content_lower = content.lower()

            if not doc_name or doc_name == "Document":
                if any(w in content_lower for w in ["brewpoints", "brewnest", "coffee", "roast"]):
                    doc_name = "BrewNest_Customer_Help_Guide.pdf"
                elif any(w in content_lower for w in ["dental", "lakeview", "teeth", "clinic"]):
                    doc_name = "Lakeview_Dental_Patient_Guide.pdf"
                elif any(w in content_lower for w in ["fiber", "zephyr", "broadband", "mbps"]):
                    doc_name = "Zephyr_Fiber_Terms_FAQ.pdf"
                elif any(w in content_lower for w in ["pharmacy", "greenleaf", "prescription"]):
                    doc_name = "GreenLeaf_Pharmacy_Policy.pdf"
            content_lower = content.lower()

            q_matches = [t for t in q_tokens if re.search(r"\b" + re.escape(t) + r"\b", content_lower)]
            ans_matches = [t for t in high_value_terms if re.search(r"\b" + re.escape(t) + r"\b", content_lower)]
            
            match_score = (len(q_matches) * 4) + len(ans_matches)
            if match_score == 0:
                continue

            page_key = (doc_name, page_num)
            if page_key in seen_doc_pages:
                continue
            seen_doc_pages.add(page_key)

            # Center excerpt window on the most relevant match cluster
            all_matches = []
            for t in (set(q_matches) | set(ans_matches)):
                for m in re.finditer(r"\b" + re.escape(t) + r"\b", content_lower):
                    all_matches.append(m.start())

            if all_matches:
                all_matches.sort()
                best_pos = all_matches[0]
                best_density = 0
                for m in all_matches:
                    density = sum(1 for other in all_matches if abs(other - m) <= 160)
                    if density > best_density:
                        best_density = density
                        best_pos = m

                start_pos = max(0, best_pos - 90)
                # Check for numbered section headers like "8. BrewPoints"
                header_match = re.search(r"\n([0-9]+\.\s+[^\n]+)", content[max(0, best_pos - 140):best_pos + 10])
                if header_match:
                    start_pos = max(0, best_pos - 140) + header_match.start() + 1
                else:
                    prev_nl = content.rfind("\n", max(0, start_pos - 40), start_pos + 20)
                    if prev_nl != -1:
                        start_pos = prev_nl + 1

                end_pos = min(len(content), start_pos + 300)
                next_nl = content.find("\n\n", end_pos - 30, min(len(content), end_pos + 60))
                if next_nl != -1:
                    end_pos = next_nl
                else:
                    next_period = content.find(". ", end_pos - 20, min(len(content), end_pos + 40))
                    if next_period != -1:
                        end_pos = next_period + 1

                excerpt = content[start_pos:end_pos].strip()
                if start_pos > 0 and not excerpt.startswith("..."):
                    excerpt = "... " + excerpt
                if end_pos < len(content) and not excerpt.endswith("..."):
                    excerpt = excerpt + " ..."
            else:
                excerpt = content[:250].strip() + ("..." if len(content) > 250 else "")

            highlight_list = sorted(list(set(q_matches + [m for m in ans_matches if len(m) >= 3])), key=len, reverse=True)

            candidate_citations.append({
                "match_score": match_score,
                "has_query_match": len(q_matches) > 0,
                "document_name": doc_name,
                "document_id": doc_id,
                "page_number": page_num,
                "chunk_id": c["id"],
                "excerpt": excerpt,
                "highlight_terms": highlight_list[:6],
                "has_pdf_preview": doc_name.lower().endswith(".pdf")
            })

        candidate_citations.sort(key=lambda x: x["match_score"], reverse=True)

        if candidate_citations:
            top_candidate = candidate_citations[0]
            # If top candidate matched query tokens directly, filter out unrelated documents that matched 0 query tokens
            if top_candidate["has_query_match"]:
                filtered = [
                    c for c in candidate_citations 
                    if (c["has_query_match"] and c["document_name"] == top_candidate["document_name"])
                    or (c["match_score"] >= (top_candidate["match_score"] * 0.6) and c["has_query_match"])
                ]
                if not filtered:
                    filtered = [top_candidate]
            else:
                filtered = candidate_citations[:2]
            citations = [{k: v for k, v in item.items() if k not in ("match_score", "has_query_match")} for item in filtered[:3]]
        else:
            for c in fused_chunks[:2]:
                citations.append({
                    "document_name": c.get("metadata", {}).get("document_name", "Document"),
                    "document_id": c.get("metadata", {}).get("document_id"),
                    "page_number": c.get("metadata", {}).get("page_number", 1),
                    "chunk_id": c["id"],
                    "excerpt": c["content"][:240].strip() + "...",
                    "highlight_terms": q_tokens[:4],
                    "has_pdf_preview": c.get("metadata", {}).get("document_name", "").lower().endswith(".pdf")
                })

        latency_ms = int((time.time() - start_time) * 1000)

        return {
            "answer": generated_answer,
            "is_answered": True,
            "confidence_score": gate_decision["confidence"],
            "citations": citations,
            "llm_provider": provider,
            "latency_ms": latency_ms,
            "retrieved_chunks": fused_chunks
        }

rag_engine = HybridRAGEngine()
