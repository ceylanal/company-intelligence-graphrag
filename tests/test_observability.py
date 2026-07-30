"""Structured logging, correlation, and telemetry fail-open tests."""

from company_graphrag.config import Settings
from company_graphrag.observability.context import (
    bind_context,
    current_request_id,
    current_run_id,
    current_trace_id,
    reset_context,
)
from company_graphrag.observability.logging import REDACTED, redact
from company_graphrag.observability.tracing import (
    _parse_headers,
    configure_telemetry,
    flush_telemetry,
)


def test_trace_context_propagates_and_resets() -> None:
    tokens = bind_context(request_id="req-1", run_id="run-1", trace_id="trace-1")
    assert (current_request_id(), current_run_id(), current_trace_id()) == ("req-1", "run-1", "trace-1")
    reset_context(tokens)
    assert current_request_id() == ""


def test_recursive_secret_redaction() -> None:
    payload = {
        "authorization": "Bearer abc",
        "nested": {"api_key": "secret", "message": "Bearer xyz"},
        "safe": "visible",
    }
    sanitized = redact(payload)
    assert sanitized["authorization"] == REDACTED
    assert sanitized["nested"]["api_key"] == REDACTED
    assert "xyz" not in sanitized["nested"]["message"]
    assert sanitized["safe"] == "visible"


def test_unreachable_telemetry_configuration_is_fail_open() -> None:
    configure_telemetry(
        Settings(
            environment="test",
            telemetry_enabled=True,
            telemetry_exporter="otlp",
            otel_exporter_otlp_endpoint="http://127.0.0.1:1",
        )
    )


def test_otlp_headers_decode_standard_url_encoding() -> None:
    headers = _parse_headers("Authorization=Basic%20opaque-token,x-scope=staging%2Ftraces")

    assert headers == {
        "Authorization": "Basic opaque-token",
        "x-scope": "staging/traces",
    }


def test_flush_telemetry_is_safe_without_configured_sdk() -> None:
    assert isinstance(flush_telemetry(timeout_millis=1), bool)
