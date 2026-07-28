"""Comprehensive unit tests for Agent Tools, Adapters, Read-Only Security, and Citation Validation."""

from unittest.mock import MagicMock

import pytest

from company_graphrag.agents.schema import EvidenceItem
from company_graphrag.agents.tools.base import ToolErrorCode, sort_evidence_deterministically
from company_graphrag.agents.tools.citation_tool import ValidateCitationTool
from company_graphrag.agents.tools.models import (
    FetchChunkInput,
    FetchSourceContextInput,
    GraphSearchInput,
    HybridSearchInput,
    InspectCompanyInput,
    InspectReportInput,
    ValidateCitationInput,
    VectorSearchInput,
)
from company_graphrag.agents.tools.neo4j_adapter import Neo4jToolAdapter, validate_read_only_cypher
from company_graphrag.agents.tools.qdrant_adapter import QdrantToolAdapter
from company_graphrag.agents.tools.search_tools import (
    FetchChunkTool,
    FetchSourceContextTool,
    GraphSearchTool,
    HybridSearchTool,
    InspectCompanyTool,
    InspectReportTool,
    VectorSearchTool,
)


@pytest.fixture
def sample_evidence():
    return EvidenceItem(
        company="Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
        ticker="ASELS",
        year=2024,
        report="annual_report",
        report_type="annual_report",
        chunk_id="chk_asels_001",
        page_number=19,
        source_file="ASELS__2024__annual_report__tr.pdf",
        retrieval_method="vector_search",
        content="ASELSAN'ın 2024 yılı cirosu 120 Milyar TL olarak gerçekleşmiştir.",
        text="ASELSAN'ın 2024 yılı cirosu 120 Milyar TL olarak gerçekleşmiştir.",
        relevance_score=0.95,
        citation_status="unverified",
    )


def test_vector_search_tool_valid_call(sample_evidence):
    """Test valid execution of VectorSearchTool returning chunk hits."""
    mock_adapter = MagicMock(spec=QdrantToolAdapter)
    mock_adapter.search.return_value = [sample_evidence]

    tool = VectorSearchTool(qdrant_adapter=mock_adapter)
    res = tool.run(VectorSearchInput(query="ASELSAN ciro", ticker="ASELS", year=2024, top_k=5))

    assert res.success is True
    assert res.record_count == 1
    assert res.data.hits[0].ticker == "ASELS"
    assert res.data.hits[0].chunk_id == "chk_asels_001"
    assert res.data.hits[0].company == "Aselsan Elektronik Sanayi ve Ticaret A.Ş."


def test_vector_search_tool_invalid_input():
    """Test VectorSearchTool error handling for empty query string."""
    tool = VectorSearchTool(qdrant_adapter=MagicMock())
    res = tool.run(VectorSearchInput(query="   "))

    assert res.success is False
    assert res.error_code == ToolErrorCode.INVALID_INPUT
    assert "cannot be empty" in res.error_message


def test_vector_search_tool_empty_retrieval():
    """Test VectorSearchTool handling empty retrieval results cleanly."""
    mock_adapter = MagicMock(spec=QdrantToolAdapter)
    mock_adapter.search.return_value = []

    tool = VectorSearchTool(qdrant_adapter=mock_adapter)
    res = tool.run(VectorSearchInput(query="Bilinmeyen Şirket", top_k=5))

    assert res.success is True
    assert res.record_count == 0
    assert res.data.hits == []


def test_tool_timeout_simulation():
    """Test tool timeout handling."""
    mock_adapter = MagicMock(spec=QdrantToolAdapter)
    mock_adapter.search.side_effect = TimeoutError("Vector DB request timeout")

    tool = VectorSearchTool(qdrant_adapter=mock_adapter)
    res = tool.run(VectorSearchInput(query="ASELSAN ciro"))

    assert res.success is False
    assert res.error_code == ToolErrorCode.TIMEOUT
    assert "timed out" in res.error_message


def test_tool_backend_error_simulation():
    """Test tool backend exception handling."""
    mock_adapter = MagicMock(spec=QdrantToolAdapter)
    mock_adapter.search.side_effect = RuntimeError("Connection lost to Qdrant cluster")

    tool = VectorSearchTool(qdrant_adapter=mock_adapter)
    res = tool.run(VectorSearchInput(query="ASELSAN ciro"))

    assert res.success is False
    assert res.error_code == ToolErrorCode.BACKEND_ERROR
    assert "Backend execution error" in res.error_message


def test_vector_search_max_results_capping(sample_evidence):
    """Test max_results capping when top_k > 50 is passed."""
    mock_adapter = MagicMock(spec=QdrantToolAdapter)
    mock_adapter.search.return_value = [sample_evidence]

    tool = VectorSearchTool(qdrant_adapter=mock_adapter)
    tool.run(VectorSearchInput(query="ASELSAN", top_k=100))

    mock_adapter.search.assert_called_once()
    assert mock_adapter.search.call_args.kwargs["top_k"] == 50


def test_read_only_cypher_validation():
    """Test strict read-only Cypher query validation against mutation keywords."""
    # Valid read-only queries
    validate_read_only_cypher("MATCH (c:Company {ticker: 'ASELS'})-[r:PRODUCES]->(p:Product) RETURN c, r, p")
    validate_read_only_cypher("MATCH (n) WHERE n.year = 2024 RETURN count(n)")

    # Forbidden mutation queries
    with pytest.raises(ValueError) as exc1:
        validate_read_only_cypher("CREATE (c:Company {name: 'Malicious'})")
    assert "READ_ONLY_VIOLATION" in str(exc1.value)

    with pytest.raises(ValueError) as exc2:
        validate_read_only_cypher("MATCH (c:Company) DETACH DELETE c")
    assert "READ_ONLY_VIOLATION" in str(exc2.value)

    with pytest.raises(ValueError) as exc3:
        validate_read_only_cypher("MATCH (c:Company {ticker: 'ASELS'}) SET c.name = 'Hacked'")
    assert "READ_ONLY_VIOLATION" in str(exc3.value)


def test_graph_search_tool_read_only_enforcement():
    """Test GraphSearchTool rejecting mutation Cypher queries."""
    tool = GraphSearchTool(neo4j_adapter=MagicMock())
    res = tool.run(GraphSearchInput(raw_query="MATCH (n) DELETE n"))

    assert res.success is False
    assert res.error_code == ToolErrorCode.READ_ONLY_VIOLATION
    assert "READ_ONLY_VIOLATION" in res.error_message


def test_graph_search_tool_valid_call(sample_evidence):
    """Test valid execution of GraphSearchTool returning path nodes & edges."""
    sample_evidence.retrieval_method = "graph_traversal"
    sample_evidence.graph_path = {"path_id": "p1", "hops": 2, "nodes": [], "edges": []}

    mock_adapter = MagicMock(spec=Neo4jToolAdapter)
    mock_adapter.search_paths.return_value = [sample_evidence]

    tool = GraphSearchTool(neo4j_adapter=mock_adapter)
    res = tool.run(GraphSearchInput(starting_ticker="ASELS", max_hops=2))

    assert res.success is True
    assert res.record_count == 1
    assert res.data.hits[0].retrieval_method == "graph_traversal"
    assert res.data.hits[0].graph_path is not None


def test_hybrid_search_tool_valid_call(sample_evidence):
    """Test HybridSearchTool combining vector and graph search."""
    vec_adapter = MagicMock(spec=QdrantToolAdapter)
    vec_adapter.search.return_value = [sample_evidence]

    grp_adapter = MagicMock(spec=Neo4jToolAdapter)
    grp_adapter.search_paths.return_value = []

    tool = HybridSearchTool(qdrant_adapter=vec_adapter, neo4j_adapter=grp_adapter)
    res = tool.run(HybridSearchInput(query="ASELSAN ciro", ticker="ASELS", vector_weight=0.6, graph_weight=0.4))

    assert res.success is True
    assert res.record_count == 1


def test_fetch_chunk_tool(sample_evidence):
    """Test FetchChunkTool retrieving single chunk by chunk_id."""
    mock_adapter = MagicMock(spec=QdrantToolAdapter)
    mock_adapter.fetch_chunk_by_id.return_value = sample_evidence

    tool = FetchChunkTool(qdrant_adapter=mock_adapter)
    res = tool.run(FetchChunkInput(chunk_id="chk_asels_001"))

    assert res.success is True
    assert res.data.found is True
    assert res.data.evidence.chunk_id == "chk_asels_001"


def test_fetch_source_context_tool(sample_evidence):
    """Test FetchSourceContextTool returning target chunk and window."""
    mock_adapter = MagicMock(spec=QdrantToolAdapter)
    mock_adapter.fetch_source_context_window.return_value = (sample_evidence, [])

    tool = FetchSourceContextTool(qdrant_adapter=mock_adapter)
    res = tool.run(FetchSourceContextInput(chunk_id="chk_asels_001", window=1))

    assert res.success is True
    assert res.data.target_chunk.chunk_id == "chk_asels_001"
    assert "120 Milyar TL" in res.data.combined_text


def test_inspect_company_tool():
    """Test InspectCompanyTool returning metadata summary."""
    mock_adapter = MagicMock(spec=Neo4jToolAdapter)
    mock_adapter.inspect_company_graph.return_value = {
        "ticker": "ASELS",
        "company_name": "Aselsan Elektronik",
        "available_years": [2023, 2024],
        "total_chunks": 420,
        "graph_node_count": 850,
        "graph_relations": ["PRODUCES", "OPERATES_IN"],
    }

    tool = InspectCompanyTool(neo4j_adapter=mock_adapter)
    res = tool.run(InspectCompanyInput(ticker="ASELS"))

    assert res.success is True
    assert res.data.ticker == "ASELS"
    assert res.data.available_years == [2023, 2024]


def test_inspect_report_tool():
    """Test InspectReportTool returning report structure stats."""
    mock_adapter = MagicMock(spec=Neo4jToolAdapter)
    mock_adapter.inspect_report.return_value = {
        "ticker": "ASELS",
        "year": 2024,
        "report_type": "annual_report",
        "source_file": "ASELS__2024__annual_report__tr.pdf",
        "total_pages": 120,
        "chunk_count": 45,
        "sections_summary": ["Finansal Göstergeler"],
    }

    tool = InspectReportTool(neo4j_adapter=mock_adapter)
    res = tool.run(InspectReportInput(ticker="ASELS", year=2024))

    assert res.success is True
    assert res.data.total_pages == 120


def test_validate_citation_tool_success_and_failure(sample_evidence):
    """Test ValidateCitationTool success when chunk matches evidence pool and failure when missing."""
    tool = ValidateCitationTool()

    # Success case: matching cited_chunk_id
    res_valid = tool.run(
        ValidateCitationInput(
            citation_text="ASELSAN cirosu 120 Milyar TL oldu.",
            claimed_source_number=1,
            cited_chunk_id="chk_asels_001",
            available_sources=[sample_evidence],
        )
    )
    assert res_valid.success is True
    assert res_valid.data.is_valid is True
    assert res_valid.data.citation_status == "verified"
    assert res_valid.data.matched_evidence.chunk_id == "chk_asels_001"

    # Failure case: missing cited_chunk_id
    res_invalid = tool.run(
        ValidateCitationInput(
            citation_text="Sahte iddia",
            claimed_source_number=2,
            cited_chunk_id="chk_nonexistent_999",
            available_sources=[sample_evidence],
        )
    )
    assert res_invalid.success is True
    assert res_invalid.data.is_valid is False
    assert res_invalid.data.citation_status == "rejected"


def test_deterministic_evidence_sorting(sample_evidence):
    """Test deterministic evidence sorting by relevance score desc and chunk_id asc."""
    item1 = sample_evidence.model_copy(update={"chunk_id": "chk_b", "relevance_score": 0.80})
    item2 = sample_evidence.model_copy(update={"chunk_id": "chk_a", "relevance_score": 0.95})
    item3 = sample_evidence.model_copy(update={"chunk_id": "chk_c", "relevance_score": 0.80})

    sorted_list = sort_evidence_deterministically([item1, item2, item3])

    assert sorted_list[0].chunk_id == "chk_a"
    assert sorted_list[1].chunk_id == "chk_b"
    assert sorted_list[2].chunk_id == "chk_c"
