# Secret Rotation Runbook

1. Create a replacement in the provider and Secret Manager.
2. Update the Cloud Run secret version reference without printing the value.
3. Deploy a no-traffic revision and test readiness/provider access.
4. Move traffic, verify telemetry redaction, then revoke the old credential.
5. Audit logs and repository history. Never place the replacement in `.env.example`, manifests, config hashes, artifacts, or CI logs.
