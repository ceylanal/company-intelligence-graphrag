"""Comprehensive unit and integration tests for ReportWriterAgent, CitationCompletenessChecker, and ReportOutput."""

import pytest

from company_graphrag.agents.schema import (
    Contradiction,
    EvidenceItem,
    ResearchPlan,
    ResearchState,
    VerifiedClaim,
)
from company_graphrag.agents.writer import CitationCompletenessChecker, ReportWriterAgent


@pytest.fixture
def sample_evidence():
    return EvidenceItem(
        company="Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
        ticker="ASELS",
        year=2024,
        report="annual_report",
        chunk_id="chk_asels_001",
        page_number=19,
        source_file="ASELS__2024__annual_report__tr.pdf",
        retrieval_method="vector_search",
        content="ASELSAN'ın 2024 yılı cirosu 120 Milyar TL olarak gerçekleşmiştir.",
        text="ASELSAN'ın 2024 yılı cirosu 120 Milyar TL olarak gerçekleşmiştir.",
        relevance_score=0.95,
    )


@pytest.fixture
def sample_verified_claim():
    return VerifiedClaim(
        claim_text="ASELSAN 2024 yılı cirosu 120 Milyar TL olarak gerçekleşmiştir.",
        supporting_evidence_ids=["chk_asels_001"],
        company="ASELS",
        year=2024,
        metric="ciro",
        value="120 Milyar",
        unit="TL",
        verification_status="verified",
    )


def test_single_metric_report(sample_evidence, sample_verified_claim):
    """Test 1: Single metric report generation with citations and evidence appendix."""
    writer = ReportWriterAgent()
    state = ResearchState(user_query="ASELSAN 2024 cirosu ne kadar?")
    state.add_evidence(sample_evidence)
    state.verified_claims.append(sample_verified_claim)

    output = writer.generate_report(state)

    assert output.answer is not None
    assert "[Source 1]" in output.answer
    assert "ASELS" in output.answer
    assert "120 Milyar TL" in output.answer
    assert len(output.citations) == 1
    assert output.citations[0].chunk_id == "chk_asels_001"
    assert output.citations[0].page_number == 19
    assert len(output.evidence_appendix) == 1
    assert state.final_answer == output.answer


def test_two_company_comparison_report(sample_evidence, sample_verified_claim):
    """Test 2: Two-company comparison report with comparison section."""
    thy_ev = EvidenceItem(
        company="Türk Hava Yolları A.O.",
        ticker="THYAO",
        year=2024,
        chunk_id="chk_thy_001",
        page_number=12,
        source_file="THYAO__2024__annual_report__tr.pdf",
        retrieval_method="vector_search",
        content="THY 2024 yılı cirosu 500 Milyar TL olarak gerçekleşmiştir.",
    )
    thy_claim = VerifiedClaim(
        claim_text="THY 2024 yılı cirosu 500 Milyar TL.",
        supporting_evidence_ids=["chk_thy_001"],
        company="THYAO",
        year=2024,
        metric="ciro",
        value="500 Milyar",
        unit="TL",
        verification_status="verified",
    )

    writer = ReportWriterAgent()
    plan = ResearchPlan(
        user_query="ASELSAN ve THY 2024 cirosunu karşılaştır",
        normalized_query="aselsan ve thy 2024 cirosunu karşılaştır",
        is_comparison=True,
    )
    state = ResearchState(
        user_query="ASELSAN ve THY 2024 cirosunu karşılaştır",
        structured_plan=plan,
    )
    state.add_evidence(sample_evidence)
    state.add_evidence(thy_ev)
    state.verified_claims.extend([sample_verified_claim, thy_claim])

    output = writer.generate_report(state)

    assert output.comparison is not None
    assert "Şirket Karşılaştırma Özeti" in output.answer
    assert "THYAO" in output.answer
    assert len(output.citations) == 2


def test_multi_year_comparison_report(sample_evidence, sample_verified_claim):
    """Test 3: Multi-year comparison report."""
    ev_2023 = EvidenceItem(
        company="Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
        ticker="ASELS",
        year=2023,
        chunk_id="chk_asels_2023",
        page_number=15,
        source_file="ASELS__2023__annual_report__tr.pdf",
        retrieval_method="vector_search",
        content="ASELSAN 2023 cirosu 106 Milyar TL.",
    )
    claim_2023 = VerifiedClaim(
        claim_text="ASELSAN 2023 cirosu 106 Milyar TL.",
        supporting_evidence_ids=["chk_asels_2023"],
        company="ASELS",
        year=2023,
        metric="ciro",
        value="106 Milyar",
        unit="TL",
        verification_status="verified",
    )

    writer = ReportWriterAgent()
    state = ResearchState(user_query="ASELSAN 2023 ve 2024 cirosu")
    state.add_evidence(ev_2023)
    state.add_evidence(sample_evidence)
    state.verified_claims.extend([claim_2023, sample_verified_claim])

    output = writer.generate_report(state)

    assert "ASELS" in output.answer
    assert "106 Milyar" in output.answer
    assert "120 Milyar" in output.answer


def test_multi_hop_research_answer(sample_evidence):
    """Test 4: Multi-hop research answer formatting with graph path info in evidence appendix."""
    grp_ev = EvidenceItem(
        company="ASELS",
        ticker="ASELS",
        year=2024,
        chunk_id="chk_grp_01",
        page_number=5,
        source_file="ASELS__2024.pdf",
        retrieval_method="graph_traversal",
        content="ASELSAN -[PRODUCES]-> KORHAN Savunma Sistemi",
        graph_path={"path_id": "p1", "hops": 2},
    )
    grp_claim = VerifiedClaim(
        claim_text="ASELSAN KORHAN Savunma Sistemi üretmektedir.",
        supporting_evidence_ids=["chk_grp_01"],
        company="ASELS",
        year=2024,
        verification_status="verified",
    )

    writer = ReportWriterAgent()
    state = ResearchState(user_query="ASELSAN ürün ilişkileri")
    state.add_evidence(grp_ev)
    state.verified_claims.append(grp_claim)

    output = writer.generate_report(state)

    assert "KORHAN" in output.answer
    assert "graph_traversal" in output.answer


def test_partially_verified_claim_inclusion(sample_evidence):
    """Test 5: Report inclusion of partially_verified claims."""
    writer = ReportWriterAgent()
    state = ResearchState(user_query="Kısmen doğrulanmış iddia")
    state.add_evidence(sample_evidence)

    part_claim = VerifiedClaim(
        claim_text="ASELSAN 2024 yılında büyüme kaydetti.",
        supporting_evidence_ids=["chk_asels_001"],
        company="ASELS",
        year=2024,
        verification_status="partially_verified",
    )
    state.verified_claims.append(part_claim)

    output = writer.generate_report(state)
    assert "büyüme kaydetti" in output.answer


def test_contradictory_evidence_formatting(sample_evidence, sample_verified_claim):
    """Test 6: Report explicitly formatting state.contradictions section."""
    writer = ReportWriterAgent()
    state = ResearchState(user_query="Çelişkili rapor")
    state.add_evidence(sample_evidence)
    state.verified_claims.append(sample_verified_claim)
    state.contradictions.append(
        Contradiction(
            description="2024 cirosu 120 Milyar TL vs 90 Milyar TL olarak çelişmektedir.",
            conflicting_evidence_ids=["chk_asels_001", "chk_asels_002"],
        )
    )

    output = writer.generate_report(state)

    assert "Çelişkili Bilgiler" in output.answer
    assert len(output.contradictions) == 1
    assert "120 Milyar TL vs 90 Milyar TL" in output.answer


def test_citation_completeness_checker():
    """Test 7: CitationCompletenessChecker flagging uncited numerical statements."""
    checker = CitationCompletenessChecker()

    text_with_uncited_number = (
        "ASELSAN 2024 yılında cirosunu %13 artırarak 120 Milyar TL olarak gerçekleştirdi.\n"
        "Şirket büyümeye devam etmektedir. [Source 1]"
    )

    warnings = checker.check_completeness(text_with_uncited_number)
    assert len(warnings) >= 1
    assert "uncited numerical" in warnings[0]


def test_zero_sufficient_evidence_handling():
    """Test 8: Returning polite insufficient context notice when 0 evidence exists."""
    writer = ReportWriterAgent()
    state = ResearchState(user_query="Bilinmeyen şirket 2024 karı")

    output = writer.generate_report(state)

    assert "Yetersiz Kanıt Uyarısı" in output.answer
    assert output.executive_summary is not None
    assert len(output.citations) == 0


def test_unnecessary_duplicate_citation_deduplication(sample_evidence, sample_verified_claim):
    """Test 9: Deduplicating active citations so unused sources are not listed."""
    unused_ev = EvidenceItem(
        company="Akbank T.A.Ş.",
        ticker="AKBNK",
        year=2024,
        chunk_id="chk_akbnk_unused",
        page_number=99,
        source_file="AKBNK__2024.pdf",
        retrieval_method="vector_search",
        content="Unused text",
    )

    writer = ReportWriterAgent()
    state = ResearchState(user_query="Tekil citation testi")
    state.add_evidence(sample_evidence)
    state.add_evidence(unused_ev)  # Not referenced in any verified claim
    state.verified_claims.append(sample_verified_claim)

    output = writer.generate_report(state)

    assert len(output.citations) == 1
    assert output.citations[0].chunk_id == "chk_asels_001"
    # Unused evidence should NOT be listed in active citations
    assert "chk_akbnk_unused" not in [c.chunk_id for c in output.citations]


def test_writer_executes_zero_db_calls(sample_evidence, sample_verified_claim):
    """Test 10: Verifying ReportWriterAgent makes 0 tool calls or DB queries."""
    writer = ReportWriterAgent()
    state = ResearchState(user_query="Zero DB call test")
    state.add_evidence(sample_evidence)
    state.verified_claims.append(sample_verified_claim)

    initial_search_calls = state.execution_budget.search_calls_count
    writer.generate_report(state)

    assert state.execution_budget.search_calls_count == initial_search_calls, "ReportWriter MUST make 0 DB search calls!"
