# Production Release Report

Decision: `PRODUCTION_ACTIVATION_BLOCKED`

| Area | Status | Evidence |
|---|---|---|
| GitHub Actions | BLOCKED | Workflows are local/uncommitted; remote has no runs |
| GHCR | BLOCKED | No package digest has been published |
| Cosign | BLOCKED | No remote digest exists to sign or verify |
| Trivy | PASS (local image) | `artifacts/security/trivy-image.json` |
| SBOM | PASS (local image) | `artifacts/security/sbom-image.spdx.json` |
| Qdrant Cloud | BLOCKED | No cloud URL/key; local baseline is 25,859 points |
| Neo4j Aura | BLOCKED | No Aura credentials and current source audit is empty |
| Cloud Run staging | BLOCKED | No GCP CLI, identity, project, WIF, secrets, or signed digest |
| Opik | BLOCKED | No real project credential or trace ID |
| Grafana Cloud | BLOCKED | No OTLP credential or delivery evidence |
| Staging eval | BLOCKED | No staging revision |
| Locust staging | BLOCKED | No staging URL |
| Backup–restore | BLOCKED | No cloud databases |
| Revision rollback | BLOCKED | No Cloud Run revisions |
| Production deployment | PENDING | Explicit approval and all release gates required |
| Production smoke | PENDING | No deployment |
| E2E production | PENDING | No deployment |

## Local evidence

The Docker release candidate builds and runs as non-root, all core services become ready, dependency failure/recovery works, graceful shutdown exits 0, the local containerized Locust smoke has zero failures, and the current Trivy CRITICAL gate has zero unfixed findings.

## Required manual account configuration

See `config/production_activation.yaml` and the production/staging runbooks. No paid resource or billing change has been created.

## Production approval

Not granted. Production deployment, tag, GitHub Release, and public release remain prohibited until the user explicitly approves them after the release-candidate gates pass.
