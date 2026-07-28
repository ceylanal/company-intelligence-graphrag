# Production Release Report

Decision: `PRODUCTION_ACTIVATION_BLOCKED`

| Area | Status | Evidence |
|---|---|---|
| GitHub Actions | PASS | Post-merge main run `30406960689`; published release run `30409074505` |
| GitHub environments | PASS | `staging` branch policy; `production` main-only plus required reviewer |
| GHCR | PASS | Multi-platform image `sha256:d13134d91ad3e0168ca46012f9264549e0e67ac8b41dd7c21e9f50c4e7d914fa` |
| Cosign | PASS | Keyless signature verified for the immutable digest and `release.yml@refs/heads/main` |
| Trivy | PASS | Scheduled run `30406188636`: 0 HIGH/CRITICAL; published release run `30409074505`: 0 critical |
| SBOM | PASS | Published release artifact: SPDX 2.3, 230 packages; build provenance and SBOM attestations present |
| Qdrant Cloud | BLOCKED | No cloud URL/key; local baseline is 25,859 points |
| Neo4j Aura | BLOCKED | No Aura credentials and current source audit is empty |
| Cloud Run staging | BLOCKED | No GCP CLI, identity, project, WIF, or secrets |
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
- Post-merge main CI: https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30406960689
- Tested remediation commit: `4449a11673bd7a1e0f6ecf35294792785e27d221`
- Quality job: 260 tests, 0 failures, 0 errors, 80.25% line coverage
- Container job: non-root, smoke, Compose readiness, dependency-failure readiness, Trivy, and SBOM all passed
- Scheduled security run: https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30406188636
- Scheduled security evidence: 0 HIGH/CRITICAL findings; Gitleaks scanned 23 commits with no leaks
- Non-publishing release candidate: https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30406190225
- Release evidence: image smoke passed, 0 critical findings, SPDX 2.3 SBOM with 230 packages
- Final eval evidence: 34 samples, `CONDITIONAL PASS — KNOWN LIMITATIONS`; this is not a live staging baseline
- Published release candidate: https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30409074505
- Published commit: `9fc138e595684acb7056fde08fb1ec1241d1b74a`
- Published tags: `sha-9fc138e59568`, `0.1.0`, and `staging`
- Immutable image: `ghcr.io/ceylanal/company-intelligence-graphrag@sha256:d13134d91ad3e0168ca46012f9264549e0e67ac8b41dd7c21e9f50c4e7d914fa`
- Platforms: `linux/amd64` and `linux/arm64`
- Cosign identity: `https://github.com/ceylanal/company-intelligence-graphrag/.github/workflows/release.yml@refs/heads/main`
- Cosign issuer: `https://token.actions.githubusercontent.com`
- Machine-readable records:
  - `artifacts/production_activation/github_actions/successful-run.json`
  - `artifacts/production_activation/github_actions/security-remediation-run.json`
  - `artifacts/production_activation/github_actions/published-release-run.json`

The release workflow is active on the default branch. After explicit user approval, run `30409074505` used `publish=true`; it pushed the multi-platform image with provenance and SBOM attestations, then keyless-signed and verified the immutable digest. This publication is not a Cloud Run deployment and does not constitute production activation.

## Required manual account configuration

See `config/production_activation.yaml` and the production/staging runbooks. GitHub environments were created without adding secret values. No paid resource or billing change has been created.

## Production approval

GHCR publication and Cosign signing were approved and completed. Production deployment, a Git tag, and a GitHub Release were not approved and remain prohibited until the remaining production gates pass and the user explicitly approves them.
