# Day 55 Final Safety Audit

## Release decision

`SAFETY_RELEASE_BLOCKED`

The local code and deterministic release-gate evidence pass, but an independently
executed remote staging run and GitHub Actions run are not available in this
workspace. A production release cannot be asserted from local evidence alone.
No production system or dataset was changed during this audit.

## Audit outcome

The Day 55 controlled red-team run executed 124 deterministic cases with no live
LLM call and no backend mutation. All 124 passed (100% defense success): 50 prompt
injection, 20 retrieval poisoning, 15 secret leakage, 15 tool abuse, 11
cross-company isolation, 10 citation/hallucination, and 3 agent-budget cases.
There are zero open critical, high, medium, low, or informational test findings in
the generated artifact.

The actual FastAPI request chain was exercised with a local staging-profile probe.
A direct prompt-injection request received HTTP 422 before workflow execution.
The remote staging service was deliberately not contacted because neither a staging
URL nor an identity token was configured in this workspace.

## Independent control checks

| Control | Evidence | Result |
| --- | --- | --- |
| Threat model alignment | Day 50 architecture and control mapping reviewed against API, RAG/GraphRAG, tools, telemetry, CI/CD, and ingestion boundaries | Pass, with residual risks below |
| Input/output chain | API `/research` and `RAGGenerator` invoke `InputGuardrails`; API and RAG invoke `OutputGuardrails` | Pass |
| Direct/indirect injection | Input guardrail blocks direct attacks; `ContextIsolator` excludes retrieved instructions | Pass |
| Retrieval poisoning | Similarity score is not trusted; suspicious chunks are excluded before context construction | Pass |
| Secret handling | Output and structured logging redact credentials; spans now retain only exception class, not exception payload | Pass |
| Citation-first | Invalid citations are removed; uncited financial statements are blocked; valid citations are retained | Pass |
| Company isolation | Tool policy constrains ticker/company to the authorized execution context | Pass |
| Agent/tool bounds | Allowlist, schemas, SSRF/path/shell checks, repeat, time, step, token, and cost limits are enforced | Pass |
| CI deploy gate | Safety evaluator is now a pre-deploy step in staging deployment and release candidate workflows | Code review pass; remote execution pending |
| Guardrail failure | Input/output evaluators fail closed and return safe public output | Pass |

## Findings fixed in this audit

- **High — resolved:** `span()` previously called OpenTelemetry `record_exception`,
  which can serialize raw exception text and stack context. It now records only the
  exception class in span status.
- **Medium — resolved:** RAG filter arguments could reach retrieval without the
  input filter schema boundary. `RAGGenerator` now validates and uses sanitized
  ticker, year, company, and report type before retrieval.
- **High — resolved:** the safety workflow was independent of deploy workflows.
  Both staging deployment and release-candidate workflows now run
  `scripts/run_safety_eval.py` before deployment/publish work.
- **Medium — resolved:** output credential detection now also covers generic
  `secret`, `client_secret`, and `authorization` assignments.

## Verification

- `uv run python scripts/run_final_safety_audit.py` — pass, 124/124.
- `uv run python scripts/run_safety_eval.py` — pass, all eight gates pass.
- `uv run pytest tests/safety -q` — pass.
- `uv run ruff check .` — pass.
- `uv run mypy src scripts/run_final_safety_audit.py` — pass.

See [final red-team evidence](../../artifacts/safety/day55/final-redteam-results.json)
and [gate evidence](../../artifacts/safety/day55/safety-gate-evidence.json).
