"""Result Fusion module implementing Reciprocal Rank Fusion (RRF) for multi-query retrieval."""

import time
from collections.abc import Sequence

import structlog

from company_graphrag.retrieval.models import SearchHit

logger = structlog.get_logger(__name__)


def reciprocal_rank_fusion(
    query_results: Sequence[Sequence[SearchHit]],
    expanded_queries: Sequence[str] | None = None,
    k: int = 60,
    top_k: int | None = None,
) -> list[SearchHit]:
    """Combine multi-query retrieval results using Reciprocal Rank Fusion (RRF)."""
    start_time = time.time()
    if not query_results:
        return []

    fused_map: dict[str, SearchHit] = {}
    rrf_scores: dict[str, float] = {}
    matched_queries_map: dict[str, list[str]] = {}
    best_ranks_map: dict[str, int] = {}

    for q_idx, hit_list in enumerate(query_results):
        q_label = (
            expanded_queries[q_idx] if expanded_queries and q_idx < len(expanded_queries) else f"Query_{q_idx + 1}"
        )

        for rank, hit in enumerate(hit_list, 1):
            cid = hit.chunk_id
            score = 1.0 / (k + rank)

            if cid not in rrf_scores:
                rrf_scores[cid] = score
                fused_map[cid] = hit.model_copy(deep=True)
                matched_queries_map[cid] = [q_label]
                best_ranks_map[cid] = rank
            else:
                rrf_scores[cid] += score
                if q_label not in matched_queries_map[cid]:
                    matched_queries_map[cid].append(q_label)
                if rank < best_ranks_map[cid]:
                    best_ranks_map[cid] = rank

    # Sort fused candidates by RRF score descending
    sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
    fused_hits: list[SearchHit] = []

    for idx, cid in enumerate(sorted_chunk_ids, 1):
        hit = fused_map[cid]
        hit.fusion_score = round(rrf_scores[cid], 6)
        hit.query_count = len(matched_queries_map[cid])
        hit.matched_queries = matched_queries_map[cid]
        hit.best_original_rank = best_ranks_map[cid]
        hit.score = hit.fusion_score
        hit.original_rank = idx
        fused_hits.append(hit)

    if top_k is not None:
        fused_hits = fused_hits[:top_k]

    duration = round((time.time() - start_time) * 1000, 2)
    logger.info(
        "reciprocal_rank_fusion completed",
        queries_in=len(query_results),
        total_unique_chunks=len(fused_hits),
        duration_ms=duration,
    )

    return fused_hits
