# Backup and Restore Runbook

Before backup, record `/version`, collection name/version, Qdrant point count, Neo4j node/relationship counts, constraints, and indexes.

- Qdrant: create a collection snapshot with the Qdrant snapshot API and copy it to access-controlled storage. Restore into a new collection first, then compare counts, sampled payloads, and a vector query.
- Neo4j: use the edition/provider-supported dump or Aura export. Restore to a separate test database and compare counts, constraints/indexes, and a multi-hop query.
- Repository: retain signed image digest, prompt registry, graph schema, eval manifests, and run manifests.

The procedure must first be rehearsed with non-sensitive test data. This task does not delete, snapshot, upload, or mutate the user’s existing databases.
