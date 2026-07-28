"""Unit tests for Multi-Agent Shared State, Evidence Provenance, and Agent Contracts."""

import pytest
from pydantic import ValidationError

from company_graphrag.agents.contracts import (
    AGENT_CONTRACTS,
    AgentRole,
    GraphResearcherInput,
    PlannerInput,
    ReportWriterInput,
    SupervisorInput,
    VectorResearcherInput,
    VerifierInput,
)
from company_graphrag.agents.schema import (
    AgentWorkflowStatus,
    CitationItem,
    Contradiction,
    EvidenceItem,
    ExecutionBudget,
    RejectedClaim,
    ResearchState,
    SubQuestion,
    ToolCallRecord,
    VerifiedClaim,
)


def test_research_state_initialization():
    """Test default initialization of ResearchState."""
    state = ResearchState(user_query="ASELSAN 2024 cirosu ne kadar?")
    assert state.user_query == "ASELSAN 2024 cirosu ne kadar?"
    assert state.run_id.startswith("run_")
    assert state.status == AgentWorkflowStatus.PENDING
    assert state.execution_budget.current_step == 0
    assert state.execution_budget.max_steps == 15
    assert len(state.evidence) == 0
    assert len(state.verified_claims) == 0
    assert len(state.tool_calls) == 0


def test_evidence_item_provenance_validation_valid():
    """Test valid EvidenceItem with complete provenance metadata."""
    item = EvidenceItem(
        company="Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
        ticker="ASELS",
        year=2024,
        report="annual_report",
        chunk_id="chk_12345",
        page_number=19,
        source_file="ASELS__2024__annual_report__tr.pdf",
        retrieval_method="vector_search",
        content="ASELSAN 2024 yılı cirosu 120 Milyar TL olarak gerçekleşmiştir.",
        relevance_score=0.92,
    )
    assert item.ticker == "ASELS"
    assert item.year == 2024
    assert item.page_number == 19
    assert item.retrieval_method == "vector_search"


def test_evidence_item_provenance_validation_missing_fields():
    """Test EvidenceItem validation failure when mandatory provenance fields are missing."""
    with pytest.raises(ValidationError) as exc_info:
        EvidenceItem(
            company="",
            ticker="  ",
            year=2024,
            chunk_id="",
            page_number=1,
            source_file="file.pdf",
            retrieval_method="vector_search",
            content="test",
        )
    assert "mandatory provenance fields" in str(exc_info.value)


def test_execution_budget_step_increment_and_exhaustion():
    """Test ExecutionBudget step increment and exhaustion detection."""
    budget = ExecutionBudget(max_steps=3, max_search_calls=2)

    assert not budget.is_exhausted()

    budget.increment_step()
    budget.increment_step()
    assert not budget.is_exhausted()

    budget.increment_step()
    assert budget.current_step == 3
    assert budget.is_exhausted()


def test_execution_budget_search_calls_exhaustion():
    """Test ExecutionBudget exhaustion triggered by search calls limit."""
    budget = ExecutionBudget(max_steps=10, max_search_calls=2)
    budget.record_search_call()
    assert not budget.is_exhausted()

    budget.record_search_call()
    assert budget.search_calls_count == 2
    assert budget.is_exhausted()


def test_research_state_retry_tracking():
    """Test retry recording and maximum retry limit enforcement per agent role."""
    state = ResearchState(user_query="Test query")
    role_name = AgentRole.VECTOR_RESEARCHER.value

    assert not state.is_retry_exceeded(role_name)

    state.record_retry(role_name)
    state.record_retry(role_name)
    assert state.retry_count[role_name] == 2
    assert not state.is_retry_exceeded(role_name)

    state.record_retry(role_name)
    assert state.retry_count[role_name] == 3
    assert state.is_retry_exceeded(role_name)


def test_research_state_evidence_and_claim_tracking():
    """Test adding evidence, claims, contradictions, and citations to ResearchState."""
    state = ResearchState(user_query="THYAO 2024 filosu kaç uçak?")

    evidence = EvidenceItem(
        company="Türk Hava Yolları A.O.",
        ticker="THYAO",
        year=2024,
        chunk_id="chk_thyao_01",
        page_number=5,
        source_file="THYAO__2024__annual_report__tr.pdf",
        retrieval_method="graph_traversal",
        content="THY 2024 yıl sonunda 470 uçaklık filoya ulaşmıştır.",
    )
    state.add_evidence(evidence)
    assert len(state.evidence) == 1

    verified = VerifiedClaim(
        claim_text="THY 2024 filosu 470 uçaktır.",
        supporting_evidence_ids=[evidence.evidence_id],
        verification_confidence=0.98,
    )
    state.verified_claims.append(verified)

    rejected = RejectedClaim(
        claim_text="THY filosu 600 uçaktır.",
        reason="Ungrounded statement without source chunk",
    )
    state.rejected_claims.append(rejected)

    contradiction = Contradiction(
        description="Farklı rapor sayfalarında filo sayısı 470 vs 465 olarak belirtilmiş.",
        conflicting_evidence_ids=[evidence.evidence_id],
    )
    state.contradictions.append(contradiction)

    citation = CitationItem(
        citation_index=1,
        chunk_id=evidence.chunk_id,
        company=evidence.company,
        ticker=evidence.ticker,
        year=evidence.year,
        source_file=evidence.source_file,
        page_number=evidence.page_number,
        retrieval_method=evidence.retrieval_method,
        snippet=evidence.content,
    )
    state.citations.append(citation)

    assert len(state.verified_claims) == 1
    assert len(state.rejected_claims) == 1
    assert len(state.contradictions) == 1
    assert len(state.citations) == 1


def test_tool_call_record_audit_log():
    """Test ToolCallRecord logging in state."""
    state = ResearchState(user_query="Test query")
    record = ToolCallRecord(
        agent_role=AgentRole.VECTOR_RESEARCHER.value,
        tool_name="vector_search_tool",
        input_params={"query": "ASELSAN ciro", "top_k": 5},
        output_summary="Retrieved 5 hits",
        execution_time_ms=12.4,
        success=True,
    )
    state.tool_calls.append(record)
    assert len(state.tool_calls) == 1
    assert state.tool_calls[0].tool_name == "vector_search_tool"


def test_agent_contracts_registry():
    """Test AGENT_CONTRACTS covers all 6 agent roles with strict rules."""
    assert len(AGENT_CONTRACTS) == 6

    for role in AgentRole:
        contract = AGENT_CONTRACTS[role]
        assert contract.role == role
        assert len(contract.description) > 0
        assert len(contract.allowed_tools) > 0
        assert len(contract.forbidden_actions) > 0
        assert len(contract.success_criteria) > 0
        assert len(contract.termination_criteria) > 0
        assert len(contract.error_behavior) > 0


def test_agent_payload_contracts():
    """Test agent input contract models."""
    sup_in = SupervisorInput(user_query="Test")
    assert sup_in.max_steps == 15

    plan_in = PlannerInput(user_query="Test query")
    assert plan_in.user_query == "Test query"

    sq = SubQuestion(question="Ciro?", target_agent=AgentRole.VECTOR_RESEARCHER.value)
    vec_in = VectorResearcherInput(subquestion=sq)
    assert vec_in.candidate_k == 20

    grp_in = GraphResearcherInput(subquestion=sq)
    assert grp_in.max_hops == 2

    ver_in = VerifierInput(user_query="Test", evidence=[])
    assert len(ver_in.evidence) == 0

    rw_in = ReportWriterInput(user_query="Test")
    assert len(rw_in.verified_claims) == 0
