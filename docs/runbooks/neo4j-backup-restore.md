# Neo4j Aura Migration and Backup/Restore Runbook

The current repository graph audit reports zero nodes and relationships. Do not claim an Aura migration until a non-empty authoritative source graph is recovered or generated.

Inventory a source or target:

```bash
NEO4J_PASSWORD=... uv run python scripts/neo4j_activation.py inventory \
  --uri neo4j+s://HOST \
  --username neo4j \
  --database neo4j \
  --output artifacts/production_activation/neo4j/inventory.json
```

After migration, compare source and target inventories:

```bash
uv run python scripts/neo4j_activation.py compare \
  --source artifacts/production_activation/neo4j/pre-migration-inventory.json \
  --target artifacts/production_activation/neo4j/post-migration-inventory.json \
  --output artifacts/production_activation/neo4j/integrity-report.json
```

Use Aura’s supported dump/import or logical export mechanism for the selected plan. Preserve deterministic identifiers, labels, relationship types, constraints, indexes, provenance, and citation fields. Restore into a separate staging or local test database, then verify counts, distributions, constraints, orphans, provenance, and deterministic multi-hop queries.
