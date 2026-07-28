"""Citation-First Report Writer Agent for Company Intelligence Multi-Agent System."""

import re
from typing import Any

from company_graphrag.agents.contracts import AgentRole
from company_graphrag.agents.schema import (
    CitationItem,
    ReportOutput,
    ResearchState,
)

NUMERICAL_CLAIM_REGEX = re.compile(
    r"\b\d+([.,]\d+)?\b|\b%\d+|\b\d+%\b|\bTL\b|\bMilyar\b|\bMilyon\b|\bDolar\b|\bUSD\b",
    re.IGNORECASE,
)
CITATION_TAG_REGEX = re.compile(r"\[(Source\s*\d+|\d+)\]", re.IGNORECASE)


class CitationCompletenessChecker:
    """Audits generated report text to ensure all numerical/financial claims possess citations."""

    @staticmethod
    def check_completeness(text: str) -> list[str]:
        """Scan body text sentences containing numerical facts and flag uncited statements."""
        warnings: list[str] = []
        sentences = [s.strip() for s in re.split(r"[.\n]+", text) if s.strip()]

        for sent in sentences:
            # Skip Markdown headers, evidence appendix items, and section titles
            if sent.startswith("#") or sent.startswith("**[Source") or sent.startswith("- Dosya:") or sent.startswith("- Alıntı:"):
                continue
            if NUMERICAL_CLAIM_REGEX.search(sent):
                if not CITATION_TAG_REGEX.search(sent):
                    warnings.append(
                        f"Citation Completeness Warning: Sentence contains uncited numerical or financial claim: '{sent[:80]}...'"
                    )
        return warnings


class ReportWriterAgent:
    """Citation-First Report Writer Agent synthesizing verified claims into grounded Markdown reports."""

    role = AgentRole.REPORT_WRITER

    def __init__(self, checker: CitationCompletenessChecker | None = None):
        self._checker = checker or CitationCompletenessChecker()

    def generate_report(self, state: ResearchState) -> ReportOutput:
        """Synthesize verified claims and evidence into a structured ReportOutput."""
        user_query = state.user_query
        verified_claims = [c for c in state.verified_claims if c.verification_status in ["verified", "partially_verified", "contradicted"]]
        evidence_pool = {ev.chunk_id: ev for ev in state.evidence}

        # 1. Handle 0 verified claims / insufficient evidence case
        if not verified_claims and not state.evidence:
            output = ReportOutput(
                answer=(
                    "### ⚠️ Yetersiz Kanıt Uyarısı\n\n"
                    f"Aranan sorgu: **'{user_query}'** için sistemde doğrulanmış herhangi bir kaynak veya iddia bulunamamıştır.\n"
                    "Lütfen sorgunuzu kontrol ediniz veya BIST şirketleri (örn. ASELS, THYAO) hakkındaki mevcut rapor dönemlerini belirtiniz."
                ),
                executive_summary="Aranan konu hakkında doğrulanmış bilgi bulunamamıştır.",
                findings=[],
                uncertainties=[f"'{user_query}' için herhangi bir doğrulanmış kaynak chunk bulunamadı."],
                unanswered_questions=[user_query],
                quality_warnings=["Zero verified claims or evidence items present in ResearchState."],
            )
            state.final_answer = output.answer
            state.structured_report = output
            return output

        # 2. Build Citation Mapping & Deduplicate Citations
        active_citations: list[CitationItem] = []
        chunk_to_citation_idx: dict[str, int] = {}

        citation_counter = 1
        for claim in verified_claims:
            for ev_id in claim.supporting_evidence_ids:
                if ev_id in evidence_pool and ev_id not in chunk_to_citation_idx:
                    ev = evidence_pool[ev_id]
                    citation_item = CitationItem(
                        citation_index=citation_counter,
                        chunk_id=ev.chunk_id,
                        company=ev.company,
                        ticker=ev.ticker,
                        year=ev.year,
                        source_file=ev.source_file,
                        page_number=ev.page_number,
                        retrieval_method=ev.retrieval_method,
                        snippet=ev.content[:200],
                    )
                    active_citations.append(citation_item)
                    chunk_to_citation_idx[ev_id] = citation_counter
                    citation_counter += 1

        # 3. Synthesize Findings & Structured Sections
        findings_list: list[str] = []
        used_claim_texts: set[str] = set()

        for claim in verified_claims:
            if claim.claim_text in used_claim_texts:
                continue
            used_claim_texts.add(claim.claim_text)

            # Map citation tags
            cit_tags = []
            for ev_id in claim.supporting_evidence_ids:
                if ev_id in chunk_to_citation_idx:
                    cit_tags.append(f"[Source {chunk_to_citation_idx[ev_id]}]")

            tag_str = f" {' '.join(cit_tags)}" if cit_tags else ""

            # Format metric line
            if claim.metric and claim.value is not None:
                line = f"**{claim.company}** ({claim.year}) **{claim.metric.upper()}**: {claim.value} {claim.unit or ''}{tag_str}"
            else:
                line = f"{claim.claim_text}{tag_str}"

            findings_list.append(line)

        # 4. Build Sections
        exec_summary = f"Bu araştırma raporu **'{user_query}'** sorgusu kapsamında {len(verified_claims)} doğrulanmış iddia ve {len(active_citations)} bağımsız kaynak chunk'ı analiz edilerek hazırlanmıştır."
        if active_citations:
            exec_summary += f" Başlıca bulgular {active_citations[0].ticker} ({active_citations[0].year}) verilerine dayanmaktadır. [Source 1]"

        # Comparison Section if applicable
        comparison_text: str | None = None
        if state.structured_plan and state.structured_plan.is_comparison:
            comp_lines = ["### 📊 Şirket Karşılaştırma Özeti\n"]
            for claim in verified_claims:
                if claim.company:
                    cit_tag = ""
                    if claim.supporting_evidence_ids and claim.supporting_evidence_ids[0] in chunk_to_citation_idx:
                        cit_tag = f" [Source {chunk_to_citation_idx[claim.supporting_evidence_ids[0]]}]"
                    comp_lines.append(f"- **{claim.company}**: {claim.claim_text}{cit_tag}")
            comparison_text = "\n".join(comp_lines)

        # Contradictions Section
        contradictions_list: list[str] = []
        if state.contradictions:
            for cnt in state.contradictions:
                contradictions_list.append(f"⚠️ **Çelişkili Kaynak Uyarısı**: {cnt.description}")

        # Uncertainties / Unanswered Questions
        uncertainties_list: list[str] = []
        for rej in state.rejected_claims:
            uncertainties_list.append(f"Metin içi doğrulanamayan iddia reddedildi: '{rej.claim_text}' ({rej.reason})")

        # 5. Build Final Markdown Answer
        markdown_parts: list[str] = [
            f"# 📋 Şirket Araştırma Raporu: {user_query}\n",
            f"## 📌 Özet\n{exec_summary}\n",
            "## 🔍 Doğrulanmış Bulgular\n" + "\n".join(f"- {f}" for f in findings_list) + "\n",
        ]

        if comparison_text:
            markdown_parts.append(f"{comparison_text}\n")

        if contradictions_list:
            markdown_parts.append("## ⚠️ Çelişkili Bilgiler\n" + "\n".join(contradictions_list) + "\n")

        if uncertainties_list:
            markdown_parts.append("## ❓ Belirsizlikler ve Reddedilen İddialar\n" + "\n".join(f"- {u}" for u in uncertainties_list) + "\n")

        # Build Evidence Appendix
        evidence_appendix_list: list[dict[str, Any]] = []
        appendix_lines = ["## 📚 Kaynakça ve Kanıt Eki\n"]
        for cit in active_citations:
            appendix_lines.append(
                f"**[Source {cit.citation_index}]** {cit.company} ({cit.ticker}) - {cit.year} Raporu\n"
                f"  - Dosya: `{cit.source_file}` (Sayfa {cit.page_number}, Chunk ID: `{cit.chunk_id}`)\n"
                f"  - Yöntem: `{cit.retrieval_method}`\n"
                f"  - Alıntı: *\"{cit.snippet}\"*\n"
            )
            evidence_appendix_list.append(cit.model_dump())

        markdown_parts.append("\n".join(appendix_lines))

        full_answer = "\n".join(markdown_parts)

        # 6. Run Citation Completeness Check
        quality_warnings = self._checker.check_completeness(full_answer)

        output = ReportOutput(
            answer=full_answer,
            executive_summary=exec_summary,
            findings=findings_list,
            comparison=comparison_text,
            uncertainties=uncertainties_list,
            contradictions=contradictions_list,
            citations=active_citations,
            evidence_appendix=evidence_appendix_list,
            unanswered_questions=[rej.claim_text for rej in state.rejected_claims],
            quality_warnings=quality_warnings,
        )

        state.final_answer = output.answer
        state.structured_report = output
        return output
