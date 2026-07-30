# Day 50 — Security Requirements

These requirements translate the Day 50 threat register into verifiable
controls. `Must` requirements are release gates for the indicated scope;
`Should` requirements are prioritized follow-up work. References use threat
register IDs and OWASP LLM Top 10 2025 identifiers.

| ID | Requirement | Verification / acceptance evidence | Priority |
|---|---|---|---|
| SR-01 | The public research boundary **must** validate request size, history size, roles, content type, file extension, query filters, repetition, and estimated token count before retrieval or LLM invocation. | API and unit tests cover normal, oversized, malformed, flooding, and injection inputs. | Must — TM-01/TM-08 |
| SR-02 | Explicit direct prompt injection **must** block; unknown patterns must fail closed if guardrail evaluation itself fails. | Input guardrail tests and block-rate telemetry without raw payload retention. | Must — TM-01 / LLM01 |
| SR-03 | Every retrieved textual source **must** be treated as untrusted and checked before it enters a Vector RAG or GraphRAG LLM context or citation snippet; suspicious content must be excluded. | Context-builder injection tests; review preserves source provenance and excludes matched chunks. | Must — TM-02 / LLM01 |
| SR-04 | Ingestion **must** retain file hash, source metadata, document/chunk identity, and validation outcome; unapproved sources must not reach production collections. | Signed/approved ingestion manifest and quarantine audit. | Must — TM-03 / LLM04 |
| SR-05 | Retrieval **must** preserve company/ticker/year/report provenance and apply explicit filters when provided. Company comparison output must attribute each claim to its cited source. | Cross-company collision test, retrieval-filter test, citation correctness report. | Must — TM-05 |
| SR-06 | Outputs **must** redact secrets and private keys, block system-prompt/internal configuration disclosure, remove invalid citations, and block definitive financial claims lacking valid retrieved citations. | Output guardrail unit tests and API response regression suite. | Must — TM-04/TM-06 / LLM02, LLM07, LLM09 |
| SR-07 | Agent tools **must** be typed, role-allowlisted, bounded, and use read-only parameterized retrieval paths. Runtime database credentials must be least-privilege and read-only for research. | Negative tool/mutation tests; deployment evidence of read-only identities. | Must — TM-07 / LLM06 |
| SR-08 | The service **must** enforce bounded concurrency, request rate, model calls, total tokens, retrieval fan-out, and execution time. A reviewed provider-price configuration must enforce a per-run monetary ceiling before production. | Load, retry/fan-out, and budget-exhaustion tests; cost telemetry. | Must before production — TM-08 / LLM10 |
| SR-09 | Logs, telemetry, manifests, checkpoints, and CI artifacts **must not** contain raw prompts, full document/chunk text, authorization material, or secrets. They must use allowlisted metadata and redaction. | Automated artifact/log scan in CI and staging telemetry leak check. | Must — TM-04/TM-09 / LLM02 |
| SR-10 | Durable workflow checkpoints **must** be encrypted at rest, access-controlled, and retained/deleted by policy before multi-instance Cloud Run production use. | Storage design review and restore/deletion exercise. | Must before multi-instance production — TM-09 |
| SR-11 | Builds **must** use locked dependencies, SHA-pinned CI actions, non-root containers, secret scanning, vulnerability/misconfiguration scanning, SBOM generation, and immutable signed image deployment. | CI artifacts: lock verification, Gitleaks, Trivy, SBOM, Cosign verification. | Must — TM-10 / LLM03 |
| SR-12 | Staging/production **must** use separate secrets, Qdrant collections, Neo4j databases, and telemetry projects; Cloud Run must require authenticated invocation. | Deployment configuration review and authenticated smoke evidence. | Must — TM-04/TM-05/TM-10 |
| SR-13 | Citation correctness, groundedness, prompt-injection blocks, redaction events, budget exhaustion, and retrieval anomalies **should** have aggregate metrics and alert thresholds. Never include sensitive examples in metric labels. | Dashboard/runbook and alert test. | Should — TM-01/TM-03/TM-06/TM-08 |
| SR-14 | PDF ingestion **should** detect image/OCR hidden instructions and route suspicious files to quarantine for human review. | Adversarial PDF fixture and quarantine decision record. | Should — TM-02 |

## Release decision rules

- A `Must` requirement without passing evidence blocks production activation.
- `Should` requirements may carry a documented residual risk only if no
  confidential, regulated, or cross-tenant data is exposed and an accountable
  owner/date is recorded.
- Any telemetry/artifact secret match, invalid-citation bypass, untrusted
  instruction reaching an LLM context, unauthorized mutation/tool invocation,
  or unbounded-spend path is a release blocker.

## Ownership and review cadence

Engineering owns SR-01–SR-08 and SR-11. Platform/SRE owns SR-09–SR-12.
Security reviews threat register changes, new tools/providers, new ingestion
sources, and any production topology change. Review at least each release and
after a provider, retrieval, or agent capability change.
