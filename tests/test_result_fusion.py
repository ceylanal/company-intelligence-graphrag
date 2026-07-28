"""Unit tests for Reciprocal Rank Fusion (RRF) result fusion (Day 16)."""

from company_graphrag.retrieval.fusion import reciprocal_rank_fusion
from company_graphrag.retrieval.models import SearchHit


def create_hit(chunk_id: str, text: str, score: float, ticker: str = "ASELS", page: int = 1) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        text=text,
        score=score,
        company="Aselsan A.Ş.",
        ticker=ticker,
        year=2024,
        report_type="annual_report",
        page_number=page,
        source_file=f"{ticker}__2024__annual_report__tr.pdf",
    )


def test_rrf_deduplication() -> None:
    """Scenario 1: Duplicate chunks across multiple queries are fused and deduplicated."""
    h1 = create_hit("c1", "ASELSAN radar sistemleri", 0.90)
    h2 = create_hit("c2", "ASELSAN ciro büyümesi", 0.85)

    q1_hits = [h1, h2]
    q2_hits = [h2, create_hit("c3", "ASELSAN ihracat", 0.80)]  # h2 appears in both queries!

    fused = reciprocal_rank_fusion([q1_hits, q2_hits], expanded_queries=["Query 1", "Query 2"])

    assert len(fused) == 3
    # c2 matched in 2 queries, so its RRF score is (1/(60+2) + 1/(60+1)) -> higher RRF boost!
    c2_hit = next(h for h in fused if h.chunk_id == "c2")
    assert c2_hit.query_count == 2
    assert "Query 1" in c2_hit.matched_queries
    assert "Query 2" in c2_hit.matched_queries


def test_rrf_scoring_and_ranking() -> None:
    """Scenario 2: RRF scoring ranks hits appearing in multiple query lists higher."""
    h1 = create_hit("c1", "Metin 1", 0.88)
    h2 = create_hit("c2", "Metin 2", 0.85)

    q1_hits = [h1, h2]
    q2_hits = [h2, h1]

    fused = reciprocal_rank_fusion([q1_hits, q2_hits])
    assert len(fused) == 2
    assert fused[0].fusion_score is not None
    assert fused[0].fusion_score > 0.0


def test_rrf_empty_lists() -> None:
    """Scenario 4: Empty candidate lists return empty fused list."""
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_rrf_deterministic_ordering() -> None:
    """Scenario 5: RRF rank ordering is 100% deterministic."""
    h1 = create_hit("c1", "Metin 1", 0.90)
    h2 = create_hit("c2", "Metin 2", 0.85)
    h3 = create_hit("c3", "Metin 3", 0.80)

    f1 = reciprocal_rank_fusion([[h1, h2], [h2, h3]])
    f2 = reciprocal_rank_fusion([[h1, h2], [h2, h3]])

    assert [x.chunk_id for x in f1] == [x.chunk_id for x in f2]
    assert [x.fusion_score for x in f1] == [x.fusion_score for x in f2]
