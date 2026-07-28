# Gün 49 — LLMOps Final Audit

Date: 2026-07-28
Source revision: `179310c02dec8b3f3cd46bf03ab9a8ef544b1089` plus uncommitted workspace changes
LLMOps implementation decision: `LLMOPS_STAGE_PASSED`
Production activation decision: `PRODUCTION_ACTIVATION_BLOCKED`

All local release gates now pass. The production image builds successfully, runs as a non-root user, passes standalone and full-stack health checks, degrades correctly when either database is unavailable, recovers when the dependency returns, and shuts down gracefully. The image has no unfixed CRITICAL vulnerabilities in the current Trivy database.

Docker Desktop's existing VM remains unusable after its ext4 journal aborted when the host previously reached 100% utilization. Validation was therefore completed in a clean, isolated Colima/arm64 Docker Engine; the existing Docker Desktop data and volumes were not reset or deleted.

## A. System status

| Area | Status | Evidence |
|---|---|---|
| Packaging | PASS | arm64 image build, non-root runtime, healthcheck, standalone smoke, clean Compose core startup |
| Versioning | PASS | version endpoint and manifest hash `0c39f647…c4880` |
| Observability | PASS | trace/redaction/fail-open tests; correlated JSON logs; Compose profile starts |
| Reliability | PASS | dependency failure/recovery and graceful shutdown verified |
| Evals | PASS | 9/9 representative regression metrics |
| CI/CD | READY | workflows parse/configured; not executed on GitHub |
| Security | PASS | 0 unfixed CRITICAL image findings; image SPDX SBOM generated |
| Deployment | READY | OIDC/manual approval workflow; no cloud deployment attempted |
| Rollback | READY | revision traffic script/runbook; cloud rehearsal still requires a deployed revision |

## B. Docker verification

- Image: `company-graphrag:latest`
- Image ID: `sha256:c36acb03b0236b680cd94d779d09cb860716b6ab7081c6a4c8968b2878fe5fca`
- Platform: `linux/arm64`
- Runtime user: `appuser` (`uid=10001`, `gid=10001`)
- Image size reported by Docker inspect: 200,664,749 bytes
- Image healthcheck: configured and healthy
- Core services: API, Qdrant `v1.18.3`, and Neo4j `5.26-community` healthy
- Healthy readiness: HTTP 200 with both Qdrant and Neo4j `ok`
- Qdrant stopped: HTTP 503; Neo4j remained `ok`
- Qdrant restarted: readiness returned to HTTP 200
- Neo4j stopped: HTTP 503; Qdrant remained `ok`
- Neo4j restarted: readiness returned to HTTP 200
- API graceful shutdown: exit code 0, not OOM-killed, `application_stopped` logged
- Containerized Locust: 30 requests, 0 failures, median 4 ms, p95 71 ms
- Observability profile: command completed successfully

The Compose configuration now pins service-to-service endpoints to Docker DNS names. Host-local `.env` values such as `localhost` can no longer override the API container's Qdrant and Neo4j endpoints. Local Neo4j Compose credentials use the separate `COMPOSE_NEO4J_USERNAME` and `COMPOSE_NEO4J_PASSWORD` variables.

## C. Security artifacts

- Trivy CRITICAL gate: PASS, 0 unfixed CRITICAL findings
- Full Trivy image report: `artifacts/security/trivy-image.txt`
- Machine-readable Trivy report: `artifacts/security/trivy-image.json`
- SPDX image SBOM: `artifacts/security/sbom-image.spdx.json`
- SPDX package count: 227

## D. Quality metrics

- Eval regression: 9/9 PASS.
- Hybrid retrieval: recall@5 0.95, precision@5 0.78, MRR 0.91, nDCG@5 0.92.
- Answer token F1: 0.066; numeric accuracy: 0.5392; abstention F1: 0.3333.
- Groundedness, multi-hop task success, average model calls, and token usage do not have a newly measured staging baseline; no values are invented.

## E. Remaining operational notes

- Cloud Run deployment, live telemetry delivery, backup/restore, and rollback against a deployed revision were not performed because they require external credentials, a target environment, and deployment approval.
- Cloud Run's file checkpoint/run-manifest persistence is single-instance only; external durable persistence is required before scaling above one instance.
- The Homebrew Docker CLI is API 1.55 while the installed Colima Engine supports API 1.54. Local Colima commands currently require `DOCKER_API_VERSION=1.54` until the Engine catches up or the CLI is aligned.
- The test stack was shut down cleanly after validation. Its new isolated test volumes were retained.

## F. Production activation status

The local LLMOps stage is complete, but production activation is not. The repository currently has no successful remote GitHub Actions run, GHCR digest, Cosign verification, Qdrant Cloud migration, non-empty Aura graph migration, Cloud Run staging revision, real Opik trace, Grafana Cloud delivery evidence, staging baseline, cloud backup/restore rehearsal, live revision rollback, or production deployment.

See `docs/llmops/production_activation_plan.md` and `docs/llmops/production_release_report.md`. Deployment files alone are not treated as production evidence.
