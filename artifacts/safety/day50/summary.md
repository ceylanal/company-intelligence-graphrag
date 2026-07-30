# Day 50 Safety Threat Modeling — Summary

Status: **completed**

The assessment covers the API, Vector RAG/Qdrant, GraphRAG/Neo4j, agent tools,
LLM gateway/fallback, PDF ingestion, CI/CD/Cloud Run, and telemetry. Ten
threats are tracked in `threat_register.json`, with OWASP LLM Top 10 2025 and
MITRE ATLAS technique-name mappings.

## Critical finding resolved

Retrieved PDF/chunk text was already recognized by an agent utility as
untrusted, but Vector RAG and GraphRAG context builders did not apply that
sanitizer before constructing LLM context. The builders now neutralize known
imperative prompt-injection fragments in both formatted context and citation
snippets. This preserves provenance and ordinary evidence while preventing that
text from being presented as executable instruction.

## Highest residual-risk work before production

1. Enforce a provider-priced monetary budget and per-principal quotas.
2. Require approved/signed ingestion manifests and independent collection write
   identities to reduce retrieval poisoning.
3. Use read-only database identities, encrypted checkpoint storage, retention
   controls, and strict environment separation.
4. Make telemetry/artifact leak scans, citation correctness, signed image
   verification, and HIGH-severity dependency policy deployment gates.
5. Add adversarial OCR/image-PDF and semantic citation-entailment test suites.

## Verification evidence

| Command | Result |
|---|---|
| `uv run pytest tests/test_context_builder.py tests/test_graphrag_answer_generation.py tests/test_observability_guardrails.py tests/safety -q` | 36 passed |
| `uv run pytest -q` | 321 passed, 0 failed (7 existing third-party/runtime warnings) |
| `uv run ruff check .` | passed |
| `uv run mypy src` | 123 source files, 0 issues |

The full test run warnings are PyMuPDF/SWIG deprecations, a FastAPI TestClient
deprecation, local Qdrant’s large-local-collection warning, and an intentionally
unreachable telemetry exporter retry. They did not change the passing command
status. No test failure remains.
