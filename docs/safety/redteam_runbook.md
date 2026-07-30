# Safety Red-Team Runbook

## Scope and safety boundary

Use this runbook only against a disposable/local environment or the approved staging
service. Do not submit real secrets, invoke write tools, change source documents, or
target production endpoints. Use synthetic credentials such as `demo_value` only.

## Local deterministic audit

Run:

```bash
uv run python scripts/run_final_safety_audit.py
uv run python scripts/run_safety_eval.py
```

The first command executes 50 direct injection, 20 retrieved-chunk poisoning, 15
secret, 15 tool, 10+ company-isolation, 10 citation, and budget cases. It uses no
live LLM and performs no retrieval/backend mutation. Inspect only:

- `artifacts/safety/day55/final-redteam-results.json`
- `artifacts/safety/day55/safety-gate-evidence.json`

## Approved staging rehearsal

Obtain a staging URL and short-lived identity token through the approved deployment
workflow. Do not copy the token into shell history, artifacts, or issue trackers.
Run the existing bounded smoke script first, then submit only the predefined,
read-only Day 55 injection requests. Expected outcome is HTTP 422 for direct
injection and no workflow run/tool call.

Before declaring staging success, verify:

1. The response contains no prompt, stack trace, URL topology, or secret value.
2. Logs and telemetry contain only request IDs, action codes, and exception class.
3. No Qdrant/Neo4j writes, collection changes, or source ingestion occurred.
4. CI artifact includes a passing `safety-summary.json` and JUnit result.

## Failure handling

If an attack is allowed, stop the rehearsal, preserve only redacted evidence, and
follow [incident response](incident_response.md). A failing `run_safety_eval.py`
exit code is a release stop; its output lists the scenario IDs that violated a gate.
