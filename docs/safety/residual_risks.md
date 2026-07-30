# Residual Safety Risks

| Risk | Severity | Accepted residual risk / mitigation |
| --- | --- | --- |
| Novel multilingual or multimodal injection bypass | Medium | Pattern-based detection is intentionally deterministic; retain context isolation, monitor false negatives, and periodically expand the corpus with reviewed real incidents. |
| Semantically plausible retrieval poisoning | Medium | Detector cannot prove financial truth. Source provenance, ingestion review, citation verification, and sampled human review remain required. |
| Provider/telemetry implementation changes | Medium | Span exception payload recording is disabled locally, but exporter/library upgrades require regression tests and staging inspection. |
| Tenant scope supplied incorrectly by upstream caller | Medium | Tool policy enforces supplied scope; authentication/tenant derivation must remain server-side and independently reviewed. |
| Remote CI/staging evidence absent in this workspace | High until completed | Execute the approved GitHub Actions staging/release workflows and archive their redacted artifacts before changing the final release decision. |
| Secret formats not covered by signatures | Low | Redaction is defense in depth, not secret management; use secret scanning, short-lived credentials, and avoid logging request bodies. |
