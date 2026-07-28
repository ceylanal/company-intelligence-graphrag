# Production Deployment Runbook

Production deployment requires explicit user approval and a fully passing production release report.

1. Select the exact digest tested in staging; do not rebuild.
2. Confirm production secrets, Qdrant collection, Aura database/instance, Opik project, and Grafana environment are separate.
3. Confirm the production GitHub environment requires manual approval.
4. Promote the signed digest using the production deployment workflow.
5. Record the Cloud Run service, revision, URL, digest, approver, and timestamp.
6. Run authenticated liveness, readiness, version, bounded research, citation, rate-limit, budget, and injection tests.
7. Verify Opik and Grafana evidence and scan all evidence for secrets.
8. Keep the prior healthy revision available for rollback.
9. Publish a Git tag or GitHub Release only with separate explicit approval.
