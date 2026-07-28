"""Unit tests for RetrievalReranker and hybrid MMR diversity (Day 15)."""

from company_graphrag.retrieval.models import SearchHit
from company_graphrag.retrieval.reranker import RetrievalReranker, compute_lexical_term_overlap
from company_graphrag.retrieval.vector_retriever import VectorRetriever


def create_hit(
    chunk_id: str,
    text: str,
    score: float,
    ticker: str = "ASELS",
    year: int = 2024,
    page: int = 1,
    doc_id: str = "ASELS_2024",
) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        text=text,
        score=score,
        company="Aselsan A.Ş.",
        ticker=ticker,
        year=year,
        report_type="annual_report",
        page_number=page,
        source_file=f"{ticker}__{year}__annual_report__tr.pdf",
        document_id=doc_id,
    )


def test_compute_lexical_term_overlap() -> None:
    """Test lexical term overlap ratio calculation."""
    q = "ASELSAN 2024 ciro ve gelir performansı"
    txt1 = "ASELSAN’ın 2024 yılında cirosu ve gelir performansı çok yüksekti"
    txt2 = "Akbank dijital bankacılık büyümesi"

    assert compute_lexical_term_overlap(q, txt1) >= 0.5
    assert compute_lexical_term_overlap(q, txt2) == 0.0


def test_normal_reranking() -> None:
    """Scenario 1: Normal reranking produces enriched hits with original and reranked ranks."""
    h1 = create_hit("c1", "Genel faaliyetler.", 0.85)
    h2 = create_hit("c2", "ASELSAN 2024 net ciro ve gelir performansı.", 0.84)

    reranker = RetrievalReranker()
    reranked = reranker.rerank("ASELSAN 2024 ciro", [h1, h2], top_k=2)

    assert len(reranked) == 2
    assert reranked[0].chunk_id == "c2"  # Lexical match boosts c2 over c1!
    assert reranked[0].reranked_rank == 1
    assert reranked[0].original_rank == 2
    assert reranked[0].vector_score is not None
    assert reranked[0].lexical_score is not None


def test_reranking_disabled_compatibility(seeded_vector_retriever: VectorRetriever) -> None:
    """Scenario 2: Reranking disabled preserves original vector order."""
    from company_graphrag.rag.pipeline import VectorRAGPipeline

    retriever = seeded_vector_retriever
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("ASELSAN ciro", top_k=3, use_reranking=False)
    assert res.retrieved_count > 0
    assert "reranking_ms" not in res.stage_timings_ms
    pipeline.close()


def test_duplicate_chunk_demotion() -> None:
    """Scenario 3: Duplicate/near-identical text receives diversity penalty."""
    txt = "ASELSAN 2024 yılı ciro ve ihracat rakamları 120 Milyar TL olarak gerçekleşti."
    h1 = create_hit("c1", txt, 0.88, page=1)
    h2 = create_hit("c2", txt, 0.87, page=2)  # Identical text
    h3 = create_hit("c3", "ASELSAN ihracat yapılan ülke sayısı 88'e ulaştı.", 0.80, page=10)

    reranker = RetrievalReranker(default_diversity_weight=0.5)
    reranked = reranker.rerank("ASELSAN ciro ihracat", [h1, h2, h3], top_k=3)

    assert reranked[0].chunk_id == "c1"
    # h3 (different topic) should be ranked before duplicate h2 due to diversity penalty!
    assert reranked[1].chunk_id == "c3"


def test_same_page_diversity_penalty() -> None:
    """Scenario 4: Demotion for multiple chunks coming from the exact same page."""
    h1 = create_hit("c1", "ASELSAN radar sistemleri üretimi.", 0.89, page=15)
    h2 = create_hit("c2", "ASELSAN elektro-optik ASELFLIR üretimi.", 0.88, page=15)  # Same page 15
    h3 = create_hit("c3", "ASELSAN yeni fabrika yatırımı.", 0.85, page=42)  # Page 42

    reranker = RetrievalReranker()
    reranked = reranker.rerank("ASELSAN üretim ve yatırım", [h1, h2, h3], top_k=3)

    assert reranked[0].chunk_id == "c1"
    assert reranked[1].chunk_id == "c3"  # Page 42 promoted over page 15 duplicate!
    assert reranked[2].diversity_penalty > 0.0


def test_metadata_filtered_reranking() -> None:
    """Scenario 5: Metadata match boost for query ticker/year."""
    h1 = create_hit("c1", "ASELSAN 2023 bilançosu.", 0.85, ticker="ASELS", year=2023)
    h2 = create_hit("c2", "ASELSAN 2024 cirosu.", 0.84, ticker="ASELS", year=2024)

    reranker = RetrievalReranker()
    reranked = reranker.rerank("ASELSAN 2024", [h1, h2], top_k=2, query_ticker="ASELS", query_year=2024)

    assert reranked[0].chunk_id == "c2"  # 2024 year match boosts c2
    assert reranked[0].metadata_score == 1.0


def test_low_score_candidates() -> None:
    """Scenario 6: Reranking low-score candidate pool."""
    h1 = create_hit("c1", "Düşük skorlu genel paragraf 1", 0.35)
    h2 = create_hit("c2", "Düşük skorlu ama ASELSAN içeren paragraf 2", 0.34)

    reranker = RetrievalReranker()
    reranked = reranker.rerank("ASELSAN", [h1, h2], top_k=2)

    assert len(reranked) == 2
    assert reranked[0].chunk_id == "c2"


def test_candidates_fewer_than_top_k() -> None:
    """Scenario 7: Candidates pool size smaller than top_k."""
    h1 = create_hit("c1", "Tek aday metni", 0.80)

    reranker = RetrievalReranker()
    reranked = reranker.rerank("Tek aday", [h1], top_k=5)

    assert len(reranked) == 1
    assert reranked[0].reranked_rank == 1


def test_empty_retrieval_reranking() -> None:
    """Scenario 8: Empty candidate list returns empty list."""
    reranker = RetrievalReranker()
    assert reranker.rerank("Sorgu", [], top_k=5) == []


def test_deterministic_reranking_repeatability() -> None:
    """Scenario 9: Reranking produces identical deterministic ordering across repeated calls."""
    h1 = create_hit("c1", "Faaliyet raporu genel özet", 0.85)
    h2 = create_hit("c2", "ASELSAN 2024 Ar-Ge harcamaları 53 Milyar TL", 0.82)
    h3 = create_hit("c3", "Akbank dijital müşteri sayısı", 0.79)

    reranker = RetrievalReranker()
    r1 = reranker.rerank("ASELSAN 2024 Ar-Ge", [h1, h2, h3], top_k=3)
    r2 = reranker.rerank("ASELSAN 2024 Ar-Ge", [h1, h2, h3], top_k=3)

    assert [x.chunk_id for x in r1] == [x.chunk_id for x in r2]
    assert [x.final_score for x in r1] == [x.final_score for x in r2]
