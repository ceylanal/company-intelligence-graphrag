# Production Activation Plan

## Current decision

`PRODUCTION_ACTIVATION_BLOCKED`

The local release candidate is healthy, but external activation prerequisites are not configured. No cloud resource, package, signature, staging revision, or production revision is claimed.

## Verified starting point

- Repository: `ceylanal/company-intelligence-graphrag`
- Branch: `main`
- Base commit: `179310c02dec8b3f3cd46bf03ab9a8ef544b1089`
- Application: `0.1.0`
- Prompt bundle: `1.0.0`
- Workflow: `1.0.0`
- Config hash: `0c39f6471caa369668c46f391ef3bd472c6345fb0042bc12943f2d35cd9c4880`
- Local Qdrant collection: `company_documents`, 25,859 points, 384-dimensional cosine vectors
- Available local graph audit: 0 nodes and 0 relationships
- GitHub access: repository administrator, but no Actions secrets, variables, environments, workflow runs, or branch protection are configured

## Activation sequence

1. Commit the current release candidate on a `codex/` branch and open a pull request.
2. Run the real PR workflows and fix all quality/security failures.
3. Configure GitHub `staging` and `production` environments. Production requires manual approval.
4. Add the variables and secrets listed in `config/production_activation.yaml`.
5. Publish a multi-platform GHCR image using immutable SHA and semantic-version tags.
6. Verify Trivy, SBOM, provenance, keyless Cosign signature, and image digest.
7. Inventory and migrate Qdrant to `company_documents_staging`; compare count, schema, samples, and checksum.
8. Recover or generate a non-empty source graph before Aura migration. Inventory and compare it with Aura.
9. Verify real Opik and Grafana Cloud delivery with secret-leak checks.
10. Deploy the signed digest to Cloud Run staging with min 0/max 1.
11. Run bounded smoke, eval, and Locust suites; record a staging baseline.
12. Rehearse backup/restore and revision rollback.
13. Produce a release-candidate report.
14. Stop for explicit production approval.
15. Promote the exact staging-tested digest, then run production smoke and E2E checks.

## Hard gates

Production remains blocked if any of these are absent: successful GitHub run, GHCR digest, verified signature, Qdrant integrity, non-empty Neo4j integrity, staging smoke, telemetry evidence, eval baseline, backup/restore evidence, or rollback evidence.

## Cost guardrails

- Cloud Run min instances: 0
- Cloud Run max instances: 1
- Concurrency: 4
- Timeout: 300 seconds
- CPU throttling enabled
- Real LLM tests: bounded, explicit, and disabled in normal PR CI
- Staging and production databases, collections, telemetry projects, and secrets remain separate

## Evidence locations

All machine-readable evidence belongs under `artifacts/production_activation/`. Secret values, authorization headers, document bodies, and full prompts must not be stored there.
