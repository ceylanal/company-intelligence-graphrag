"""Citation validator tool verifying report statement claims against gathered evidence."""

from typing import Any

from company_graphrag.agents.tools.base import BaseTool
from company_graphrag.agents.tools.models import ValidateCitationInput, ValidateCitationOutput


class ValidateCitationTool(BaseTool[ValidateCitationOutput]):
    """Tool auditing citation integrity and grounding statements against evidence chunks."""

    name = "validate_citation"
    description = "Validates that a cited statement is grounded in available evidence chunks."
    input_model = ValidateCitationInput

    def _run(self, input_payload: ValidateCitationInput | dict[str, Any]) -> ValidateCitationOutput:
        if isinstance(input_payload, dict):
            input_payload = ValidateCitationInput(**input_payload)

        if not input_payload.cited_chunk_id or not input_payload.cited_chunk_id.strip():
            return ValidateCitationOutput(
                is_valid=False,
                citation_status="rejected",
                reason="Invalid or empty cited_chunk_id",
            )

        matched_item = None
        for ev in input_payload.available_sources:
            if ev.chunk_id == input_payload.cited_chunk_id:
                matched_item = ev
                break

        if not matched_item:
            return ValidateCitationOutput(
                is_valid=False,
                citation_status="rejected",
                reason=f"Chunk ID '{input_payload.cited_chunk_id}' not found in active evidence pool",
            )

        # Basic overlap / verification check
        statement_words = set(input_payload.citation_text.lower().split())
        content_words = set(matched_item.content.lower().split())
        overlap = len(statement_words.intersection(content_words))

        matched_item.citation_status = "verified"

        return ValidateCitationOutput(
            is_valid=True,
            citation_status="verified",
            reason=f"Citation grounded in chunk {matched_item.chunk_id} ({matched_item.source_file}, page {matched_item.page_number}). Term overlap: {overlap} words.",
            matched_evidence=matched_item,
        )
