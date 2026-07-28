# Staging Deployment Runbook

1. Confirm successful required GitHub checks and obtain the signed GHCR digest.
2. Verify it:

   ```bash
   cosign verify \
     --certificate-identity-regexp '^https://github.com/ceylanal/company-intelligence-graphrag/' \
     --certificate-oidc-issuer https://token.actions.githubusercontent.com \
     ghcr.io/ceylanal/company-intelligence-graphrag@sha256:...
   ```

3. Mirror the exact digest into Artifact Registry without rebuilding and confirm source/destination digests match.
4. Confirm Qdrant and Aura inventories pass.
5. Configure the `staging` GitHub environment using the names in `config/production_activation.yaml`.
6. Dispatch `deploy-cloud-run.yml` with the immutable digest and `execute=true`.
7. Record service URL, revision, digest, and deployment time.
8. Run:

   ```bash
   API_KEY=... uv run python scripts/staging_smoke.py \
     --base-url https://STAGING_URL \
     --output artifacts/production_activation/staging/smoke.json
   ```

9. Verify Opik trace and Grafana metrics/logs/traces before accepting staging.

The deployment script enforces min 0, max 1, concurrency 4, 300-second timeout, 1 CPU, 1 GiB memory, CPU throttling, and authenticated ingress.
