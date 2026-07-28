"""Comprehensive unit and integration tests for Vector Researcher, Graph Researcher, and Evidence Deduplicator."""

from unittest.mock import MagicMock

import pytest

from company_graphrag.agents.researchers import (
    EvidenceDeduplicator,
    GraphResearcherAgent,
    VectorResearcherAgent,
)
from company_graphrag.agents.schema import EvidenceItem, ResearchState, ResearchTaskStep
from company_graphrag.agents.tools.base import ToolResult
from company_graphrag.agents.tools.models import GraphSearchOutput, VectorSearchOutput
from company_graphrag.agents.tools.search_tools import GraphSearchTool, VectorSearchTool


@pytest.fixture
def sample_vector_evidence():
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
        relevance_score=0.92,
    )


@pytest.fixture
def sample_graph_evidence():
    return EvidenceItem(
        company="ASELS",
        ticker="ASELS",
        year=2024,
        report="annual_report",
        chunk_id="chk_graph_001",
        page_number=1,
        source_file="ASELS__2024.pdf",
        retrieval_method="graph_traversal",
        content="ASELSAN -[PRODUCES]-> KORHAN",
        relevance_score=0.88,
        graph_path={"path_id": "p_101", "hops": 2, "nodes": [], "edges": []},
    )


def test_vector_only_research_execution(sample_vector_evidence):
    """Test 1: VectorResearcherAgent executing task step and returning evidence with provenance."""
    mock_tool = MagicMock(spec=VectorSearchTool)
    mock_tool.name = "vector_search"
    mock_tool.run.return_value = ToolResult(
        tool_name="vector_search",
        success=True,
        data=VectorSearchOutput(query="test", hits=[sample_vector_evidence], total_hits=1),
        record_count=1,
    )

    agent = VectorResearcherAgent(vector_search_tool=mock_tool)
    state = ResearchState(user_query="ASELSAN 2024 cirosu ne kadar?")
    step = ResearchTaskStep(
        task_id="task_1",
        question="ASELS 2024 ciro verilerini getir.",
        objective="Retrieve revenue metric for ASELS",
        required_entities={"ticker": "ASELS", "year": 2024},
        retrieval_strategy="vector_search",
        max_tool_calls=2,
    )

    res = agent.execute_task(step, state)

    assert res.status == "COMPLETED"
    assert len(res.evidence) == 1
    assert res.evidence[0].ticker == "ASELS"
    assert res.evidence[0].page_number == 19
    assert len(state.evidence) == 1
    assert len(state.tool_calls) == 1
    assert state.final_answer is None, "Researcher must NEVER write final answer!"


def test_graph_only_research_execution(sample_graph_evidence):
    """Test 2: GraphResearcherAgent executing task step and returning graph path evidence."""
    mock_tool = MagicMock(spec=GraphSearchTool)
    mock_tool.name = "graph_search"
    mock_tool.run.return_value = ToolResult(
        tool_name="graph_search",
        success=True,
        data=GraphSearchOutput(query="test", hits=[sample_graph_evidence], paths_found=1),
        record_count=1,
    )

    agent = GraphResearcherAgent(graph_search_tool=mock_tool)
    state = ResearchState(user_query="ASELSAN ürünleri nelerdir?")
    step = ResearchTaskStep(
        task_id="task_1",
        question="ASELS ürün ilişkilerini getir.",
        objective="Retrieve graph paths for ASELS products",
        required_entities={"ticker": "ASELS"},
        retrieval_strategy="graph_search",
        max_tool_calls=2,
    )

    res = agent.execute_task(step, state)

    assert res.status == "COMPLETED"
    assert len(res.evidence) == 1
    assert res.evidence[0].retrieval_method == "graph_traversal"
    assert res.evidence[0].graph_path["path_id"] == "p_101"
    assert state.final_answer is None, "Researcher must NEVER write final answer!"


def test_hybrid_research_preparation(sample_vector_evidence, sample_graph_evidence):
    """Test 3: Hybrid research evidence merging and deduplication."""
    state = ResearchState(user_query="ASELSAN hibrit sorgu")

    # Add evidence from both researchers
    state.add_evidence(sample_vector_evidence)
    state.add_evidence(sample_graph_evidence)

    deduped = EvidenceDeduplicator.deduplicate(state.evidence)
    assert len(deduped) == 2
    assert deduped[0].relevance_score >= deduped[1].relevance_score


def test_empty_result_query_expansion(sample_vector_evidence):
    """Test 4: VectorResearcher attempting alternative query expansion when primary search yields 0 hits."""
    mock_tool = MagicMock(spec=VectorSearchTool)
    mock_tool.name = "vector_search"

    # First call returns 0 hits, second call (alternative query) returns 1 hit
    res_empty = ToolResult(
        tool_name="vector_search",
        success=True,
        data=VectorSearchOutput(query="empty", hits=[], total_hits=0),
        record_count=0,
    )
    res_success = ToolResult(
        tool_name="vector_search",
        success=True,
        data=VectorSearchOutput(query="alt", hits=[sample_vector_evidence], total_hits=1),
        record_count=1,
    )
    mock_tool.run.side_effect = [res_empty, res_success]

    agent = VectorResearcherAgent(vector_search_tool=mock_tool)
    state = ResearchState(user_query="Nadir arama")
    step = ResearchTaskStep(
        task_id="task_1",
        question="Karmaşık arama metni",
        required_entities={"ticker": "ASELS", "year": 2024},
        max_tool_calls=2,
    )

    res = agent.execute_task(step, state)

    assert mock_tool.run.call_count == 2
    assert res.tool_calls_count == 2
    assert len(res.used_queries) == 2
    assert res.status == "COMPLETED"
    assert len(res.evidence) == 1


def test_duplicate_chunk_deduplication(sample_vector_evidence):
    """Test 5: EvidenceDeduplicator merging duplicate chunk_ids and keeping highest score."""
    dup1 = sample_vector_evidence.model_copy(update={"relevance_score": 0.70})
    dup2 = sample_vector_evidence.model_copy(update={"relevance_score": 0.95})

    deduped = EvidenceDeduplicator.deduplicate([dup1, dup2])
    assert len(deduped) == 1
    assert deduped[0].relevance_score == 0.95


def test_duplicate_graph_path_deduplication(sample_graph_evidence):
    """Test 6: EvidenceDeduplicator merging duplicate graph path_ids."""
    path1 = sample_graph_evidence.model_copy(update={"relevance_score": 0.80})
    path2 = sample_graph_evidence.model_copy(update={"relevance_score": 0.90})

    deduped = EvidenceDeduplicator.deduplicate([path1, path2])
    assert len(deduped) == 1
    assert deduped[0].relevance_score == 0.90


def test_max_tool_calls_limit_enforcement():
    """Test 7: Researcher strictly obeying step.max_tool_calls limit."""
    mock_tool = MagicMock(spec=VectorSearchTool)
    mock_tool.name = "vector_search"
    mock_tool.run.return_value = ToolResult(
        tool_name="vector_search",
        success=True,
        data=VectorSearchOutput(query="q", hits=[], total_hits=0),
        record_count=0,
    )

    agent = VectorResearcherAgent(vector_search_tool=mock_tool)
    state = ResearchState(user_query="Limit testi")
    step = ResearchTaskStep(
        task_id="task_1",
        question="Soru",
        max_tool_calls=1,  # Strictly 1 tool call max
    )

    res = agent.execute_task(step, state)

    assert mock_tool.run.call_count == 1
    assert res.tool_calls_count == 1


def test_backend_error_handling():
    """Test 8: Researcher handling tool backend exceptions gracefully."""
    mock_tool = MagicMock(spec=VectorSearchTool)
    mock_tool.name = "vector_search"
    mock_tool.run.return_value = ToolResult(
        tool_name="vector_search",
        success=False,
        error_message="Backend timeout",
        record_count=0,
    )

    agent = VectorResearcherAgent(vector_search_tool=mock_tool)
    state = ResearchState(user_query="Hata testi")
    step = ResearchTaskStep(task_id="task_1", question="Soru", max_tool_calls=1)

    res = agent.execute_task(step, state)

    assert res.status == "NO_RESULTS"
    assert res.failed_attempts == 1
    assert len(res.evidence) == 0
