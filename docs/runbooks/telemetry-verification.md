# Telemetry Verification Runbook

## Opik

Configure `OPIK_ENABLED`, `OPIK_API_KEY`, and `OPIK_WORKSPACE` through the runtime secret mechanism. Run one bounded staging research request, then record its request, run, trace, Opik trace, project URL, version, prompt/workflow versions, config hash, model, token, retry, retrieval, citation, latency, and status metadata.

## Grafana Cloud

Configure `TELEMETRY_ENABLED=true`, `TELEMETRY_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and secret `OTEL_EXPORTER_OTLP_HEADERS`. Verify request/error counters, latency, active tasks, model calls/latency, tokens, retries, dependency latency, citation coverage, and budget failures. Verify structured logs can be searched by `trace_id` and correlated to traces.

## Privacy

Search exported telemetry and artifacts for API keys, authorization headers, passwords, cookies, `.env` values, full document text, and oversized chunks. Any match blocks deployment. Exporter failure must leave application liveness and bounded research functional.

Current status: no real Opik or Grafana Cloud credentials or delivery evidence are available.
