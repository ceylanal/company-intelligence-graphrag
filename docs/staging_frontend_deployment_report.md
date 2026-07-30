# Staging frontend deployment report

## Current deployment

| Item | Value |
| --- | --- |
| Public staging URL | `https://company-intelligence-graphrag-stagi.vercel.app` |
| Latest application deployment | `https://company-intelligence-graphrag-staging-3lpk2cg0k.vercel.app` |
| Private Cloud Run URL | `https://company-graphrag-staging-77096651349.europe-west1.run.app` |
| Vercel project | `ascs-projects-740622ac/company-intelligence-graphrag-staging` |
| Framework / root directory | Next.js / `frontend` |
| Branch / current BFF commit | `codex/vercel-staging-frontend` / `12ffe8d` |

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
| Service account | `graphrag-vercel-stg-invoker@project-7db8afc0-2c35-49c8-a17.iam.gserviceaccount.com` |
| Cloud Run IAM | `roles/run.invoker` on `company-graphrag-staging` only |

No `allUsers` invoker binding was added, no Cloud Run deployment was created, and no
service-account key, OIDC token, IAM token, or provider credential was added to the
repository or a `NEXT_PUBLIC_*` variable. This follows the current
[Vercel OIDC GCP configuration](https://vercel.com/docs/oidc/gcp) and
[Cloud Run service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service)
guidance.

## Environment configuration

Configured Production server-only Vercel variable names (values redacted):

```text
CLOUD_RUN_STAGING_URL
GCP_PROJECT_NUMBER
GCP_WORKLOAD_IDENTITY_POOL_ID
GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID
GCP_SERVICE_ACCOUNT_EMAIL
PROXY_CONNECT_TIMEOUT_MS
BACKEND_API_KEY
```

The first six names above are configured for Vercel Production. `BACKEND_API_KEY`
is intentionally not configured yet: it must be stored as a Vercel Sensitive
server-side value, never placed in source or a `NEXT_PUBLIC_*` variable. Vercel supplies
`VERCEL_OIDC_TOKEN` automatically to the function runtime and it is not stored as a
project variable. The checked-in `frontend/.env.example` contains only an endpoint
and identifiers, never credential material.

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
| Same-origin `/api/health/live` | PASS — HTTP 200, `{"status":"live","environment":"staging"}` |
| Anonymous private Cloud Run `/health/live` | PASS — HTTP 403 |
| Same-origin real `/api/research` | PASS — HTTP 200 in 8.62s; grounded ASELSAN response, 10 cited source chunks, and OTEL trace ID returned |
| Browser health status | PASS — public staging UI displays `Backend ready` after hard refresh |
| Browser research interaction | BLOCKED — frontend calls `/api/research/stream`, but the deployed backend returns HTTP 404 |
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

The WIF provider, exact Vercel subject binding, and service-scoped Cloud Run invoker
binding were successfully reconciled. The active subject is:

```text
owner:ascs-projects-740622ac:project:company-intelligence-graphrag-staging:environment:production
```

The bootstrap script now uses the Vercel team slug and project slug in the exact
subject, updates existing providers, and removes obsolete bindings. It does not make
Cloud Run public or create a key.

The existing application API key is configured as Vercel Production **Sensitive**
variable `BACKEND_API_KEY`; the BFF forwards it only to the private backend as
`X-API-Key`.

## Deployed-backend contract limitation

The authoritative deployed `GET /openapi.json`, read through the authenticated BFF,
lists only `/health/live`, `/health/ready`, and non-streaming `POST /research`.
It does not publish `/research/stream`, company/comparison, citation/source/PDF, or
graph-context routes. The real `/research` response contains grounded source entries
in its answer text and telemetry metadata, but it is one JSON document rather than
NDJSON. Consequently the existing frontend cannot receive progressive workflow
events or open structured citation/PDF/graph routes from this backend revision.

The BFF intentionally does not synthesize or buffer fake NDJSON because that would
violate the streaming requirement. Completing those browser acceptance cases requires
the existing Cloud Run service to expose the frontend’s streaming/source/graph API
contract; no backend deployment was performed in this work.
