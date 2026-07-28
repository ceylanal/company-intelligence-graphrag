"""Unit and integration tests for Vector RAG Retriever Pipeline (Day 11)."""

from company_graphrag.embeddings import TextEmbeddingEncoder
from company_graphrag.retrieval.vector_retriever import VectorRetriever, build_retriever_filter
from company_graphrag.storage import QdrantVectorStore


def test_build_retriever_filter_all() -> None:
    """Test building Qdrant filter with all parameters."""
    q_filter = build_retriever_filter(
        ticker="ASELS",
        year=2024,
        company="Aselsan A.Ş.",
        report_type="annual_report",
        language="tr",
    )
    assert q_filter is not None
    assert len(q_filter.must) == 5


def test_vector_retriever_empty_query() -> None:
    """Test empty and whitespace queries safely return empty response."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    res1 = retriever.retrieve("")
    assert res1.total_hits == 0
    assert len(res1.hits) == 0

    res2 = retriever.retrieve("   \n ")
    assert res2.total_hits == 0
    retriever.close()


def test_vector_retriever_mock_search() -> None:
    """Test VectorRetriever search with mock encoder and filter."""
    store = QdrantVectorStore(path="data/vector_store/qdrant_db")
    encoder = TextEmbeddingEncoder(mock=True)

    retriever = VectorRetriever(encoder=encoder, store=store, collection_name="company_documents")
    res = retriever.retrieve("Aselsan net kar performansı", top_k=3, ticker="ASELS", year=2025)

    assert res.query == "Aselsan net kar performansı"
    assert res.total_hits <= 3
    for hit in res.hits:
        assert hit.ticker == "ASELS"
        assert hit.year == 2025
        assert hit.chunk_id != ""
        assert hit.text != ""
        assert hit.source_file != ""
        assert hit.report_type == "annual_report"
    retriever.close()


def test_vector_retriever_10_smoke_queries() -> None:
    """Smoke test running 10 different financial queries through VectorRetriever."""
    retriever = VectorRetriever()

    test_queries = [
        ("ASELSAN'ın 2024 gelir performansı nedir?", "ASELS", 2024),
        ("yatırımlar", "ASELS", 2024),
        ("Akbank dijital bankacılık 2024 müşteri sayısı", "AKBNK", 2024),
        ("Ford Otosan electric vehicle investment", "FROTO", None),
        ("Turkcell fiber omurga altyapısı", "TCELL", 2024),
        ("THY yolcu kapasitesi ve filo uçak sayısı", "THYAO", 2023),
        ("Tüpraş rafineri kapasite kullanım oranı 2025", "TUPRS", 2025),
        ("Şişecam ambalaj camı üretimi ve ihracatı", "SISE", None),
        ("Koç Holding net aktif değeri ve kombine gelirler", "KCHOL", 2024),
        ("Migros yeni mağaza açılışları ve online satış", "MGROS", 2024),
    ]

    for q_str, ticker, year in test_queries:
        res = retriever.retrieve(query=q_str, top_k=2, ticker=ticker, year=year)
        assert res.total_hits >= 0
        if res.hits:
            hit = res.hits[0]
            assert hit.ticker == ticker if ticker else True
            assert hit.chunk_id != ""
            assert hit.text != ""

    retriever.close()
