# Staging frontend deployment report

## Deployment

| Item | Value |
| --- | --- |
| Vercel staging URL | `https://company-intelligence-graphrag-stagi.vercel.app` |
| Deployment URL | `https://company-intelligence-graphrag-staging-gm0udcz4f.vercel.app` |
| Cloud Run backend | `https://company-graphrag-staging-c6oeawtcxq-ew.a.run.app` |
| Vercel project | `ascs-projects-740622ac/company-intelligence-graphrag-staging` |
| Framework / root | Next.js / `frontend` |
| Deployment target | Vercel Production (the dedicated project is the staging environment) |

`NEXT_PUBLIC_API_BASE_URL` is configured in the Vercel project for Preview and
Production. Its value is the Cloud Run URL above. It is a public service URL only;
no credential, token, provider key, or secret is stored in a `NEXT_PUBLIC_*`
variable.

## CORS configuration

FastAPI already uses the environment-driven exact-origin allow-list
`CORS_ALLOWED_ORIGINS`; it does not use a wildcard. The staging contract is:

```text
http://localhost:3000,https://company-intelligence-graphrag-stagi.vercel.app
```

The root `.env.example` records that contract. Applying it to the existing Cloud
Run service requires an authorized update of that service's runtime environment.
No new backend was created or deployed.

## Checks completed

| Command / check | Result |
| --- | --- |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm run build` | PASS |
| `npm run test` | PASS — 2 files, 3 tests |
| `npm audit --omit=dev --audit-level=high` | PASS — 0 vulnerabilities |
| `uv run pytest tests/test_api.py tests/test_config.py` | PASS — 16 tests |
| `uv run ruff check src/company_graphrag/api/app.py src/company_graphrag/config.py tests/test_api.py` | PASS |
| `uv run mypy src` | PASS — 128 source files |
| `npx vercel deploy --prod --yes` | PASS — deployment ready |
| Frontend HTTP request through authenticated Vercel CLI | PASS — HTTP 200 |
| Anonymous Cloud Run `/health/ready` | BLOCKED — HTTP 403 |
| `PLAYWRIGHT_BASE_URL=<deployment-url> npm run test:e2e` | BLOCKED — all 18 browser cases reach Vercel sign-in rather than the application |

`PLAYWRIGHT_BASE_URL=<deployed-url> npm run test:e2e` now targets an already
deployed frontend and does not start the local dev server. This is the required
command once browser access is enabled.

## Acceptance-test evidence and limitations

The deployed frontend is protected by Vercel deployment protection; an unauthenticated
browser is redirected to Vercel sign-in before application JavaScript loads. In
addition, the existing Cloud Run staging service is private: direct anonymous requests
to `/health/ready` return HTTP 403. Consequently, these real-backend checks cannot
yet be truthfully marked as passed:

- visible backend health, research HTTP 200, NDJSON events and step updates;
- citations/evidence and PDF-source route; graph context;
- cancellation, safety-refusal and insufficient-evidence UI states;
- desktop/tablet/mobile interaction, hard refresh and browser-console checks;
- staging telemetry trace verification.

No frontend LLM-provider calls were found in the source audit. The browser E2E suite
also explicitly asserts that no OpenAI, Anthropic, Gemini, or Google Generative
Language request is made.

## Required external follow-up

1. Grant browser access to the protected Vercel staging deployment (or explicitly
   make this dedicated staging project publicly viewable).
2. Provide an authorized browser-callable path to the existing private Cloud Run
   service. A browser cannot attach Google IAM identity tokens to direct cross-origin
   fetches. This normally means a suitable authenticated gateway/BFF, or an explicit
   staging IAM decision.
3. Apply the exact `CORS_ALLOWED_ORIGINS` value above to the existing Cloud Run
   service, then rerun the deployed Playwright command and telemetry verification.

No backend, credential rotation, custom domain, or LLM-provider integration was
created as part of this frontend deployment.
