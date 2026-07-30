# Staging frontend deployment report

## Current deployment

| Item | Value |
| --- | --- |
| Public staging URL | `https://company-intelligence-graphrag-stagi.vercel.app` |
| Latest application deployment | `https://company-intelligence-graphrag-staging-lcw3121ft.vercel.app` |
| Private Cloud Run URL | `https://company-graphrag-staging-c6oeawtcxq-ew.a.run.app` |
| Vercel project | `ascs-projects-740622ac/company-intelligence-graphrag-staging` |
| Framework / root directory | Next.js / `frontend` |
| Branch / commits | `codex/vercel-staging-frontend` / `c21aae0`, `f302fb3` |

The Vercel project uses production-domain access with preview-only deployment
protection. The public staging URL returns HTTP 200 without a Vercel login. Preview
deployments remain protected. `NEXT_PUBLIC_API_BASE_URL` was removed from both
Vercel environments; the browser now always requests the same-origin `/api/*` BFF.

## Private-backend and OIDC/WIF design

The browser path is:

```text
Browser -> Vercel /api/* route handler -> Google STS -> IAM Credentials -> private Cloud Run
```

The route handler obtains the Vercel-provided request OIDC token server-side,
exchanges it with Google Security Token Service, generates a Cloud Run ID token for
the exact service URL, and streams the upstream response unchanged. It forwards
only required request headers and a response-header allow-list, supports ranges and
binary PDF responses, never exposes an identity token to the browser, and never
logs credentials. Client disconnects abort the upstream fetch.

The intended WIF resources are deliberately narrow:

| Resource | Intended restriction |
| --- | --- |
| Pool / provider | `vercel-staging` / `vercel-staging`, issuer `https://oidc.vercel.com/ascs-projects-740622ac` |
| Provider condition | Exact Vercel team `team_qNUQ6N3WoZ7DfOP21idJFfqy`, project `prj_nUnGou9ZPk2PArkYYjKJ0zKjm3rA`, production environment, subject, and audience |
| Service account | `company-graphrag-vercel-staging-invoker@PROJECT_ID.iam.gserviceaccount.com` |
| Cloud Run IAM | `roles/run.invoker` on `company-graphrag-staging` only |

No `allUsers` invoker binding was added, no Cloud Run deployment was created, and no
service-account key, OIDC token, IAM token, or provider credential was added to the
repository or a `NEXT_PUBLIC_*` variable. This follows the current
[Vercel OIDC GCP configuration](https://vercel.com/docs/oidc/gcp) and
[Cloud Run service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service)
guidance.

## Environment configuration

Configured server-only Vercel variable names (values redacted where not yet
available):

```text
CLOUD_RUN_STAGING_URL
GCP_PROJECT_NUMBER
GCP_WORKLOAD_IDENTITY_POOL_ID
GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID
GCP_SERVICE_ACCOUNT_EMAIL
PROXY_CONNECT_TIMEOUT_MS
```

`CLOUD_RUN_STAGING_URL` is configured for Production and Preview. The remaining
federation identifiers cannot be configured until the WIF resources exist. The
checked-in `frontend/.env.example` contains only an endpoint and identifiers, never
credential material.

FastAPI retains its environment-based exact-origin allow-list (`CORS_ALLOWED_ORIGINS`)
with the staging contract:

```text
http://localhost:3000,https://company-intelligence-graphrag-stagi.vercel.app
```

The BFF makes the production browser path same-origin, so Cloud Run CORS is not used
by the browser. No wildcard CORS configuration was introduced.

## Verification and quality gates

| Command / check | Result |
| --- | --- |
| `curl -I <public-staging-url>` | PASS — HTTP 200 without Vercel login |
| Browser navigation and hard refresh of public staging URL | PASS — application renders |
| Anonymous Cloud Run `/health/ready` | PASS — HTTP 403, remains private |
| Same-origin `/api/health/live` | BLOCKED — HTTP 503 until WIF identifiers are configured |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm run build` | PASS — dynamic `/api/[...path]` route emitted |
| `npm run test` | PASS — 3 files, 4 tests |
| `npm audit --omit=dev --audit-level=high` | PASS — 0 vulnerabilities |
| `PLAYWRIGHT_BASE_URL=<public-staging-url> npm run test:e2e` | PASS — 18/18 desktop, tablet, and mobile fixture tests |
| `uv run pytest tests/test_api.py tests/test_config.py` | PASS — 16 tests |
| `uv run ruff check .` | PASS |
| `uv run mypy src` | PASS — 128 source files, no errors |
| Frontend static-bundle scan for Cloud Run URLs, public API-base variable, and LLM provider URLs | PASS — no matches |

The deployed Playwright suite verifies responsive layouts, same-origin request URLs,
NDJSON UI handling, research-stage updates, evidence panel behavior, cancellation,
safety refusal, and insufficient-evidence rendering with deterministic route fixtures.
It cannot substitute for the remaining real private-backend acceptance test.

## Remaining IAM blocker and exact follow-up

Workflow run `30512714427` successfully authenticated the existing GitHub staging
deployer and ran the non-deploy safety validation. Its WIF job then stopped at the
first intended write with:

```text
PERMISSION_DENIED: iam.workloadIdentityPools.create
```

This confirms the current deployer does not have federation-administration access;
it did not change WIF, Cloud Run IAM, or Cloud Run deployment state. A GCP IAM
administrator must either run `scripts/configure_vercel_wif.sh` with the required
environment variables or grant the bootstrap identity only the temporary ability to:

1. create/manage the named WIF pool and provider;
2. create the dedicated invoker service account and its WIF impersonation binding;
3. set `roles/run.invoker` on only `company-graphrag-staging` in `europe-west1`.

After that approval, rerun `Deploy Cloud Run Staging` on this branch with
`execute=false` and `configure_vercel_wif=true`, configure the four resulting
server-only identifiers in Vercel, redeploy, and run the real (unmocked) acceptance
cases: health, research HTTP 200 / progressive NDJSON, citation and PDF routes,
graph context, cancellation, safety and insufficient-evidence states, console audit,
and staging telemetry trace. Until then those real-backend checks are intentionally
not reported as passing.
