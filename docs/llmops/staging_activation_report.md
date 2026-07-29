# Phase 7.5: Staging Production Activation Report

Date: 2026-07-30
Repository: `ceylanal/company-intelligence-graphrag`
Branch: `codex/configure-staging-runtime-identity`
Checkpoint commit: `d847683d00b383ee699eb1930359dde65b4de4e9`

## Credential Precheck

Status: `PASS`

GitHub CLI, staging GitHub Environment, Google Workload Identity Federation, Google Secret Manager, Qdrant Cloud, Neo4j Aura, Comet Opik and Grafana Cloud OTLP credentials were exercised by real staging operations. No secret value is stored in the report or evidence.

## Qdrant Cloud Migration

Status: `PASS`

- Collection: `company_documents_staging`
- Points: 25,859
- Vector: 384 dimensions, Cosine
- ID/payload checksum: `7ec2d5f537c205e73febf71978962bf1276f24a8aaaa445bd268feaa0b43fb01`
- Required payload indexes: `ticker`, `year`, `company`, `report_type`, `language`
- Post-fix filtered vector queries: HTTP 200

The first live baseline exposed missing payload indexes through real Qdrant HTTP 400 responses. The broken run (`30499589188`) was retained as diagnostic evidence. The indexes were created without rewriting points, verified over all 25,859 records, and made idempotent in `scripts/qdrant_activation.py`.

Evidence:

- `artifacts/production_activation/qdrant/cloud-inventory.json`
- `artifacts/production_activation/qdrant/payload-index-evidence.json`

## Neo4j Aura Migration

Status: `PASS`

- Database: `64a945c7`
- Nodes: 4
- Relationships: 3
- Labels: Company 1, Date 1, FinancialMetric 1, Person 1
- Relationship types: `FOR_DATE` 1, `HOLDS_ROLE_AT` 1, `REPORTED_METRIC` 1
- Duplicate deterministic node/relationship IDs: 0/0
- Missing provenance: 0
- Orphan nodes: 0
- Multi-hop queries: 3/3 returned the expected path
- Constraints/indexes: 13/26

Evidence:

- `artifacts/production_activation/neo4j/cloud-migration-result.json`
- `artifacts/production_activation/neo4j/cloud-inventory.json`

## Cloud Run Deployment

Status: `PASS`

- Verified workflow: GitHub Actions run `30499923938`
- Signed release workflow: run `30498173366`
- Signed multi-platform digest: `sha256:a0a8b9ae9b20a3c3e745961b2ee63bbde40dd6b626b970f8523924608ace54d3`
- Cloud Run resolved linux/amd64 digest: `sha256:d57d0d38177a7ad14d409be467135475b93c9b55969a065594e52947278096c7`
- Revision: `company-graphrag-staging-sha-a0a8b9ae-run-99923938`
- Runtime: gen2, CPU 1, memory 2 GiB, min 0, max 1, concurrency 4, timeout 300 seconds
- Access: private; unauthenticated health request returned 403
- Traffic: 100% staging revision
- Production service: absent; no production deployment or traffic change was made

The original requested digest `d13134d...` was superseded because live staging identified runtime defects. The final digest contains the bounded runtime fixes and passed release security gates with 0 HIGH/CRITICAL Trivy findings and a verified Cosign signature.

Evidence:

- `artifacts/production_activation/staging/runtime-evidence.json`
- `artifacts/production_activation/github_run_30498173366/release-candidate-evidence/`
- Trivy's committed evidence is the sanitized `trivy-release-summary.json`; the raw scanner export remains local because base-image metadata contains a public package-signing key that triggers generic secret scanners.

## Smoke Tests

Status: `PASS`

Run `30499923938` passed 6/6 checks: liveness, readiness, version, invalid input, missing API-key rejection and bounded research. Readiness reported both Qdrant and Neo4j healthy. The bounded research request returned HTTP 200 after the Qdrant index fix.

Evidence: `artifacts/production_activation/github_run_30499923938/staging-smoke-results/smoke.json`

## Live Observability

Status: `PARTIAL`

Verified:

- Application request, run and trace IDs are present.
- Opik health returned 200.
- Opik trace batch and patch requests returned 204.
- Grafana OTLP `/otlp/v1/traces` authentication and transport returned 200.
- Final revision had zero `Failed to export` or `opik_export_failed` log matches.

Not verified:

- A positive Grafana Tempo trace-search result.
- Token usage, cost, retry and fallback fields in the observability UI/API.

Unverified telemetry is not marked as passed.

Evidence: `artifacts/production_activation/observability/live-evidence.json`

## Staging Eval Baseline

Status: `QUALITY_GATE_FAILED`

Execution completed successfully against the private staging endpoint: 34/34 requests returned HTTP 200. The resulting quality is not production-ready:

- Correctness: 32.35%
- Faithfulness proxy: 100%
- Citation correctness proxy: 36.36%
- Retrieval recall proxy: 61.76%
- Multi-hop success: 0%
- Hallucination proxy: 55.88%
- P50/P95 latency: 5,060.59 / 5,557.79 ms

Faithfulness, citation and retrieval values are explicitly deterministic proxies because the public response does not expose raw retrieval evidence or an LLM-judge result.

Evidence: `artifacts/production_activation/github_run_30499923938/staging-eval-baseline/`

## Locust Load Baseline

Status: `PASS`

The bounded health/readiness/version profile generated no paid-model repeated traffic.

| Users | Requests | Failures | Success | P50 | P95 | P99 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 30 | 0 | 100% | 99 ms | 110 ms | 140 ms |
| 5 | 141 | 0 | 100% | 99 ms | 100 ms | 120 ms |
| 10 | 278 | 0 | 100% | 98 ms | 110 ms | 130 ms |

Provider fallback was not exercised by this health-only profile and is recorded as `null`, not zero.

Evidence: `artifacts/production_activation/github_run_30499923938/staging-load-baseline/`

## Backup–Restore

Status: `BLOCKED_EXTERNAL_DEPENDENCY`

Qdrant: `PASS`. A real Cloud snapshot was restored into the isolated `company_documents_staging_restore_rehearsal_v2` collection in 37.78 seconds. Point count, vectors, payload schema and checksum matched. The final post-index run is `30500595911`.

Neo4j: `BLOCKED_EXTERNAL_DEPENDENCY`. The connected AuraDB Free instance does not provide snapshot backup/restore or export. No simulated restore was reported.

Evidence:

- `artifacts/production_activation/github_run_30500595911/backup-verification/disaster_recovery/qdrant-restore.json`
- `docs/runbooks/neo4j-backup-restore.md`

## Rollback Rehearsal

Status: `PASS`

Staging traffic was switched to the known 1 GiB revision `company-graphrag-staging-sha-9b1f6433d3b8`. The bounded research smoke returned HTTP 503 in 12 seconds. Traffic was then restored to `company-graphrag-staging-sha-a0a8b9ae-run-99923938`; readiness and bounded research both returned HTTP 200. Recovery verification completed in 28 seconds. Production was untouched.

Evidence: `artifacts/production_activation/rollback/rollback-rehearsal.json`

## External Blockers

1. Neo4j Aura backup/restore requires an Aura tier that exposes backup and restore.
2. The frozen staging quality baseline failed on correctness, multi-hop and hallucination proxies.
3. Grafana trace search and token/cost/retry/fallback fields remain unverified.

## Manual Actions

No credential or form entry remains for the currently available services. The remaining actions require product/quality decisions rather than missing text fields:

1. Upgrade or replace AuraDB Free with a tier that supports backup/restore, then perform an isolated restore rehearsal.
2. Remediate answer grounding and multi-hop behavior, then rerun the frozen 34-sample baseline.
3. Query one recorded trace ID in Grafana Tempo and verify token, cost, retry and fallback attributes.

## Final Decision

```text
CLOUD_DATA_MIGRATION_PASSED
STAGING_DEPLOYMENT_PASSED
STAGING_RUNTIME_VALIDATION_PASSED
LOCUST_LOAD_BASELINE_PASSED
QDRANT_DISASTER_RECOVERY_PASSED
ROLLBACK_REHEARSAL_PASSED

LIVE_OBSERVABILITY_PARTIAL
STAGING_QUALITY_GATE_FAILED
NEO4J_DISASTER_RECOVERY_BLOCKED_EXTERNAL_DEPENDENCY

STAGING_ACTIVATION_BLOCKED
PRODUCTION_ACTIVATION_BLOCKED
```

Production deployment and production traffic remain disabled.
