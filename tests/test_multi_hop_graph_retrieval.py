"""Unit and integration tests for Multi-Hop Graph Retrieval and Intent Extraction (Day 23)."""

from pathlib import Path

from company_graphrag.graph.ingestion import GraphIngestionPipeline
from company_graphrag.graph.retrieval import CypherQueryBuilder, GraphIntentExtractor, MultiHopGraphRetriever
from company_graphrag.storage import Neo4jGraphStore


def test_intent_extractor_categories() -> None:
    """Test extracting query intents across sample question types."""
    extractor = GraphIntentExtractor()

    # Question 1: Company Products (1-hop)
    i1 = extractor.extract_intent("ASELSAN'ın ürünleri nelerdir?")
    assert i1.starting_ticker == "ASELS"
    assert "Product" in i1.target_node_labels
    assert "PRODUCES" in i1.allowed_rel_types
    assert i1.max_hops == 1

    # Question 2: Same Sector Competitors (2-hop)
    i2 = extractor.extract_intent("Akbank ile aynı sektörde faaliyet gösteren şirketler hangileridir?")
    assert i2.starting_ticker == "AKBNK"
    assert "Sector" in i2.target_node_labels or "Company" in i2.target_node_labels
    assert i2.max_hops == 2

    # Question 3: Financial Metrics & Year Filter (2-hop)
    i3 = extractor.extract_intent("THY 2024 yılı cirosu nedir?")
    assert i3.starting_ticker == "THYAO"
    assert i3.year_filter == 2024
    assert "FinancialMetric" in i3.target_node_labels


def test_cypher_builder_parameterization() -> None:
    """Verify parameterized Cypher building and allowlist safety."""
    extractor = GraphIntentExtractor()
    builder = CypherQueryBuilder()

    intent = extractor.extract_intent("ASELSAN 2024 ürünleri nelerdir?", max_hops=1)
    cypher, params = builder.build_multi_hop_query(intent)

    # Parametrized checks
    assert "$ticker" in cypher
    assert "$target_labels" in cypher
    assert params["ticker"] == "ASELS"
    assert params["year"] == 2024
    assert "ASELSAN" not in cypher  # User text not concatenated directly


def test_multi_hop_retriever_search_mock(tmp_path: Path) -> None:
    """Test multi-hop retrieval over ingested graph dataset."""
    store = Neo4jGraphStore(mock_mode=True)
    pipeline = GraphIngestionPipeline(neo4j_store=store)

    # Ingest sample dataset
    sample_dir = Path("data/graph/sample_day19")
    pipeline.run_pipeline(sample_dir, checkpoint_path=tmp_path / "chk_mh.json")

    retriever = MultiHopGraphRetriever(neo4j_store=store)

    # Test Query 1: 1-Hop query
    res1 = retriever.search("ASELSAN kârlılık", max_hops=1)
    assert res1.query == "ASELSAN kârlılık"
    assert res1.total_paths_found >= 1
    assert res1.results[0].relevance_score > 0.0
    assert res1.results[0].lineage is not None

    store.close()
