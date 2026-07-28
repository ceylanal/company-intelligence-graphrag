# Rollback Runbook

1. Identify the last healthy Cloud Run revision and its `/version` manifest.
2. Set `TARGET_REVISION`, `GCP_PROJECT_ID`, `GCP_REGION`, and `CLOUD_RUN_SERVICE`.
3. Run `scripts/rollback_cloud_run.sh`.
4. Verify liveness, readiness, version hash, vector, graph, hybrid, and citation smoke checks.
5. Keep the bad revision at zero traffic for investigation; do not delete evidence.

For local rollback, run the previous immutable image digest with the same external database URLs. Never delete named Qdrant/Neo4j volumes as part of rollback.
