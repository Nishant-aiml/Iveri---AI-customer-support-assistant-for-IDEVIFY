import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def reciprocal_rank_fusion(
    dense_hits: List[Dict[str, Any]],
    sparse_hits: List[Dict[str, Any]],
    k: int = 60,
    top_n: int = 5
) -> List[Dict[str, Any]]:
    """Merges Dense Vector search results with Sparse BM25 results using Reciprocal Rank Fusion (RRF).
    
    Formula: RRF_score(d) = Sum( 1 / (k + rank(d)) )
    
    Args:
        dense_hits: Ordered list from ChromaDB vector search
        sparse_hits: Ordered list from BM25 lexical search
        k: Smoothing constant (standard: 60)
        top_n: Maximum number of fused candidate chunks to return
        
    Returns:
        List[Dict[str, Any]]: Deduplicated, fused chunks ranked by RRF score
    """
    scores: Dict[str, float] = {}
    chunk_data: Dict[str, Dict[str, Any]] = {}
    dense_scores: Dict[str, float] = {}
    sparse_scores: Dict[str, float] = {}

    # 1. Process Dense hits (rank is 0-indexed)
    for rank, hit in enumerate(dense_hits):
        chunk_id = hit["id"]
        dense_scores[chunk_id] = hit.get("score", 0.0)
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank + 1))
        if chunk_id not in chunk_data:
            chunk_data[chunk_id] = {
                "id": chunk_id,
                "content": hit["content"],
                "metadata": hit.get("metadata", {})
            }

    # 2. Process Sparse BM25 hits
    for rank, hit in enumerate(sparse_hits):
        chunk_id = hit["id"]
        sparse_scores[chunk_id] = hit.get("score", 0.0)
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank + 1))
        if chunk_id not in chunk_data:
            chunk_data[chunk_id] = {
                "id": chunk_id,
                "content": hit["content"],
                "metadata": hit.get("metadata", {})
            }

    if not scores:
        return []

    # Sort descending by RRF score
    ranked_chunk_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

    # Normalize max RRF score to 1.0 scale
    max_possible = (1.0 / (k + 1)) + (1.0 / (k + 1))
    results: List[Dict[str, Any]] = []

    for cid in ranked_chunk_ids[:top_n]:
        raw_rrf = scores[cid]
        normalized_score = min(1.0, raw_rrf / max_possible)
        
        item = chunk_data[cid]
        results.append({
            "id": cid,
            "content": item["content"],
            "metadata": item["metadata"],
            "rrf_score": round(normalized_score, 4),
            "dense_similarity": round(dense_scores.get(cid, 0.0), 4),
            "sparse_score": round(sparse_scores.get(cid, 0.0), 4)
        })

    logger.debug(f"RRF fused {len(dense_hits)} dense + {len(sparse_hits)} sparse hits into {len(results)} chunks.")
    return results
