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

        # Step 2: Multi-Hybrid Retrieval (Dense Vector + Sparse BM25)
        dense_hits = await vector_store_service.search(business_id, expanded_query, top_k=10)
        sparse_hits = bm25_store_service.search(business_id, expanded_query, top_k=10)

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

        # Step 7: Deterministic Citation Extraction
        citations = []
        for c in fused_chunks[:3]:
            doc_name = c.get("metadata", {}).get("document_name", "Document")
            page_num = c.get("metadata", {}).get("page_number", 1)
            content_snippet = c["content"].strip()
            excerpt = content_snippet[:220] + ("..." if len(content_snippet) > 220 else "")
            
            citations.append({
                "document_name": doc_name,
                "page_number": page_num,
                "chunk_id": c["id"],
                "excerpt": excerpt
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
