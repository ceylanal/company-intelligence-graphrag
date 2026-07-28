# Qdrant Migration and Backup/Restore Runbook

Create the local baseline:

```bash
uv run python scripts/qdrant_activation.py inventory \
  --path data/vector_store/qdrant_db \
  --collection company_documents \
  --output artifacts/production_activation/qdrant/pre-migration-inventory.json
```

Dry-run migration:

```bash
TARGET_QDRANT_API_KEY=... uv run python scripts/qdrant_activation.py migrate \
  --source-path data/vector_store/qdrant_db \
  --source-collection company_documents \
  --target-url https://QDRANT_STAGING \
  --target-collection company_documents_staging \
  --output artifacts/production_activation/qdrant/migration-report.json
```

Repeat with `--execute` only after checking the target name and backup state. Upsert IDs make reruns idempotent.

Create the cloud inventory with `inventory --url ...`, then compare:

```bash
uv run python scripts/qdrant_activation.py compare \
  --source artifacts/production_activation/qdrant/pre-migration-inventory.json \
  --target artifacts/production_activation/qdrant/post-migration-inventory.json \
  --output artifacts/production_activation/qdrant/integrity-report.json
```

Use the Qdrant Cloud snapshot API/console supported by the selected free plan, restore into a distinctly named temporary collection, rerun inventory/query comparisons, and delete it only after recording explicit cleanup approval. Never delete the local collection.
