# Staging Baseline

Status: `NOT_MEASURED`

No Cloud Run staging revision exists, so no real staging quality, latency, token, retry, fallback, cost, or load-test baseline is available. Local Docker and mock-model measurements must not be represented as cloud staging measurements.

This document is updated only after all of the following exist:

- immutable signed image digest;
- ready Qdrant Cloud staging collection;
- ready, non-empty Neo4j Aura staging graph;
- Cloud Run staging URL and revision;
- real Opik and Grafana Cloud delivery;
- bounded staging eval and Locust reports.

Expected machine-readable output:

`artifacts/production_activation/baselines/staging_baseline.json`

Required fields include task success, citation coverage/correctness, groundedness, multi-hop success, retrieval recall, p50/p95/p99 latency, error rate, model calls, input/output/total tokens, retry/fallback rate, and estimated cost metadata.
