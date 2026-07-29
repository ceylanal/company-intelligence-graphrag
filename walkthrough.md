# Phase 7.5 Staging Activation Walkthrough

This walkthrough records the verified order of the real staging activation. The machine-readable checkpoint is `artifacts/production_activation/activation_manifest.json`.

1. Verified GitHub, GCP WIF, Secret Manager, Qdrant, Neo4j, Opik and Grafana access without printing secret values.
2. Migrated 25,859 Qdrant points and verified dimension, distance, checksum and samples.
3. Loaded the idempotent Neo4j staging graph and verified schema, provenance and three multi-hop queries.
4. Published and signed digest `sha256:a0a8b9ae9b20a3c3e745961b2ee63bbde40dd6b626b970f8523924608ace54d3`.
5. Mirrored that immutable digest to Artifact Registry and deployed private Cloud Run staging.
6. Detected missing Qdrant payload indexes from real 400 responses, added the five required indexes, and confirmed filtered queries return 200.
7. Passed the 6/6 smoke suite and 449-request bounded 1/5/10-user load test.
8. Ran the frozen 34-sample staging evaluation. Transport passed; the resulting quality gate failed.
9. Verified Opik trace delivery and Grafana OTLP transport; Grafana trace search and detailed cost/token fields remain unverified.
10. Restored a real Qdrant snapshot into an isolated collection. Neo4j restore is unavailable on AuraDB Free.
11. Switched staging to a known bad revision, observed HTTP 503, and restored the healthy revision with readiness and research HTTP 200.
12. Confirmed there is no production Cloud Run service and no production traffic was opened.

Final state:

```text
STAGING_ACTIVATION_BLOCKED
PRODUCTION_ACTIVATION_BLOCKED
```

The blockers are the failed quality baseline, Neo4j Free-tier restore limitation and incomplete Grafana field-level verification.
