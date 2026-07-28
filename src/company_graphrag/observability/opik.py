"""Optional Opik trace bridge correlated with OpenTelemetry identifiers."""

from __future__ import annotations

from typing import Any

import structlog

from company_graphrag.config import settings
from company_graphrag.observability.context import current_request_id, current_trace_id

logger = structlog.get_logger(__name__)
_client: Any = None


def record_opik_run(
    *,
    run_id: str,
    status: str,
    workflow_version: str,
    prompt_bundle_version: str,
    config_hash: str,
) -> None:
    """Create a metadata-only Opik trace; failures are deliberately non-fatal."""
    if not settings.opik_enabled:
        return
    try:
        global _client
        if _client is None:
            from opik import Opik

            _client = Opik(api_key=settings.opik_api_key or None, workspace=settings.opik_workspace or None)
        trace = _client.trace(
            name="company-graphrag-research",
            input=None,
            output=None,
            metadata={
                "trace_id": current_trace_id(),
                "request_id": current_request_id(),
                "run_id": run_id,
                "status": status,
                "workflow_version": workflow_version,
                "prompt_bundle_version": prompt_bundle_version,
                "config_hash": config_hash,
            },
        )
        if hasattr(trace, "end"):
            trace.end()
        if hasattr(_client, "flush"):
            _client.flush(timeout=2)
    except Exception as exc:
        logger.warning("opik_export_failed", error_type=type(exc).__name__, run_id=run_id)
