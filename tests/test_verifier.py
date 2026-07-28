"""Comprehensive unit and integration tests for EvidenceVerifierAgent, VerifiedClaim, and Contradiction detection."""

import pytest

from company_graphrag.agents.schema import EvidenceItem, ResearchState, VerifiedClaim
from company_graphrag.agents.verifier import EvidenceVerifierAgent


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
        content="ASELSAN'ın 2024 yılı cirosu %13 artarak 120 Milyar TL olarak gerçekleşmiştir.",
        text="ASELSAN'ın 2024 yılı cirosu %13 artarak 120 Milyar TL olarak gerçekleşmiştir.",
        relevance_score=0.95,
    )


def test_fully_supported_claim(sample_evidence):
    """Test 1: Fully supported claim matching company, year, value, unit, and chunk_id -> verified."""
    verifier = EvidenceVerifierAgent()

    claim = VerifiedClaim(
        claim_text="ASELSAN 2024 yılı cirosu 120 Milyar TL olarak gerçekleşmiştir.",
        supporting_evidence_ids=["chk_asels_001"],
        company="ASELS",
        year=2024,
        metric="ciro",
        value="120 Milyar",
        unit="TL",
    )

    audited = verifier.verify_claim(claim, [sample_evidence])

    assert audited.verification_status == "verified"
    assert audited.confidence >= 0.90
    assert len(audited.warnings) == 0


def test_partially_supported_claim(sample_evidence):
    """Test 2: Partially supported claim with text overlap -> partially_verified."""
    verifier = EvidenceVerifierAgent()

    claim = VerifiedClaim(
        claim_text="ASELSAN 2024 yılında ciro artışı sağladı.",
        supporting_evidence_ids=["chk_asels_001"],
        company="ASELS",
        year=2024,
    )

    audited = verifier.verify_claim(claim, [sample_evidence])

    assert audited.verification_status in ["verified", "partially_verified"]
    assert audited.confidence >= 0.70


def test_wrong_year_claim(sample_evidence):
    """Test 3: Claim specifying year 2023 when evidence is 2024 -> unsupported."""
    verifier = EvidenceVerifierAgent()

    claim = VerifiedClaim(
        claim_text="ASELSAN 2023 yılı cirosu 120 Milyar TL.",
        supporting_evidence_ids=["chk_asels_001"],
        company="ASELS",
        year=2023,  # Wrong year
        value="120 Milyar",
    )

    audited = verifier.verify_claim(claim, [sample_evidence])

    assert audited.verification_status == "unsupported"
    assert audited.confidence == 0.0
    assert any("Year mismatch" in w for w in audited.warnings)


def test_wrong_company_claim(sample_evidence):
    """Test 4: Claim specifying THYAO when evidence is from ASELS -> unsupported."""
    verifier = EvidenceVerifierAgent()

    claim = VerifiedClaim(
        claim_text="THY 2024 yılı cirosu 120 Milyar TL.",
        supporting_evidence_ids=["chk_asels_001"],
        company="THYAO",  # Wrong company
        year=2024,
    )

    audited = verifier.verify_claim(claim, [sample_evidence])

    assert audited.verification_status == "unsupported"
    assert audited.confidence == 0.0
    assert any("Company mismatch" in w for w in audited.warnings)


def test_wrong_financial_value_claim(sample_evidence):
    """Test 5: Claim specifying wrong value 500 Milyar when evidence has 120 Milyar -> unsupported."""
    verifier = EvidenceVerifierAgent()

    claim = VerifiedClaim(
        claim_text="ASELSAN 2024 yılı cirosu 500 Milyar TL.",
        supporting_evidence_ids=["chk_asels_001"],
        company="ASELS",
        year=2024,
        value="500 Milyar",  # Wrong value
    )

    audited = verifier.verify_claim(claim, [sample_evidence])

    assert audited.verification_status == "unsupported"
    assert audited.confidence == 0.0
    assert any("value mismatch" in w for w in audited.warnings)


def test_wrong_unit_claim(sample_evidence):
    """Test 6: Claim specifying Dolar when evidence has TL -> unsupported."""
    verifier = EvidenceVerifierAgent()

    claim = VerifiedClaim(
        claim_text="ASELSAN 2024 yılı cirosu 120 Dolar.",
        supporting_evidence_ids=["chk_asels_001"],
        company="ASELS",
        year=2024,
        value="120",
        unit="Dolar",  # Wrong unit
    )

    audited = verifier.verify_claim(claim, [sample_evidence])

    assert audited.verification_status == "unsupported"
    assert audited.confidence == 0.0
    assert any("Unit mismatch" in w for w in audited.warnings)


def test_invalid_chunk_id(sample_evidence):
    """Test 7: Claim referencing a non-existent chunk_id -> unsupported."""
    verifier = EvidenceVerifierAgent()

    claim = VerifiedClaim(
        claim_text="ASELSAN 2024 cirosu.",
        supporting_evidence_ids=["chk_nonexistent_999"],  # Non-existent chunk ID
        company="ASELS",
        year=2024,
    )

    audited = verifier.verify_claim(claim, [sample_evidence])

    assert audited.verification_status == "unsupported"
    assert audited.confidence == 0.0
    assert any("do not exist" in w for w in audited.warnings)


def test_contradiction_between_sources(sample_evidence):
    """Test 8: Two conflicting evidence sources for same company & year -> contradicted, recorded in state."""
    conflicting_ev = EvidenceItem(
        company="Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
        ticker="ASELS",
        year=2024,
        report="annual_report",
        chunk_id="chk_asels_002",
        page_number=45,
        source_file="ASELS__2024__audit.pdf",
        retrieval_method="vector_search",
        content="ASELSAN 2024 yılı cirosu 90 Milyar TL olarak açıklanmıştır.",  # Conflicting value
        relevance_score=0.90,
    )

    verifier = EvidenceVerifierAgent()
    state = ResearchState(user_query="ASELSAN ciro çelişki testi")
    state.add_evidence(sample_evidence)
    state.add_evidence(conflicting_ev)

    claim = VerifiedClaim(
        claim_text="ASELSAN 2024 yılı cirosu 120 Milyar TL.",
        supporting_evidence_ids=["chk_asels_001"],
        company="ASELS",
        year=2024,
        value="120 Milyar",
    )
    state.verified_claims.append(claim)

    summary = verifier.verify_research_state(state)

    assert summary["contradicted_count"] == 1
    assert len(state.contradictions) == 1
    assert "chk_asels_001" in state.contradictions[0].conflicting_evidence_ids
    assert "chk_asels_002" in state.contradictions[0].conflicting_evidence_ids


def test_insufficient_evidence_and_followup_request(sample_evidence):
    """Test 9: Unsupported claim requesting targeted follow-up research topic."""
    verifier = EvidenceVerifierAgent()
    state = ResearchState(user_query="Takip testi")
    state.add_evidence(sample_evidence)

    # Claim with non-existent chunk ID
    unsupported_claim = VerifiedClaim(
        claim_text="ASELSAN 2024 Ar-Ge harcaması 15 Milyar TL.",
        supporting_evidence_ids=["chk_missing_009"],
        company="ASELS",
        year=2024,
    )
    state.verified_claims.append(unsupported_claim)

    summary = verifier.verify_research_state(state)

    assert summary["unsupported_count"] == 1
    assert len(state.rejected_claims) == 1
    assert any("Requested targeted follow-up" in w for w in state.warnings)


def test_max_verification_cycles_capping(sample_evidence):
    """Test 10: Verifier stopping follow-up requests when max_verification_cycles limit is reached."""
    verifier = EvidenceVerifierAgent(max_verification_cycles=2)
    state = ResearchState(user_query="Döngü sınırı testi")
    state.add_evidence(sample_evidence)

    unsupported_claim = VerifiedClaim(
        claim_text="ASELSAN sahte iddia",
        supporting_evidence_ids=["chk_missing_009"],
    )

    # Simulate 3 cycles
    state.verified_claims.append(unsupported_claim)
    verifier.verify_research_state(state)

    state.verified_claims.append(unsupported_claim)
    verifier.verify_research_state(state)

    state.verified_claims.append(unsupported_claim)
    summary3 = verifier.verify_research_state(state)

    assert summary3["cycle"] == 3
    # Follow up requests should be stopped on cycle 3 (> max_verification_cycles=2)
    assert not any(c.required_follow_up for c in state.verified_claims)


def test_verifier_never_generates_final_answer(sample_evidence):
    """Test 11: Verification execution leaves state.final_answer strictly None."""
    verifier = EvidenceVerifierAgent()
    state = ResearchState(user_query="Cevap yazmama testi")
    state.add_evidence(sample_evidence)

    verifier.verify_research_state(state)

    assert state.final_answer is None, "Verifier MUST NEVER write final answer!"
