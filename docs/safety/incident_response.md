# Safety Incident Response

## Trigger conditions

Treat these as a security incident: a secret in an API/log/trace response, a
cross-company source returned outside authorization scope, an unauthorized tool
execution, successful prompt injection, a poisoned chunk used as an instruction, or
a failing critical/high safety gate.

## Immediate actions

1. Stop the affected deployment or disable the research endpoint through the normal
   operational control; do not delete evidence.
2. Revoke/rotate exposed credentials through the secret manager. Never paste the
   old value into a ticket or artifact.
3. Preserve request ID, run ID, trace ID, guardrail decision codes, and a redacted
   payload fingerprint.
4. Quarantine the document/chunk or disable the affected tool route. Do not alter
   production source data while preserving forensic evidence.
5. Mark the release `SAFETY_RELEASE_BLOCKED` and notify the security owner.

## Investigation and recovery

Determine whether the control failed before retrieval, during context construction,
at a tool boundary, in model output, or during observability export. Add a
deterministic regression case, apply the smallest fail-closed fix, and rerun the
Day 55 audit plus staging rehearsal. Security approval and a fresh passing CI gate
are required before reopening release readiness.
