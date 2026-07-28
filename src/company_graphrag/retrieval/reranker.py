"""Lightweight, deterministic Retrieval Reranker combining vector score, term overlap, metadata match, and MMR diversity penalty."""

import re
import time
from collections.abc import Sequence

import structlog

from company_graphrag.retrieval.models import SearchHit

logger = structlog.get_logger(__name__)


def compute_lexical_term_overlap(query: str, text: str) -> float:
    """Compute normalized token overlap ratio between query terms and document text."""
    if not query or not text:
        return 0.0
    q_terms = set(re.findall(r"\w+", query.lower()))
    t_terms = set(re.findall(r"\w+", text.lower()))

    # Filter short stop words
    stop_words = {"ve", "veya", "bir", "ile", "için", "de", "da", "bu", "şu", "nedir", "nasıldı", "hakkında", "göre"}
    q_terms = {t for t in q_terms if t not in stop_words and len(t) > 1}

    if not q_terms:
        return 0.0

    overlap = len(q_terms & t_terms)
    return round(overlap / len(q_terms), 4)


def compute_text_overlap(text1: str, text2: str) -> float:
    """Compute character n-gram text overlap between two chunks."""
    set1 = set(text1.lower().split())
    set2 = set(text2.lower().split())
    if not set1 or not set2:
        return 0.0
    inter = len(set1 & set2)
    union = len(set1 | set2)
    return inter / union if union > 0 else 0.0


class RetrievalReranker:
    """Deterministic Hybrid Reranker with MMR Diversity Penalty."""

    def __init__(
        self,
        vector_weight: float = 0.5,
        lexical_weight: float = 0.3,
        metadata_weight: float = 0.2,
        default_diversity_weight: float = 0.2,
    ) -> None:
        self.vector_weight = vector_weight
        self.lexical_weight = lexical_weight
        self.metadata_weight = metadata_weight
        self.default_diversity_weight = default_diversity_weight

    def rerank(
        self,
        query: str,
        candidate_hits: Sequence[SearchHit],
        top_k: int = 5,
        query_ticker: str | None = None,
        query_year: int | None = None,
        diversity_weight: float | None = None,
    ) -> list[SearchHit]:
        """Rerank candidate pool and return top_k hits enriched with detailed scores."""
        start_time = time.time()
        if not candidate_hits:
            return []

        div_w = diversity_weight if diversity_weight is not None else self.default_diversity_weight
        hits = [hit.model_copy(deep=True) for hit in candidate_hits]

        # Attach original ranks
        for idx, hit in enumerate(hits, 1):
            hit.original_rank = idx

        for h in hits:
            # Vector score is cosine similarity in [0, 1] range
            h.vector_score = round(max(0.0, min(1.0, float(h.score))), 4)

            # Lexical Term Overlap Score
            h.lexical_score = compute_lexical_term_overlap(query, h.text)

            # Metadata Match Score
            m_score = 1.0
            if query_ticker and h.ticker.upper() != query_ticker.upper():
                m_score -= 0.5
            if query_year and h.year != query_year:
                m_score -= 0.5
            h.metadata_score = max(0.0, m_score)

        # Iterative Diversity Selection (MMR-Style)
        selected_hits: list[SearchHit] = []
        remaining_hits = hits.copy()

        while remaining_hits and len(selected_hits) < top_k:
            best_candidate = None
            best_final_score = -999.0
            best_penalty = 0.0

            for candidate in remaining_hits:
                base_score = (
                    self.vector_weight * (candidate.vector_score or 0.0)
                    + self.lexical_weight * (candidate.lexical_score or 0.0)
                    + self.metadata_weight * (candidate.metadata_score or 0.0)
                )

                # Compute Diversity Penalty against already selected hits
                penalty = 0.0
                if selected_hits:
                    for sel in selected_hits:
                        # Same Document Page Penalty
                        if sel.document_id == candidate.document_id and sel.page_number == candidate.page_number:
                            penalty += 0.15

                        # Text Overlap Penalty
                        t_sim = compute_text_overlap(candidate.text, sel.text)
                        if t_sim > 0.6:
                            penalty += t_sim * div_w

                final_score = base_score - penalty

                if final_score > best_final_score:
                    best_final_score = final_score
                    best_candidate = candidate
                    best_penalty = penalty

            if best_candidate:
                best_candidate.diversity_penalty = round(best_penalty, 4)
                best_candidate.final_score = round(best_final_score, 4)
                best_candidate.reranked_rank = len(selected_hits) + 1
                best_candidate.score = best_candidate.final_score
                selected_hits.append(best_candidate)
                remaining_hits.remove(best_candidate)

        duration = round((time.time() - start_time) * 1000, 2)
        logger.info(
            "RetrievalReranker completed reranking",
            candidates_in=len(candidate_hits),
            top_k_out=len(selected_hits),
            duration_ms=duration,
        )
        return selected_hits
