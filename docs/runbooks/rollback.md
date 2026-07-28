# Revision Rollback Runbook

1. Identify the last healthy revision and its immutable digest.
2. Set only non-secret identifiers:

   ```bash
   export GCP_PROJECT_ID=...
   export GCP_REGION=...
   export CLOUD_RUN_SERVICE=...
   export TARGET_REVISION=...
   ./scripts/rollback_cloud_run.sh
   ```

3. Record rollback start/end time and the traffic update result.
4. Re-run liveness, readiness, version, representative research, citation, and telemetry checks.
5. Verify the returned version manifest and image digest match the target revision.
6. Do not apply a database rollback unless its backward-compatibility and backup plan are separately approved.
