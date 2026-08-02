# Staging frontend deployment report

## Current deployment

| Item | Value |
| --- | --- |
| Public staging URL | `https://company-intelligence-graphrag-stagi.vercel.app` |
| Latest application deployment | `https://company-intelligence-graphrag-staging-3lpk2cg0k.vercel.app` |
| Private Cloud Run URL | `https://company-graphrag-staging-77096651349.europe-west1.run.app` |
| Vercel project | `ascs-projects-740622ac/company-intelligence-graphrag-staging` |
| Framework / root directory | Next.js / `frontend` |
| Branch | `codex/vercel-staging-frontend` |
| Latest backend commit (pushed) | `dc147dd` feat(api): expose streaming, companies, citation, and PDF routes |
| Test commit (pushed) | `a289fa7` test(api): add contract, streaming, citation, PDF, and auth tests |

## Root cause of missing routes

The deployed Cloud Run revision was built from an earlier commit that predated
the addition of the streaming and citation routes. The remote branch contained
a stripped `research.py` with only `POST /research` (non-streaming). The
following routes existed locally but had never been committed or deployed:

| Route | Status before this fix |
|---|---|
| `POST /research/stream` | ❌ Not in deployed image → HTTP 404 |
| `GET /research/companies` | ❌ Not in deployed image → HTTP 404 |
| `GET /research/{run_id}/sources/{idx}` | ❌ Not in deployed image → HTTP 404 |
| `GET /research/{run_id}/sources/{idx}/document` | ❌ Not in deployed image → HTTP 404 |

These routes are now committed and pushed. A new Cloud Run revision must be
built and deployed to make them live.

## Route implementation summary

All routes reuse existing domain services with no duplicated research logic:

**`POST /research/stream`** — Real progressive NDJSON from the existing
`ResearchWorkflow`. Polls the `JSONCheckpointSaver` checkpoint every 100 ms
while the workflow runs in a thread, emitting `stage` events as
`current_stage` changes. After completion emits `evidence`, `citations`,
`metrics`, `answer_delta` chunks (512 bytes each), and `complete`. Safety
controls (input + output guardrails) are applied identically to the
non-streaming endpoint. Never buffers the complete response.

**`GET /research/companies`** — Reads `config/companies.yaml` at request
time. No live market data. Graph context, company profile, and comparison
data are surfaced through the research answer and `plan.is_comparison` field
— no dedicated graph-context or comparison endpoint exists in the frontend
contract.

**`GET /research/{run_id}/sources/{idx}`** — Loads a durable JSON checkpoint
from `settings.checkpoint_dir`, finds the citation by `citation_index`,
matches it to the evidence item, and returns a `SourceDetail` including
`relevance_score`, `citation_status`, `graph_path`, `document_available`,
and `document_url`.

**`GET /research/{run_id}/sources/{idx}/document`** — Serves the source PDF
via Starlette `FileResponse`, which natively handles `Accept-Ranges` and HTTP
`Range` requests. Path traversal is prevented by requiring the filename to be
a plain basename ending in `.pdf` and resolving it under trusted roots only
(`data/raw`, `data/archive`).

## Private-backend and OIDC/WIF design

_Unchanged from previous report — see WIF section below._

The browser path is:

```text
Browser → Vercel /api/* route handler → Google STS → IAM Credentials → private Cloud Run
```

| Resource | Intended restriction |
| --- | --- |
| Pool / provider | `vercel-staging` / `vercel-staging`, issuer `https://oidc.vercel.com/ascs-projects-740622ac` |
| Provider condition | Exact Vercel team `team_qNUQ6N3WoZ7DfOP21idJFfqy`, project `prj_nUnGou9ZPk2PArkYYjKJ0zKjm3rA`, production environment |
| Service account | `graphrag-vercel-stg-invoker@project-7db8afc0-2c35-49c8-a17.iam.gserviceaccount.com` |
| Cloud Run IAM | `roles/run.invoker` on `company-graphrag-staging` only |

## Environment configuration (unchanged)

```text
CLOUD_RUN_STAGING_URL
GCP_PROJECT_NUMBER
GCP_WORKLOAD_IDENTITY_POOL_ID
GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID
GCP_SERVICE_ACCOUNT_EMAIL
PROXY_CONNECT_TIMEOUT_MS
BACKEND_API_KEY
```

## Quality gates — local results (pre-deployment)

| Command / check | Result |
| --- | --- |
| `uv run ruff check .` | PASS — 0 issues |
| `uv run mypy src` | PASS — 128 source files, no errors |
| `uv run pytest tests/test_api.py -v` | PASS — 45/45 tests |
| Full pytest suite (excluding lineage/rag-gen/rag-pipeline) | PASS — all dots, 0 failures |
| Docker container build | DEFERRED — Docker daemon not running locally; CI release.yml will build |
| Container smoke test | DEFERRED — will run in CI |

## New contract tests added (tests/test_api.py)

| Test group | Count | What is verified |
|---|---|---|
| OpenAPI schema | 5 | All 5 required routes in `/openapi.json` |
| `GET /research/companies` | 2 | Array shape, required fields, no market data |
| `POST /research/stream` events | 10 | accepted-first, complete-last, delta reconstruction, graph_path, safety events, error/conflict codes, NDJSON type, cache-control |
| `GET /research/{run_id}/sources/{idx}` | 4 | Citation detail fields, relevance_score, 404 on missing run/index |
| `GET /.../document` | 3 | 404 no PDF, 200 application/pdf, 404 missing run |
| `POST /research` (non-streaming) | 4 | Shape, trace_id in metadata, 503 on error, 409 on conflict |
| API key middleware | 4 | 401 wrong, 401 missing, 200 correct, health exempt |
| Request size | 1 | 413 on oversized body |
| **Total new** | **33** | |

## Deployment steps required (awaiting authorization)

### Step 4 — Build and push image

Trigger `release.yml` with `publish: true` on the `codex/vercel-staging-frontend`
branch (or merge to `main` first). This runs all quality gates, builds a
multi-platform image, signs it with keyless Cosign, and publishes to GHCR.
Copy the resulting `sha256:...` digest.

### Step 5 — Deploy new Cloud Run revision

Trigger `deploy-cloud-run.yml` with:
- `image_digest`: the `sha256:...` from Step 4
- `execute`: `true`
- `configure_vercel_wif`: `false`

The workflow runs the safety red-team gate, validates the digest, deploys a
new revision pinned to that digest with `--no-allow-unauthenticated`, runs the
staging smoke test, staging evaluation baseline (18 samples), and bounded
load test (1/5/10 users × 20 s).

## Post-deployment verification checklist

| Check | Expected |
|---|---|
| Anonymous `GET /health/live` direct to Cloud Run | HTTP 403 |
| Authenticated `GET /health/live` | HTTP 200, `{"status":"live","environment":"staging"}` |
| Authenticated `GET /openapi.json` | HTTP 200, paths include `/research/stream`, `/research/companies`, `/research/{run_id}/sources/{citation_index}`, `/research/{run_id}/sources/{citation_index}/document` |
| Same-origin Vercel `GET /api/health/live` | HTTP 200 |
| Same-origin `POST /api/research/stream` | HTTP 200, `content-type: application/x-ndjson`, progressive events |
| Research stages update progressively | PLANNING → RESEARCH_EXECUTION → VERIFICATION → COMPLETED visible in UI |
| Citations panel loads real evidence | `citation_status: verified`, `graph_path` rendered in `<details>` |
| `GET /api/research/{run_id}/sources/{idx}` | HTTP 200, SourceDetail with citation fields |
| PDF link when document available | HTTP 200 `application/pdf`, `Accept-Ranges: bytes` |
| Cancellation propagates | Abort closes upstream Cloud Run connection |
| Safety refusal renders | HTTP 422 → "The request was declined by the safety policy." in UI |
| Insufficient evidence renders | `### Yetersiz Kanıt` heading in answer, empty citations panel |
| Telemetry trace created | `otel_trace_id` in `complete.metadata`, visible in OTLP backend |
| Playwright E2E on staging URL | All desktop, tablet, and mobile tests pass against real backend |

## Remaining genuine limitations

- **Checkpoints are ephemeral in Cloud Run**: `CHECKPOINT_DIR=/tmp/…` means
  checkpoints do not survive instance restarts. `GET /research/{run_id}/sources`
  returns 404 after an instance recycle. A persistent volume or GCS backend
  would be needed for durable checkpoint access across instances.
- **PDFs not present in staging image**: `document_available` will be `false`
  for all citations in the staged deployment because `data/raw` and
  `data/archive` are not copied into the container image. The evidence panel
  shows "The source PDF is not available from this deployment." This is expected
  and correct behaviour.
- **GraphRAG context exposed through evidence**: No dedicated `/graph-context`
  endpoint exists; `graph_path` is populated on each citation/evidence item
  from the Neo4j traversal performed during research. This matches the frontend
  rendering in `<details class="graph-context">`.
- **Comparison**: `plan.is_comparison` signals multi-company queries in the
  research plan; no separate comparison endpoint is called by the frontend.

## 2026-08-02 streaming and PDF deployment addendum

### Contract implementation

The committed staging backend now uses workflow-native events rather than
checkpoint polling followed by synthetic answer chunks:

- `ResearchWorkflow` emits real stage transitions, plans, task/evidence updates,
  citations, and completion signals while it runs.
- `ReportWriterAgent` emits each report section at generation time. The stream
  never receives a completed response and divides it into artificial fixed-size
  chunks.
- Each emitted answer section passes the existing output guardrail before it is
  sent. The completed answer retains the existing final guardrail and
  non-streaming `POST /research` behavior.
- A disconnect sets a cooperative cancellation signal. The workflow saves a
  `CANCELLED` checkpoint and stops before its next bounded stage or task.
- Citation detail and PDF resolution now require an exact, `verified` entry in
  `data/report_manifest.jsonl`. The staging image includes the matching tracked
  `data/raw` PDFs, so `FileResponse` can return real `application/pdf` bytes and
  native HTTP ranges; it does not construct source filenames, page numbers,
  excerpts, URLs, or files.

The frontend/BFF contract still has no separate graph-context, company-profile,
or comparison API route. The exact supported surfaces are the catalog route,
research plan/answer, and citation/evidence events: catalog profiles are backed
by `config/companies.yaml`, comparisons by `plan.is_comparison` plus the
citation-backed research report, and GraphRAG context by evidence
`graph_path`. Where a run has no graph evidence, that field is `null`; no graph
context is manufactured.

### Local evidence

| Check | Result |
| --- | --- |
| Full backend pytest suite (documented exclusions) | PASS — 405 passed |
| Ruff | PASS |
| mypy | PASS — 132 source files |
| OpenAPI contract verification | PASS — `/health/live`, `/health/ready`, `/research`, `/research/stream`, `/research/companies`, source detail, and document paths present |
| Native streaming unit/integration coverage | PASS — writer section deltas, workflow stage cancellation, NDJSON contract, safety, source/PDF, and HTTP Range coverage |
| Local Docker build | NOT RUN — local Colima/Docker socket unavailable |
| GitHub release container build/smoke/Trivy/SBOM | PASS — [run 30744920853](https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30744920853) |

### Published image and deployment status

| Item | Value |
| --- | --- |
| Source commits | `87e0ff7` (workflow-native stream/PDF), `a41bfe0` (immutable mirror gate), `7e74a9e` superseded (deployer cannot self-manage repository IAM) |
| Published GHCR image | `ghcr.io/ceylanal/company-intelligence-graphrag@sha256:bdef4670255d679b8cf318c32769049d849003dbad9407031d1bc2b7f569ed90` |
| Image signature | PASS — release evidence contains Cosign verification |
| First staging deploy | FAILED — [run 30745292857](https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30745292857); digest was not mirrored into Artifact Registry |
| Second staging deploy | FAILED before Cloud Run revision creation — [run 30745405803](https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30745405803); deploy identity lacks `artifactregistry.repositories.uploadArtifacts` on `europe-west1/company-graphrag` |
| Third staging deploy | FAILED before image mirroring — [run 30745554398](https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30745554398); the deploy identity also lacks `artifactregistry.repositories.getIamPolicy`, so it cannot grant itself the required role |
| Artifact Registry mirror | PASS — `mirror-bdef4670255d` resolved to the identical signed digest |
| Active Cloud Run revision | `company-graphrag-staging-sha-bdef4670-run-66207668`, 100% staging traffic |
| Successful deploy stages | Image mirror and guarded private Cloud Run deploy PASS in [run 30766207668](https://github.com/ceylanal/company-intelligence-graphrag/actions/runs/30766207668) |
| Workflow result | FAILED only at readiness smoke: Neo4j returned `ServiceUnavailable`; Qdrant, liveness, version, request validation, API-key rejection, and bounded real research passed |

The deployment workflow now copies the exact signed OCI index with pinned
`gcrane v0.21.8`, verifies the destination digest equals the signed GHCR digest,
and only then invokes Cloud Run. This is a copy, not a rebuild. The remaining
external prerequisite is a repository-level `roles/artifactregistry.writer`
binding for the service account configured as `GCP_SERVICE_ACCOUNT` in the
staging GitHub environment. A repository IAM administrator must create that
binding; the deployment identity cannot safely grant it to itself, so that
attempt has been removed from the workflow. No production resource, Cloud Run
public access, or Cloud Run traffic changed during the failed attempts.

### 2026-08-02 deployed-staging verification

The Artifact Registry Writer binding was then provisioned for the dedicated
staging deployer. The deployer mirrored the existing signed image without a
rebuild and deployed revision
`company-graphrag-staging-sha-bdef4670-run-66207668` with all staging traffic.
Direct anonymous access to
`https://company-graphrag-staging-c6oeawtcxq-ew.a.run.app/health/live` remained
HTTP 403. The same-origin Vercel BFF health route remained HTTP 200.

Authenticated OpenAPI, fetched through the same-origin BFF, contains exactly:

```
/
/health/live
/health/ready
/research
/research/companies
/research/stream
/research/{run_id}/sources/{citation_index}
/research/{run_id}/sources/{citation_index}/document
/version
```

Real browser acceptance against the public Vercel staging app exercised a
live ASELSAN research run. It displayed workflow steps progressively, rendered
the final citation-backed answer and safety/evidence-coverage warnings, and
loaded the actual indexed `ASELS__2024__annual_report__tr.pdf`. The source
endpoint returned its real document name, SHA-256, official source URL, page,
and vector retrieval method. The BFF PDF endpoint returned `206 Partial
Content`, `Accept-Ranges: bytes`, and
`Content-Range: bytes 0-255/14951328`. Responsive browser checks passed at
desktop (1280px), tablet (768px), and mobile (390px) with no horizontal
overflow; backend readiness, workflow steps, answer metrics, citations, and
safety warning state were visible.

Representative telemetry correlation IDs include smoke liveness trace
`88cce1d7e4e943e18a531c5f0574947d`, bounded-research trace
`5d149d5132fe4067b628c136ce4e0f92`, and BFF PDF trace
`b8dd5735c0344ef0a08b539a600349c5`. The real browser runs showed no direct
Cloud Run browser calls or client-side provider keys.

#### Genuine remaining limitation

The deployment workflow is correctly failing closed because the staging Neo4j
Aura dependency currently returns `ServiceUnavailable`: `/health/ready` is
HTTP 503 while Qdrant is healthy. The prior 2026-07-30 staging smoke artifacts
show this same Neo4j configuration healthy, so this is an external runtime
availability or credential issue, not a fabricated graph result. The research
workflow preserves its documented vector fallback and returns `graph_path:
null`; consequently GraphRAG context cannot presently be accepted as working.
No IAM scope was broadened and no production resource was modified. The live
browser cancellation control was exercised, but the short staging workflow
completed before an end-to-end cancelled checkpoint could be observed; the
workflow-level cancellation contract remains covered by the backend test
suite. Re-run graph and cancellation acceptance after Neo4j health is restored.
