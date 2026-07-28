# Staging Deployment Runbook

## Fresh clone and local core

```bash
cp .env.example .env
uv sync --frozen
make check version-check compose-config docker-build
docker compose --profile core up -d
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
curl --fail http://127.0.0.1:8000/version
```

Core starts API (1 GiB), Qdrant (1 GiB), and Neo4j (2 GiB). Observability and load-test profiles are off. Cloud Qdrant/Aura use the same environment keys with TLS URLs and runtime-injected credentials. No data is recreated.

## Cloud Run staging

The deployment workflow requires GitHub environment approval, OIDC federation, an immutable image digest, Artifact Registry mirror coordinates, and Secret Manager entries. Guardrails: min instances 0, max 1, concurrency 4, 300-second timeout, 1 CPU, 1 GiB, request size limit, API key, and authenticated invocation.

Cloud Run deploys Artifact Registry images. Mirror the signed GHCR digest without rebuilding, verify source and destination digests match, then set `ARTIFACT_REGISTRY_IMAGE` to the destination repository path. Required settings:

- GitHub secrets: `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`
- GitHub variables: `GCP_PROJECT_ID`, `GCP_REGION`, `CLOUD_RUN_SERVICE`, `ARTIFACT_REGISTRY_IMAGE`
- Secret Manager: `company-graphrag-api-key`, optional provider key
- Runtime: Qdrant Cloud URL/key, Neo4j Aura URI/user/password, optional Grafana/Opik values

No cloud resource or deployment is created by repository validation.

The regular CI suite excludes the three legacy tests that require the ignored 25,859-point embedded developer store. The container job separately starts clean Qdrant/Neo4j service containers and verifies readiness plus dependency-failure behavior. A developer with the local store still runs the complete `uv run pytest` suite.

## Smoke

Run liveness, readiness, version/config hash, a vector question, graph question, hybrid research, and citation check. Confirm logs share `request_id`, `run_id`, and `trace_id`. Telemetry verification is only PASS when the user’s Grafana/Opik accounts show the trace.
