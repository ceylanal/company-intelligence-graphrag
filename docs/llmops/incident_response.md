# Incident Response Runbook

Classify incidents as availability, bad answer/quality regression, credential exposure, cost spike, or dependency degradation. Preserve the request/run/trace IDs and public manifest; do not copy user queries or document content into tickets unless approved.

For availability, inspect readiness components and dependency latency. For answer quality, quarantine the release digest, compare prompt/workflow/config hashes, and run the representative eval. For cost, disable external model credentials or set provider quotas, then switch to mock only for diagnostics—not as an undisclosed production answer source. For suspected credential exposure, follow secret rotation immediately and invalidate affected tokens.
