# Phase 7.5: Staging Production Activation Report

Date: 2026-07-29  
Repository: `ceylanal/company-intelligence-graphrag`  
Branch: `codex/configure-staging-runtime-identity`  
Commit: `ac42c2da87c956099048778c0e28e5f1689796b7`

---

## 1. GitHub Actions

- **Workflows Verified**:
  - `CI` (`.github/workflows/ci.yml`): Passing in PR and post-merge runs (Post-merge main run `#30406960689`).
  - `Release Candidate` (`.github/workflows/release.yml`): Published release run `#30409074505` passed all hermetic quality gates, Trivy critical scan, SBOM generation, and Cosign keyless signing.
  - `Backup Verification` (`.github/workflows/backup-verify.yml`): Triggered live on GitHub Actions (Run `#30414786770` on `codex/configure-staging-runtime-identity` branch). Passed 100% cleanly.
  - `Scheduled Security` (`.github/workflows/security.yml`): Run `#30406188636` passed with 0 HIGH/CRITICAL vulnerabilities and 0 Gitleaks secret leaks.
  - `Deploy Cloud Run Staging` (`.github/workflows/deploy-cloud-run.yml`): Ready for dispatch.
- **Evidence**:
  - Downloaded workflow artifacts stored at `artifacts/production_activation/github_run_30414786770/`.

---

## 2. Image / GHCR / SBOM / Cosign

- **Published Digest**: `ghcr.io/ceylanal/company-intelligence-graphrag@sha256:d13134d91ad3e0168ca46012f9264549e0e67ac8b41dd7c21e9f50c4e7d914fa`
- **Tags**: `sha-9fc138e59568`, `0.1.0`, `staging`
- **Architecture & Runtime**: Multi-platform (`linux/amd64`, `linux/arm64`), non-root `appuser` (`uid=10001`, `gid=10001`).
- **SBOM**: SPDX 2.3 JSON format containing 230 packages (`artifacts/security/sbom-image.spdx.json`).
- **Cosign Verification**: Keyless OIDC signature verified against issuer `https://token.actions.githubusercontent.com` and repository `ceylanal/company-intelligence-graphrag`.
- **Trivy Vulnerability Scan**: 0 CRITICAL findings (`artifacts/security/trivy-image.json`).

---

## 3. Qdrant Cloud Migration

- **Cloud Connection**: Verified via GitHub Actions run `#30414786770` connecting to `https://8aa7d6a2-3631-4441-ba0a-d07c4dae1cd6.eu-central-1-0.aws.cloud.qdrant.io`.
- **Local Baseline Inventory**:
  - Collection: `company_documents`
  - Points Count: **25,859**
  - Storage Size: 150.06 MB
  - SHA256 Checksum: `7ec2d5f537c205e73febf71978962bf1276f24a8aaaa445bd268feaa0b43fb01`
  - Vector Dimension: 384 (Cosine distance)
  - Report: `artifacts/production_activation/qdrant/local-inventory.json`
- **Cloud Inventory Status**:
  - Target Collection: `company_documents_staging`
  - Status: `NOT_FOUND` (`exists: false`, `points_count: 0`)
  - Report: `artifacts/production_activation/qdrant/cloud-inventory.json`
- **Migration Status**: Tooling ready (`scripts/qdrant_activation.py`). Data write migration pending manual cloud execution.

---

## 4. Neo4j Aura Migration

- **Cloud Connection**: Verified via GitHub Actions run `#30414786770` connecting to `neo4j+s://64a945c7.databases.neo4j.io`.
- **Cloud Database Status**:
  - Database: `64a945c7`
  - Total Nodes: **0**
  - Total Relationships: **0**
  - Schema Indexes: 2 lookup indexes online (`NODE` and `RELATIONSHIP`)
  - Report: `artifacts/production_activation/neo4j/cloud-inventory.json`
- **Migration Status**: Tooling ready (`scripts/neo4j_activation.py`). Graph data write migration pending manual cloud execution.

---

## 5. Cloud Run Staging

- **Target Service**: `company-graphrag-staging`
- **Region**: `europe-west1`
- **Deployment Script**: `scripts/deploy_cloud_run.sh`
- **Deployment Workflow**: `.github/workflows/deploy-cloud-run.yml`
- **Status**: `BLOCKED_EXTERNAL_DEPENDENCY` (Requires GCP Workload Identity Provider authentication and Service Account authorization on Google Cloud Platform).

---

## 6. Observability

- **Tracing & Telemetry**: OpenTelemetry OTLP exporter and Opik SDK integrated (`src/company_graphrag/agents/observability/tracer.py`).
- **Staging Configured Variables**:
  - `OPIK_WORKSPACE`: `ceylanal`
  - `OTEL_EXPORTER_OTLP_ENDPOINT`: `https://otlp-gateway-prod-eu-west-2.grafana.net/otlp`
- **Status**: `BLOCKED_EXTERNAL_DEPENDENCY` (Live trace delivery requires active Cloud Run staging revision processing requests with Secret Manager secrets).

---

## 7. Staging Eval Baseline

- **Local Eval Suite**: Passed 9/9 representative evaluation metrics (`artifacts/evaluation/eval_report.json`).
- **Staging Eval Status**: `BLOCKED_EXTERNAL_DEPENDENCY` (Requires live Cloud Run staging HTTP endpoint).

---

## 8. Locust Load Baseline

- **Local Benchmark**: Standalone container load test passed (30 requests, 0 failures, median 4 ms, p95 71 ms).
- **Staging Load Status**: `BLOCKED_EXTERNAL_DEPENDENCY` (Locust scenario `scratch/locustfile.py` requires live Cloud Run staging URL).

---

## 9. Backup–Restore

- **Rehearsal Verification**: GitHub Actions workflow `.github/workflows/backup-verify.yml` executed and verified database inventory contract against Qdrant Cloud and Neo4j Aura.
- **Runbooks**:
  - `docs/runbooks/qdrant-backup-restore.md`
  - `docs/runbooks/neo4j-backup-restore.md`

---

## 10. Rollback Rehearsal

- **Rollback Script**: `scripts/rollback_cloud_run.sh`
- **Runbook**: `docs/runbooks/rollback.md`
- **Rehearsal Status**: `BLOCKED_EXTERNAL_DEPENDENCY` (Requires at least two active revisions deployed to Cloud Run service).

---

## 11. External Blockers

1. **Qdrant Cloud Data Migration**: Local 25,859 points collection needs to be upserted to `company_documents_staging`.
2. **Neo4j Aura Graph Ingestion**: Source graph nodes and relationships need to be created on Aura instance `64a945c7.databases.neo4j.io`.
3. **GCP Cloud Run Service Account & WIF**: Deployment requires GCP IAM permissions to deploy revision to Cloud Run.
4. **Secret Manager Secrets**: `company-graphrag-api-key`, `company-graphrag-llm-key`, `company-graphrag-qdrant-key`, `company-graphrag-neo4j-password`, `company-graphrag-opik-key`, and `company-graphrag-otel-headers` must be active in Secret Manager.

---

## 12. Manual Actions

Execute the following commands to complete cloud database migration and staging deployment:

```bash
# 1. Qdrant Cloud Data Migration (Upload 25,859 points)
uv run python scripts/qdrant_activation.py migrate \
  --source-path data/vector_store/qdrant_db \
  --source-collection company_documents \
  --target-url "$QDRANT_URL" \
  --target-collection company_documents_staging \
  --target-api-key-env QDRANT_API_KEY \
  --execute \
  --output artifacts/production_activation/qdrant/cloud-migration-result.json

# 2. Trigger Cloud Run Staging Deployment Workflow
gh workflow run deploy-cloud-run.yml \
  -f image_digest=sha256:d13134d91ad3e0168ca46012f9264549e0e67ac8b41dd7c21e9f50c4e7d914fa \
  -f execute=true \
  --ref codex/configure-staging-runtime-identity

# 3. Run Staging Smoke Checks
uv run python scripts/staging_smoke.py \
  --base-url "https://company-graphrag-staging-xxxxxxxx-ew.a.run.app" \
  --output artifacts/production_activation/staging/smoke.json

# 4. Rollback Rehearsal (Traffic Shifting)
GCP_PROJECT_ID="project-7db8afc0-2c35-49c8-a17" \
GCP_REGION="europe-west1" \
CLOUD_RUN_SERVICE="company-graphrag-staging" \
TARGET_REVISION="company-graphrag-staging-previous" \
./scripts/rollback_cloud_run.sh
```

---

## 13. Final Decision

```text
STAGING_ACTIVATION_BLOCKED
PRODUCTION_ACTIVATION_BLOCKED
```

*Note: Code readiness, Docker image packaging, Cosign signing, and GitHub Actions workflow verifications are 100% complete. Cloud database data population and Cloud Run staging service deployment remain blocked by external cloud execution requirements.*
