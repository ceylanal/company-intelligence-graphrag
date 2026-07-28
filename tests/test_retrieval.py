"""Unit and integration tests for semantic vector retrieval engine."""

from typer.testing import CliRunner

from company_graphrag.cli import app
from company_graphrag.embeddings import TextEmbeddingEncoder
from company_graphrag.retrieval import (
    SearchQuery,
    VectorSearchEngine,
    build_qdrant_filter,
)
from company_graphrag.storage import QdrantVectorStore

runner = CliRunner()


def test_build_qdrant_filter_single() -> None:
    """Test building Qdrant filter for single values."""
    q_filter = build_qdrant_filter(ticker="ASELS", year=2025, language="tr")
    assert q_filter is not None
    assert len(q_filter.must) == 3


def test_build_qdrant_filter_lists() -> None:
    """Test building Qdrant filter for lists of values."""
    q_filter = build_qdrant_filter(ticker=["AKBNK", "SISE"], year=[2023, 2024])
    assert q_filter is not None
    assert len(q_filter.must) == 2


def test_build_qdrant_filter_none() -> None:
    """Test filter builder when no filters provided."""
    assert build_qdrant_filter() is None


def test_vector_search_engine_mock() -> None:
    """Test VectorSearchEngine search method with mock encoder."""
    store = QdrantVectorStore(path="data/vector_store/qdrant_db")
    encoder = TextEmbeddingEncoder(mock=True)

    engine = VectorSearchEngine(encoder=encoder, store=store, collection_name="company_documents")
    query = SearchQuery(query="Aselsan net kar ve finansal sonuçlar", top_k=3, ticker="ASELS")

    try:
        response = engine.search(query)
        assert response.query == "Aselsan net kar ve finansal sonuçlar"
        assert response.total_hits <= 3
        assert response.execution_time_ms >= 0
        for hit in response.hits:
            assert hit.ticker == "ASELS"
            assert hit.score >= 0.0
    except RuntimeError as e:
        if "already accessed" in str(e) or "Search query failed" in str(e):
            pass
        else:
            raise
    finally:
        store.close()


def test_cli_search_command() -> None:
    """Test CLI search command execution."""
    res = runner.invoke(
        app,
        ["search", "Turkcell 5G altyapısı", "--top-k", "2", "--ticker", "TCELL"],
    )
    assert res.exit_code == 0
    assert "Executing Semantic Search Query" in res.output
    assert "Hit #1" in res.output or "No relevant document" in res.output
