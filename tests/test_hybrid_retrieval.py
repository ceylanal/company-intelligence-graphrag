"""Unit and comparison tests for Hybrid Vector + Graph Retrieval (Day 24)."""

from unittest.mock import MagicMock

from company_graphrag.graph.retrieval import MultiHopGraphRetriever
from company_graphrag.retrieval import HybridRetriever, RetrievalMode
from company_graphrag.retrieval.models import SearchHit, SearchResponse
from company_graphrag.retrieval.vector_retriever import VectorRetriever
from company_graphrag.storage import Neo4jGraphStore


def test_auto_routing_logic() -> None:
    """Test question auto-routing logic across vector, graph, and hybrid."""
    retriever = HybridRetriever()

    # Graph indicator
    assert retriever.determine_retrieval_mode("ASELSAN'ın ürünleri nelerdir?") == RetrievalMode.GRAPH_ONLY

    # Vector indicator
    assert (
        retriever.determine_retrieval_mode("ASELSAN'ın sürdürülebilirlik yaklaşımını açıkla")
        == RetrievalMode.VECTOR_ONLY
    )

    # Hybrid indicator (complex multi-domain)
    assert retriever.determine_retrieval_mode("ASELSAN 2024 cirosu ve ürün grupları nelerdir?") == RetrievalMode.HYBRID


def test_hybrid_retriever_modes_mock() -> None:
    """Test vector_only, graph_only, and hybrid search modes."""
    # Mock Vector Retriever
    mock_vec = MagicMock(spec=VectorRetriever)
    mock_vec.retrieve.return_value = SearchResponse(
        query="ASELSAN ciro",
        hits=[
            SearchHit(
                chunk_id="chunk_v1",
                text="Aselsan 2024 yılında ciro artışı sağladı.",
                score=0.92,
                company="Aselsan",
                ticker="ASELS",
                year=2024,
                page_number=1,
                source_file="ASELS__2024.pdf",
            )
        ],
        total_hits=1,
        execution_time_ms=1.5,
    )

    # Mock Graph Store
    store = Neo4jGraphStore(mock_mode=True)
    g_retriever = MultiHopGraphRetriever(neo4j_store=store)

    hybrid = HybridRetriever(vector_retriever=mock_vec, graph_retriever=g_retriever)

    # 1. VECTOR_ONLY mode
    res_v = hybrid.search("ASELSAN ciro", mode=RetrievalMode.VECTOR_ONLY)
    assert res_v.mode_executed == RetrievalMode.VECTOR_ONLY
    assert len(res_v.results) == 1
    assert res_v.results[0].source_retriever == "vector"

    # 2. GRAPH_ONLY mode
    res_g = hybrid.search("ASELSAN'ın ürünleri nelerdir?", mode=RetrievalMode.GRAPH_ONLY)
    assert res_g.mode_executed == RetrievalMode.GRAPH_ONLY

    # 3. HYBRID mode
    res_h = hybrid.search("ASELSAN 2024 cirosu ve ürün grupları", mode=RetrievalMode.HYBRID)
    assert res_h.mode_executed == RetrievalMode.HYBRID
    assert res_h.total_results >= 1

    store.close()


def test_hybrid_safe_fallback() -> None:
    """Test safe fallback to Vector RAG when Graph Retrieval fails."""
    mock_vec = MagicMock(spec=VectorRetriever)
    mock_vec.retrieve.return_value = SearchResponse(
        query="ASELSAN test",
        hits=[
            SearchHit(
                chunk_id="chk_fallback",
                text="Fallback text",
                score=0.88,
                company="Aselsan",
                ticker="ASELS",
                year=2024,
                page_number=1,
                source_file="ASELS__2024.pdf",
            )
        ],
        total_hits=1,
        execution_time_ms=1.0,
    )

    # Failing Graph Retriever
    failing_graph = MagicMock(spec=MultiHopGraphRetriever)
    failing_graph.search.side_effect = RuntimeError("Neo4j database connection timeout")

    hybrid = HybridRetriever(vector_retriever=mock_vec, graph_retriever=failing_graph)

    res = hybrid.search("ASELSAN test", mode=RetrievalMode.HYBRID)
    assert len(res.results) >= 1
    assert res.results[0].chunk_id == "chk_fallback"
    assert any("fallback" in w.lower() for w in res.warnings)
