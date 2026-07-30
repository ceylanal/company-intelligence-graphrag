#!/usr/bin/env bash
set -euo pipefail

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
: "${GCP_REGION:?GCP_REGION is required}"
: "${CLOUD_RUN_SERVICE:?CLOUD_RUN_SERVICE is required}"

readonly VERCEL_TEAM_ID="team_qNUQ6N3WoZ7DfOP21idJFfqy"
readonly VERCEL_PROJECT_ID="prj_nUnGou9ZPk2PArkYYjKJ0zKjm3rA"
readonly VERCEL_ISSUER="https://oidc.vercel.com/ascs-projects-740622ac"
readonly VERCEL_AUDIENCE="https://vercel.com/ascs-projects-740622ac"
readonly POOL_ID="vercel-staging"
readonly PROVIDER_ID="vercel-staging"
readonly SERVICE_ACCOUNT_ID="company-graphrag-vercel-staging-invoker"

PROJECT_NUMBER="$(gcloud projects describe "$GCP_PROJECT_ID" --format='value(projectNumber)')"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_ID}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
SUBJECT="owner:${VERCEL_TEAM_ID}:project:${VERCEL_PROJECT_ID}:environment:production"
POOL_RESOURCE="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}"

if ! gcloud iam workload-identity-pools describe "$POOL_ID" --project "$GCP_PROJECT_ID" --location global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$POOL_ID" \
    --project "$GCP_PROJECT_ID" \
    --location global \
    --display-name "Vercel staging federation"
fi

if ! gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" --project "$GCP_PROJECT_ID" --location global --workload-identity-pool "$POOL_ID" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
    --project "$GCP_PROJECT_ID" \
    --location global \
    --workload-identity-pool "$POOL_ID" \
    --display-name "Vercel staging production" \
    --issuer-uri "$VERCEL_ISSUER" \
    --allowed-audiences "$VERCEL_AUDIENCE" \
    --attribute-mapping "google.subject=assertion.sub" \
    --attribute-condition "assertion.sub == '$SUBJECT' && assertion.owner_id == '$VERCEL_TEAM_ID' && assertion.project_id == '$VERCEL_PROJECT_ID' && assertion.environment == 'production' && assertion.aud == '$VERCEL_AUDIENCE'"
fi

if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_ID" \
    --project "$GCP_PROJECT_ID" \
    --display-name "Vercel staging Cloud Run invoker"
fi

gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT_EMAIL" \
  --project "$GCP_PROJECT_ID" \
  --role roles/iam.workloadIdentityUser \
  --member "principal://iam.googleapis.com/${POOL_RESOURCE}/subject/${SUBJECT}" \
  --quiet

gcloud run services add-iam-policy-binding "$CLOUD_RUN_SERVICE" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --role roles/run.invoker \
  --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --quiet

printf 'project_number=%s\n' "$PROJECT_NUMBER" >> "$GITHUB_OUTPUT"
printf 'service_account_email=%s\n' "$SERVICE_ACCOUNT_EMAIL" >> "$GITHUB_OUTPUT"
printf 'pool_id=%s\nprovider_id=%s\n' "$POOL_ID" "$PROVIDER_ID" >> "$GITHUB_OUTPUT"
