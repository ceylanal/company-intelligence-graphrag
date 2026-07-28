"""Evidence Verifier and Critic Agent for Company Intelligence Multi-Agent System."""

import re
from typing import Any

from company_graphrag.agents.contracts import AgentRole
from company_graphrag.agents.schema import (
    Contradiction,
    EvidenceItem,
    RejectedClaim,
    ResearchState,
    VerifiedClaim,
)
from company_graphrag.agents.tools.citation_tool import ValidateCitationTool
from company_graphrag.agents.tools.models import ValidateCitationInput


class EvidenceVerifierAgent:
    """Evidence Verifier and Critic Agent auditing claims against evidence provenance."""

    role = AgentRole.EVIDENCE_VERIFIER

    def __init__(
        self,
        citation_tool: ValidateCitationTool | None = None,
        max_verification_cycles: int = 2,
    ):
        self._citation_tool = citation_tool or ValidateCitationTool()
        self.max_verification_cycles = max_verification_cycles

    def verify_claim(self, claim: VerifiedClaim, available_evidence: list[EvidenceItem]) -> VerifiedClaim:
        """Audit a single claim against available evidence items."""
        # 1. Check if supporting evidence IDs are provided and exist in evidence pool
        if not claim.supporting_evidence_ids:
            claim.verification_status = "unsupported"
            claim.confidence = 0.0
            claim.warnings.append("No supporting evidence chunk IDs provided for claim.")
            return claim

        evidence_map = {ev.chunk_id: ev for ev in available_evidence}

        # Check for invalid chunk IDs
        valid_supporting_ev = []
        for ev_id in claim.supporting_evidence_ids:
            if ev_id in evidence_map:
                valid_supporting_ev.append(evidence_map[ev_id])

        if not valid_supporting_ev:
            claim.verification_status = "unsupported"
            claim.confidence = 0.0
            claim.warnings.append("Supporting chunk IDs do not exist in the gathered evidence pool.")
            return claim

        ev = valid_supporting_ev[0]

        # 2. Company / Ticker Match
        if claim.company and claim.company.strip():
            claim_c_norm = claim.company.strip().upper()
            ev_c_norm = ev.company.strip().upper()
            ev_t_norm = ev.ticker.strip().upper()
            if claim_c_norm not in ev_c_norm and claim_c_norm not in ev_t_norm and ev_t_norm not in claim_c_norm:
                claim.verification_status = "unsupported"
                claim.confidence = 0.0
                claim.warnings.append(f"Company mismatch: claim specifies '{claim.company}', but evidence is from '{ev.ticker} ({ev.company})'.")
                return claim

        # 3. Year Match
        if claim.year and ev.year and claim.year != ev.year:
            claim.verification_status = "unsupported"
            claim.confidence = 0.0
            claim.warnings.append(f"Year mismatch: claim specifies year {claim.year}, but evidence is from year {ev.year}.")
            return claim

        # 4. Numerical Value Match in Source Content
        if claim.value is not None:
            val_str = str(claim.value).strip().lower()
            content_lower = ev.content.lower()
            if val_str not in content_lower:
                claim.verification_status = "unsupported"
                claim.confidence = 0.0
                claim.warnings.append(f"Financial value mismatch: claim value '{claim.value}' not found in source chunk content.")
                return claim

        # 5. Unit Match (if specified)
        if claim.unit is not None and claim.unit.strip():
            unit_str = claim.unit.strip().lower()
            content_lower = ev.content.lower()
            if unit_str not in content_lower:
                claim.verification_status = "unsupported"
                claim.confidence = 0.0
                claim.warnings.append(f"Unit mismatch: claim unit '{claim.unit}' not found in source text.")
                return claim

        # 6. Check for Contradicting Evidence in the Pool
        contradicting_ev = []
        for other_ev in available_evidence:
            if other_ev.chunk_id == ev.chunk_id:
                continue
            # Same company and year, but conflicting content/values
            if (
                claim.company
                and claim.company.strip().upper() in other_ev.ticker.strip().upper()
                and claim.year == other_ev.year
            ):
                if claim.value is not None and str(claim.value) not in other_ev.content:
                    # Potential discrepancy
                    if re.search(r"\b\d+(\.\d+)?\b", other_ev.content):
                        contradicting_ev.append(other_ev)

        if contradicting_ev:
            claim.verification_status = "contradicted"
            claim.confidence = 0.4
            claim.contradicting_evidence_ids = [c_ev.chunk_id for c_ev in contradicting_ev]
            claim.warnings.append(f"Contradiction detected across sources: Chunk {ev.chunk_id} conflicts with Chunk(s) {claim.contradicting_evidence_ids}.")
            return claim

        # 7. Grounding via Citation Validator
        cit_res = self._citation_tool.run(
            ValidateCitationInput(
                citation_text=claim.claim_text,
                claimed_source_number=1,
                cited_chunk_id=ev.chunk_id,
                available_sources=available_evidence,
            )
        )

        if cit_res.success and cit_res.data and cit_res.data.is_valid:
            claim.verification_status = "verified"
            claim.confidence = 0.95
        else:
            claim.verification_status = "partially_verified"
            claim.confidence = 0.70
            claim.warnings.append("Partial text overlap validation.")

        return claim

    def verify_research_state(self, state: ResearchState) -> dict[str, Any]:
        """Audit all evidence items and claims in ResearchState."""
        current_cycle = state.record_retry(self.role.value)

        verified_count = 0
        unsupported_count = 0
        contradicted_count = 0

        # Build candidate claims from evidence if verified_claims is empty
        candidate_claims = list(state.verified_claims)
        if not candidate_claims and state.evidence:
            for ev in state.evidence:
                candidate_claims.append(
                    VerifiedClaim(
                        claim_text=ev.content,
                        supporting_evidence_ids=[ev.chunk_id],
                        company=ev.ticker,
                        year=ev.year,
                        verification_status="unverified",
                    )
                )

        state.verified_claims.clear()

        for raw_claim in candidate_claims:
            audited_claim = self.verify_claim(raw_claim, state.evidence)

            if audited_claim.verification_status == "verified":
                verified_count += 1
                state.verified_claims.append(audited_claim)
            elif audited_claim.verification_status == "partially_verified":
                verified_count += 1
                state.verified_claims.append(audited_claim)
            elif audited_claim.verification_status == "contradicted":
                contradicted_count += 1
                state.verified_claims.append(audited_claim)
                # Record contradiction without taking sides
                state.contradictions.append(
                    Contradiction(
                        description=f"Contradiction for claim '{audited_claim.claim_text[:60]}...': {', '.join(audited_claim.warnings)}",
                        conflicting_evidence_ids=audited_claim.supporting_evidence_ids + audited_claim.contradicting_evidence_ids,
                        severity="high",
                    )
                )
            else:  # unsupported or ambiguous
                unsupported_count += 1
                state.rejected_claims.append(
                    RejectedClaim(
                        claim_text=audited_claim.claim_text,
                        reason="; ".join(audited_claim.warnings) or "Ungrounded claim without supporting evidence",
                        contradicting_evidence_ids=audited_claim.contradicting_evidence_ids,
                    )
                )

                # Request targeted follow-up if verification cycle permits
                if current_cycle <= self.max_verification_cycles:
                    audited_claim.required_follow_up = f"Targeted search to verify: {audited_claim.claim_text[:50]}"
                    state.warnings.append(f"Verifier: Requested targeted follow-up for unsupported claim '{audited_claim.claim_id}'.")

        return {
            "verified_count": verified_count,
            "unsupported_count": unsupported_count,
            "contradicted_count": contradicted_count,
            "cycle": current_cycle,
        }
