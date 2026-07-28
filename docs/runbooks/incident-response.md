# Production Incident Response

1. Classify impact: availability, dependency, data integrity, model quality, telemetry, security, or cost.
2. Capture service/revision/digest, UTC window, request/run/trace IDs, dependency status, and sanitized logs.
3. Contain:
   - revoke or rotate exposed credentials;
   - disable the affected revision or route traffic to the last healthy revision;
   - stop migrations or write traffic if integrity is uncertain;
   - tighten rate/model/token budgets for cost incidents.
4. Recover using the rollback and database runbooks.
5. Validate liveness, readiness, version, representative research, citations, telemetry, and integrity.
6. Preserve a secret-free evidence timeline.
7. Document root cause, contributing factors, detection gap, corrective actions, owners, and deadlines.
