# Changelog

All notable changes follow Keep a Changelog conventions.

## [Unreleased]

### Added

- Production container, Compose profiles, health probes, and Cloud Run staging configuration.
- Versioned prompt registry, deterministic public config hash, per-run manifests, and version CLI.
- OpenTelemetry-compatible tracing, Prometheus metrics, correlated JSON logs, and secret redaction.
- Transient retry classification, explicit research budgets, concurrency/rate controls, and Locust scenarios.
- CI quality/eval gates, Trivy scanning, SBOM generation, keyless signing preparation, and Dependabot.

### Compatibility

- Existing prompt constant imports and legacy `ResearchState` checkpoints remain readable.
- Data pipelines, Qdrant collections, Neo4j graphs, PDFs, chunks, and embeddings are not migrated or regenerated.
