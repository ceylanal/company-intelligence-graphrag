# Production Release Report

Decision: `PRODUCTION_ACTIVATION_BLOCKED`

| Area | Status | Evidence |
|---|---|---|
| GitHub Actions | PASS | Main run `30405381168`; remediation PR run `30406163831` |
| GitHub environments | PASS | `staging` branch policy; `production` main-only plus required reviewer |
| GHCR | BLOCKED | No package digest has been published |
| Cosign | BLOCKED | No remote digest exists to sign or verify |
| Trivy | PASS | Scheduled run `30406188636`: 0 HIGH/CRITICAL; release run `30406190225`: 0 critical |
| SBOM | PASS | Release artifact: SPDX 2.3, 230 packages |
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

The Docker release candidate builds for Linux AMD64 and runs as `appuser`, all core services become ready, dependency failure/recovery works, graceful shutdown exits 0, and the current Trivy HIGH/CRITICAL gate has zero unfixed findings. The remediated image contains FastEmbed 0.8.0 and Pillow 12.3.0 while preserving the existing CLS-pooled 384-dimensional embedding contract.

## GitHub evidence

- Pull request: https://github.com/ceylanal/company-intelligence-graphrag/pull/1
- Main activation CI: https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30405381168
- Security remediation pull request: https://github.com/ceylanal/company-intelligence-graphrag/pull/11
- Remediation CI: https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30406163831
- Tested remediation commit: `4449a11673bd7a1e0f6ecf35294792785e27d221`
- Quality job: 260 tests, 0 failures, 0 errors, 80.25% line coverage
- Container job: non-root, smoke, Compose readiness, dependency-failure readiness, Trivy, and SBOM all passed
- Scheduled security run: https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30406188636
- Scheduled security evidence: 0 HIGH/CRITICAL findings; Gitleaks scanned 23 commits with no leaks
- Non-publishing release candidate: https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30406190225
- Release evidence: image smoke passed, 0 critical findings, SPDX 2.3 SBOM with 230 packages
- Final eval evidence: 34 samples, `CONDITIONAL PASS — KNOWN LIMITATIONS`; this is not a live staging baseline
- Machine-readable records:
  - `artifacts/production_activation/github_actions/successful-run.json`
  - `artifacts/production_activation/github_actions/security-remediation-run.json`

The release workflow is active on the default branch. The successful validation used `publish=false`; GHCR push, provenance publication, and keyless Cosign signing were intentionally skipped because publishing has not been authorized.

## Required manual account configuration

See `config/production_activation.yaml` and the production/staging runbooks. GitHub environments were created without adding secret values. No paid resource or billing change has been created.

## Production approval

Not granted. Production deployment, tag, GitHub Release, and public release remain prohibited until the user explicitly approves them after the release-candidate gates pass.
