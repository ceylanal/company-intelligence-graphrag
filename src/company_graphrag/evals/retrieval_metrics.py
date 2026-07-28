"""Retrieval metrics calculation module: Recall@k, Precision@k, MRR, nDCG@k, Lineage Recall."""

import math

from company_graphrag.evals.models import RetrievalMetricsResult


def calculate_recall_at_k(retrieved_ids: list[str], ground_truth_ids: list[str], k: int) -> float:
    """Calculate Recall@K: fraction of relevant ground truth items retrieved in top-K."""
    if not ground_truth_ids:
        return 1.0
    top_k_retrieved = set(retrieved_ids[:k])
    gt_set = set(ground_truth_ids)
    hits = top_k_retrieved & gt_set
    return round(len(hits) / len(gt_set), 4)


def calculate_precision_at_k(retrieved_ids: list[str], ground_truth_ids: list[str], k: int) -> float:
    """Calculate Precision@K: fraction of top-K retrieved items that are relevant."""
    if k <= 0:
        return 0.0
    top_k_retrieved = retrieved_ids[:k]
    if not top_k_retrieved:
        return 0.0
    gt_set = set(ground_truth_ids)
    hits = sum(1 for r_id in top_k_retrieved if r_id in gt_set)
    return round(hits / len(top_k_retrieved), 4)


def calculate_mrr(retrieved_ids: list[str], ground_truth_ids: list[str]) -> float:
    """Calculate Mean Reciprocal Rank (MRR): 1 / rank of first relevant item."""
    if not ground_truth_ids or not retrieved_ids:
        return 0.0
    gt_set = set(ground_truth_ids)
    for rank, r_id in enumerate(retrieved_ids, start=1):
        if r_id in gt_set:
            return round(1.0 / rank, 4)
    return 0.0


def calculate_ndcg_at_k(retrieved_ids: list[str], ground_truth_ids: list[str], k: int) -> float:
    """Calculate Normalized Discounted Cumulative Gain (nDCG@K)."""
    if not ground_truth_ids or not retrieved_ids:
        return 0.0
    gt_set = set(ground_truth_ids)
    top_k_retrieved = retrieved_ids[:k]

    dcg = 0.0
    for i, r_id in enumerate(top_k_retrieved, start=1):
        rel = 1.0 if r_id in gt_set else 0.0
        dcg += rel / math.log2(i + 1)

    # Ideal DCG (all relevant items at top)
    idcg = 0.0
    ideal_hits = min(k, len(gt_set))
    for i in range(1, ideal_hits + 1):
        idcg += 1.0 / math.log2(i + 1)

    if idcg == 0.0:
        return 0.0
    return round(dcg / idcg, 4)


def calculate_lineage_recall(retrieved_items: list[str], expected_items: list[str]) -> float:
    """Calculate recall for generic lineage items (source files, page numbers, or chunk IDs)."""
    if not expected_items:
        return 1.0
    if not retrieved_items:
        return 0.0
    retrieved_set = {str(item).lower() for item in retrieved_items}
    expected_set = {str(item).lower() for item in expected_items}
    hits = retrieved_set & expected_set
    return round(len(hits) / len(expected_set), 4)


def evaluate_retrieval(
    retrieved_chunk_ids: list[str],
    expected_chunk_ids: list[str],
    retrieved_sources: list[str] | None = None,
    expected_sources: list[str] | None = None,
    retrieved_pages: list[int] | None = None,
    expected_pages: list[int] | None = None,
) -> RetrievalMetricsResult:
    """Aggregate all retrieval performance metrics into RetrievalMetricsResult."""
    retrieved_sources = retrieved_sources or []
    expected_sources = expected_sources or []
    retrieved_pages = retrieved_pages or []
    expected_pages = expected_pages or []

    return RetrievalMetricsResult(
        recall_at_1=calculate_recall_at_k(retrieved_chunk_ids, expected_chunk_ids, 1),
        recall_at_3=calculate_recall_at_k(retrieved_chunk_ids, expected_chunk_ids, 3),
        recall_at_5=calculate_recall_at_k(retrieved_chunk_ids, expected_chunk_ids, 5),
        recall_at_10=calculate_recall_at_k(retrieved_chunk_ids, expected_chunk_ids, 10),
        precision_at_1=calculate_precision_at_k(retrieved_chunk_ids, expected_chunk_ids, 1),
        precision_at_3=calculate_precision_at_k(retrieved_chunk_ids, expected_chunk_ids, 3),
        precision_at_5=calculate_precision_at_k(retrieved_chunk_ids, expected_chunk_ids, 5),
        precision_at_10=calculate_precision_at_k(retrieved_chunk_ids, expected_chunk_ids, 10),
        mrr=calculate_mrr(retrieved_chunk_ids, expected_chunk_ids),
        ndcg_at_5=calculate_ndcg_at_k(retrieved_chunk_ids, expected_chunk_ids, 5),
        ndcg_at_10=calculate_ndcg_at_k(retrieved_chunk_ids, expected_chunk_ids, 10),
        source_recall=calculate_lineage_recall(retrieved_sources, expected_sources),
        page_recall=calculate_lineage_recall([str(p) for p in retrieved_pages], [str(p) for p in expected_pages]),
        chunk_recall=calculate_recall_at_k(retrieved_chunk_ids, expected_chunk_ids, 10),
    )
