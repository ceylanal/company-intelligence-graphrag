"""Structured JSON logging with recursive sensitive-data redaction."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

import structlog

from company_graphrag.config import settings
from company_graphrag.observability.context import current_request_id, current_run_id, current_trace_id

REDACTED = "[REDACTED]"
SENSITIVE_KEY = re.compile(
    r"(api[-_]?key|authorization|cookie|password|secret|token|credential|otel_exporter_otlp_headers)",
    re.IGNORECASE,
)
BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


def redact(value: Any, key: str = "") -> Any:
    """Recursively redact known credential keys and bearer values."""
    if key and SENSITIVE_KEY.search(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(item_key): redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return BEARER_VALUE.sub(f"Bearer {REDACTED}", value)
    return value


def _add_context(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict.setdefault("service", settings.otel_service_name)
    event_dict.setdefault("environment", settings.environment)
    event_dict.setdefault("trace_id", current_trace_id())
    event_dict.setdefault("request_id", current_request_id())
    event_dict.setdefault("run_id", current_run_id())
    sanitized = redact(event_dict)
    assert isinstance(sanitized, dict)
    return sanitized


def configure_logging() -> None:
    """Configure structlog once for container-friendly JSON output."""
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_context,  # type: ignore[list-item]
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
