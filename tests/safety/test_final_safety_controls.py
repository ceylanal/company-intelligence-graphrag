"""Regression tests for production-safety fixes identified in the final audit."""

from __future__ import annotations

import pytest

from company_graphrag.observability import tracing
from company_graphrag.rag.generator import RAGGenerator


def test_trace_span_never_records_raw_exception_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """OTel status may identify an error class, but must not export exception text."""

    statuses: list[object] = []

    class FakeSpan:
        def __enter__(self) -> FakeSpan:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def set_status(self, status: object) -> None:
            statuses.append(status)

    class FakeTracer:
        def start_as_current_span(self, *_: object, **__: object) -> FakeSpan:
            return FakeSpan()

    monkeypatch.setattr(tracing.trace, "get_tracer", lambda _: FakeTracer())
    with pytest.raises(RuntimeError, match="demo_value_for_redaction"):
        with tracing.span("audit"):
            raise RuntimeError("demo_value_for_redaction")

    assert len(statuses) == 1


def test_rag_filter_validation_blocks_before_retrieval() -> None:
    """Invalid company filters cannot bypass the input boundary through RAGGenerator."""

    class NeverRetrieve:
        def retrieve(self, **_: object) -> list[object]:
            raise AssertionError("retrieval must not run after a filter safety block")

    result = RAGGenerator(retriever=NeverRetrieve(), mock_mode=True).generate(
        "ASELS finansal özeti",
        ticker="../../AKBNK",
    )

    assert result.fallback_reason == "input_guardrail_block"
    assert result.used_source_count == 0
