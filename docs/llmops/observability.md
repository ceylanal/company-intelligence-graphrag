# Observability Guide

Defaults are private and fail-open:

- `TELEMETRY_ENABLED=false`, `TELEMETRY_EXPORTER=none`
- `TELEMETRY_CAPTURE_PROMPTS=false`
- API keys, authorization, cookies, passwords, secrets, tokens, and OTLP headers are recursively redacted.
- Full prompts, user input, PDF text, and retrieved chunks are not telemetry attributes.

For local span inspection, set `TELEMETRY_ENABLED=true` and `TELEMETRY_EXPORTER=console`. For Grafana Cloud, use the HTTPS OTLP endpoint and inject `OTEL_EXPORTER_OTLP_HEADERS` at runtime; never commit it. Export failures are handled by the OpenTelemetry batch exporter and do not gate API responses.

Prometheus metrics are exposed at `/metrics`: request count/latency, active research tasks, dependency latency, model calls, token direction, retries, and citation coverage. The dashboard starter is `config/grafana/dashboard.json`.

Opik is disabled by default. When enabled, the SDK emits a metadata-only research trace containing `trace_id`, `request_id`, `run_id`, prompt/workflow version, and `config_hash`; export and flush failures are caught. A real Opik workspace verification requires user credentials and is not claimed.
