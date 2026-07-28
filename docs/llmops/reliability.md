# Reliability, Cost, and Performance Policy

Only network/connection timeouts, transport failures, HTTP 429, and HTTP 5xx are transient. Authentication, validation, malformed input, and other 4xx failures are permanent. Transient retries use exponential backoff with jitter; defaults are two retries and a 250 ms base.

| Dependency | Timeout | Retries | Failure behavior |
|---|---:|---:|---|
| Qdrant | 5 s | 2 transient-only | readiness 503 / controlled research failure |
| Neo4j | 5 s | 2 transient-only | readiness 503 / controlled research failure |
| LLM | 30 s | 2 transient-only | deterministic grounded fallback, explicitly marked |
| OTLP / Opik | exporter-owned | non-blocking | logs warning; application continues |

Per-research defaults are 300 seconds, 12 model calls, 64k input tokens, 16k output tokens, 80k total tokens, and no monetary cap until a reviewed provider price is configured. `config/model_pricing.yaml` is dated; mock cost is zero. No unreviewed provider prices are invented.

Idempotency uses the `Idempotency-Key` plus query hash and the existing durable checkpoint. A key cannot be reused for a different query. Process-local rate and concurrency controls are safe for the one-instance staging cap; a multi-instance production service needs a shared limiter.

The Locust file supports `smoke`, `normal`, `burst`, `long-running`, and `dependency-failure` tags. Baseline p50/p95 and quality regression thresholds must come from measured artifacts; no fabricated gate is included.
