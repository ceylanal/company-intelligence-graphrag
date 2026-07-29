#!/usr/bin/env sh
set -eu

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
: "${GCP_REGION:?GCP_REGION is required}"
: "${GCP_SERVICE_ACCOUNT:?GCP_SERVICE_ACCOUNT is required}"
: "${CLOUD_RUN_SERVICE:?CLOUD_RUN_SERVICE is required}"
: "${ARTIFACT_REGISTRY_IMAGE:?ARTIFACT_REGISTRY_IMAGE is required}"
: "${IMAGE_DIGEST:?IMAGE_DIGEST is required}"
: "${QDRANT_URL:?QDRANT_URL is required}"
: "${QDRANT_COLLECTION_NAME:?QDRANT_COLLECTION_NAME is required}"
: "${NEO4J_URI:?NEO4J_URI is required}"
: "${NEO4J_USERNAME:?NEO4J_USERNAME is required}"
: "${NEO4J_DATABASE:=neo4j}"
: "${LLM_PROVIDER:=mock}"
: "${LLM_MODEL:=mock-v1}"
: "${OPIK_WORKSPACE:?OPIK_WORKSPACE is required}"
: "${OTEL_EXPORTER_OTLP_ENDPOINT:?OTEL_EXPORTER_OTLP_ENDPOINT is required}"
: "${CLOUD_RUN_MEMORY:=2Gi}"

case "$IMAGE_DIGEST" in
  sha256:*) ;;
  *) echo "IMAGE_DIGEST must start with sha256:" >&2; exit 2 ;;
esac

image="${ARTIFACT_REGISTRY_IMAGE}@${IMAGE_DIGEST}"
digest_prefix="$(printf '%s' "${IMAGE_DIGEST#sha256:}" | cut -c1-12)"
revision_suffix="sha-${digest_prefix}"
if [ -n "${GITHUB_RUN_ID:-}" ]; then
  run_suffix="$(printf '%s' "$GITHUB_RUN_ID" | tail -c 8)"
  revision_suffix="sha-$(printf '%s' "$digest_prefix" | cut -c1-8)-run-${run_suffix}"
fi

gcloud run deploy "$CLOUD_RUN_SERVICE" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --service-account "$GCP_SERVICE_ACCOUNT" \
  --image "$image" \
  --revision-suffix "$revision_suffix" \
  --execution-environment gen2 \
  --min-instances 0 \
  --max-instances 1 \
  --concurrency 4 \
  --timeout 300 \
  --cpu 1 \
  --memory "$CLOUD_RUN_MEMORY" \
  --cpu-throttling \
  --ingress all \
  --no-allow-unauthenticated \
  --set-env-vars "ENVIRONMENT=staging,CHECKPOINT_DIR=/tmp/company-graphrag/checkpoints,QDRANT_USE_CLOUD=true,QDRANT_URL=${QDRANT_URL},QDRANT_COLLECTION_NAME=${QDRANT_COLLECTION_NAME},NEO4J_USE_CLOUD=true,NEO4J_URI=${NEO4J_URI},NEO4J_USERNAME=${NEO4J_USERNAME},NEO4J_DATABASE=${NEO4J_DATABASE},LLM_PROVIDER=${LLM_PROVIDER},LLM_MODEL=${LLM_MODEL},TELEMETRY_ENABLED=true,TELEMETRY_EXPORTER=otlp,OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT},OPIK_ENABLED=true,OPIK_WORKSPACE=${OPIK_WORKSPACE},TELEMETRY_CAPTURE_PROMPTS=false" \
  --set-secrets "API_KEY=company-graphrag-api-key:latest,LLM_API_KEY=company-graphrag-llm-key:latest,QDRANT_API_KEY=company-graphrag-qdrant-key:latest,NEO4J_PASSWORD=company-graphrag-neo4j-password:latest,OPIK_API_KEY=company-graphrag-opik-key:latest,OTEL_EXPORTER_OTLP_HEADERS=company-graphrag-otel-headers:latest"

# Keep the staging service private while allowing the dedicated deployer identity
# to run authenticated smoke and rollback verification.
gcloud run services add-iam-policy-binding "$CLOUD_RUN_SERVICE" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --member "serviceAccount:${GCP_SERVICE_ACCOUNT}" \
  --role "roles/run.invoker" \
  --quiet >/dev/null
