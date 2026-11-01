import time
import logging
from typing import List, Dict, Any, Optional
from app.config import settings
from app.services.vector_store import vector_store_service
from app.services.bm25_store import bm25_store_service
from app.services.rrf import reciprocal_rank_fusion
from app.services.circuit_breaker import GreetingInterceptor, circuit_breaker
from app.services.llm_client import llm_client
from app.services.guardrails import guardrails_service

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

        # Step 1.5: Typo Correction & Normalization against Knowledge Base
        import difflib
        import re
        clean_query = sanitized_query
        vocab = bm25_store_service.get_vocabulary(business_id)
        if vocab:
            tokens = sanitized_query.split()
            corrected = []
            for tok in tokens:
                alph = re.sub(r"[^a-zA-Z]", "", tok.lower())
                if len(alph) > 3 and alph not in vocab:
                    matches = difflib.get_close_matches(alph, list(vocab), n=1, cutoff=0.74)
                    if matches:
                        corrected.append(matches[0])
                        continue
                corrected.append(tok)
            clean_query = " ".join(corrected)
            if clean_query.lower() != user_query.lower():
                logger.info(f"Query typo corrected: '{user_query}' -> '{clean_query}'")

        # Step 2: Multi-Hybrid Retrieval (Dense Vector + Sparse BM25)
        dense_hits = await vector_store_service.search(business_id, clean_query, top_k=10)
        sparse_hits = bm25_store_service.search(business_id, clean_query, top_k=10)

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
            threshold=settings.CONFIDENCE_THRESHOLD
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

        # Step 6: Post-generation Unknown check
        if "[UNKNOWN]" in generated_answer or generated_answer.strip() == "[UNKNOWN]":
            latency_ms = int((time.time() - start_time) * 1000)
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
