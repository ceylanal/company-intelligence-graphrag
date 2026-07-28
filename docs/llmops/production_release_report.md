# Production Release Report

Decision: `PRODUCTION_ACTIVATION_BLOCKED`

| Area | Status | Evidence |
|---|---|---|
| GitHub Actions | PASS | Run `30404491347`: quality, secret-scan, container |
| GitHub environments | PASS | `staging` branch policy; `production` main-only plus required reviewer |
| GHCR | BLOCKED | No package digest has been published |
| Cosign | BLOCKED | No remote digest exists to sign or verify |
| Trivy | PASS | GitHub artifact: 0 critical and 0 total findings |
| SBOM | PASS | GitHub artifact: SPDX 2.3, 230 packages |
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

## GitHub evidence

- Pull request: https://github.com/ceylanal/company-intelligence-graphrag/pull/1
- Successful CI run: https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30404491347
- Tested commit: `87dfa10711f27c3cab02d9ee716eae853ce8375a`
- Quality job: 259 tests, 0 failures, 0 errors, 80.23% line coverage
- Container job: non-root, smoke, Compose readiness, dependency-failure readiness, Trivy, and SBOM all passed
- Machine-readable record: `artifacts/production_activation/github_actions/successful-run.json`

The release workflow and GHCR publish remain pending because the workflow is not on the default branch and merging or publishing has not been authorized.

## Required manual account configuration

See `config/production_activation.yaml` and the production/staging runbooks. GitHub environments were created without adding secret values. No paid resource or billing change has been created.

## Production approval

Not granted. Production deployment, tag, GitHub Release, and public release remain prohibited until the user explicitly approves them after the release-candidate gates pass.
