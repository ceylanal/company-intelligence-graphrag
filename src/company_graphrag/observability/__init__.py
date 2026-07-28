"""Fail-open telemetry, metrics, and structured logging."""

from company_graphrag.observability.context import (
    bind_context,
    current_request_id,
    current_run_id,
    current_trace_id,
)
from company_graphrag.observability.logging import configure_logging, redact
from company_graphrag.observability.tracing import configure_telemetry, span

__all__ = [
    "bind_context",
    "configure_logging",
    "configure_telemetry",
    "current_request_id",
    "current_run_id",
    "current_trace_id",
    "redact",
    "span",
]
