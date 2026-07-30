"""OpenTelemetry setup that never makes telemetry a runtime dependency."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import unquote

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from company_graphrag.config import Settings, settings

logger = structlog.get_logger(__name__)
_configured = False


def configure_telemetry(settings_obj: Settings = settings) -> None:
    """Configure console or OTLP tracing; log and continue on exporter failure."""
    global _configured
    if _configured or not settings_obj.telemetry_enabled or settings_obj.telemetry_exporter == "none":
        return
    try:
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": settings_obj.otel_service_name,
                    "deployment.environment": settings_obj.environment,
                }
            )
        )
        if settings_obj.telemetry_exporter == "console":
            exporter: Any = ConsoleSpanExporter()
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(
                endpoint=settings_obj.otel_exporter_otlp_endpoint,
                headers=_parse_headers(settings_obj.otel_exporter_otlp_headers),
            )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _configured = True
    except Exception as exc:
        logger.warning("telemetry_configuration_failed", error_type=type(exc).__name__)


def flush_telemetry(timeout_millis: int = 5000) -> bool:
    """Force buffered spans out before serverless CPU is throttled."""
    provider = trace.get_tracer_provider()
    force_flush = getattr(provider, "force_flush", None)
    if not callable(force_flush):
        return False
    try:
        return bool(force_flush(timeout_millis=timeout_millis))
    except Exception as exc:
        logger.warning("telemetry_flush_failed", error_type=type(exc).__name__)
        return False


def _parse_headers(raw: str) -> dict[str, str]:
    return {
        unquote(key.strip()): unquote(value.strip())
        for item in raw.split(",")
        if "=" in item
        for key, value in [item.split("=", 1)]
    }


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """Create a span and record failures without masking the application error."""
    tracer = trace.get_tracer("company_graphrag")
    with tracer.start_as_current_span(name, attributes=attributes) as current:
        try:
            yield current
        except Exception as exc:
            # Exception messages and stack locals can contain credentials, provider
            # responses, or source text.  Record only the class in span status; the
            # request path returns a separately sanitized public error.
            current.set_status(trace.Status(trace.StatusCode.ERROR, type(exc).__name__))
            raise
