"""Production activation contract and evidence tests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from scripts.generate_activation_manifest import build_activation_manifest
from scripts.neo4j_activation import migrate as migrate_neo4j
from scripts.qdrant_activation import REQUIRED_PAYLOAD_INDEXES, ensure_payload_indexes


def test_activation_manifest_never_contains_secret_values(monkeypatch: object) -> None:
    secret = "do-not-leak-production-secret"
    # pytest's fixture is intentionally duck-typed here to avoid importing its implementation type.
    monkeypatch.setenv("QDRANT_API_KEY", secret)  # type: ignore[attr-defined]
    monkeypatch.setenv("OPIK_API_KEY", secret)  # type: ignore[attr-defined]

    manifest = build_activation_manifest()
    rendered = json.dumps(manifest)

    assert secret not in rendered
    assert manifest["credential_presence"]["application_secrets"]["QDRANT_API_KEY"] is True
    assert manifest["credential_presence"]["application_secrets"]["OPIK_API_KEY"] is True


def test_activation_contract_uses_separate_staging_and_production_targets() -> None:
    contract = yaml.safe_load(Path("config/production_activation.yaml").read_text(encoding="utf-8"))
    staging = contract["environments"]["staging"]
    production = contract["environments"]["production"]

    assert staging["qdrant_collection"] != production["qdrant_collection"]
    assert staging["opik_project"] != production["opik_project"]
    assert staging["cloud_run_service"] != production["cloud_run_service"]
    assert staging["github_environment"] == "staging"
    assert production["github_environment"] == "production"


def test_production_release_report_is_blocked_without_external_evidence() -> None:
    report = Path("docs/llmops/production_release_report.md").read_text(encoding="utf-8")
    assert "PRODUCTION_ACTIVATION_BLOCKED" in report
    assert "No deployment" in report


def test_neo4j_migration_uses_target_specific_checkpoint(tmp_path: Path) -> None:
    checkpoint = tmp_path / "staging-checkpoint.json"
    report = migrate_neo4j(
        uri="neo4j+s://example.invalid",
        username="neo4j",
        password_env="NEO4J_PASSWORD",
        database="staging",
        input_dir=Path("data/graph/sample_day19"),
        checkpoint_path=checkpoint,
        execute=False,
    )

    assert report["status"] == "DRY_RUN"
    assert report["checkpoint_path"] == str(checkpoint)


def test_private_cloud_run_grants_only_deployer_invocation() -> None:
    deploy_script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")

    assert "--no-allow-unauthenticated" in deploy_script
    assert 'serviceAccount:${GCP_SERVICE_ACCOUNT}' in deploy_script
    assert 'roles/run.invoker' in deploy_script


def test_cloud_run_has_runtime_memory_headroom_and_unique_ci_revision() -> None:
    deploy_script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")

    assert 'CLOUD_RUN_MEMORY:=2Gi' in deploy_script
    assert '--memory "$CLOUD_RUN_MEMORY"' in deploy_script
    assert 'GITHUB_RUN_ID' in deploy_script
    assert "CHECKPOINT_DIR=/tmp/company-graphrag/checkpoints" in deploy_script
    assert "RUN_MANIFEST_DIR=/tmp/company-graphrag/run-manifests" in deploy_script


def test_qdrant_activation_creates_only_missing_retrieval_indexes() -> None:
    class CollectionInfo:
        payload_schema = {"ticker": {"data_type": "keyword"}}

    class FakeClient:
        def __init__(self) -> None:
            self.created: list[tuple[str, str, object, bool]] = []

        def get_collection(self, collection: str) -> CollectionInfo:
            assert collection == "company_documents_staging"
            return CollectionInfo()

        def create_payload_index(
            self,
            *,
            collection_name: str,
            field_name: str,
            field_schema: object,
            wait: bool,
        ) -> None:
            self.created.append((collection_name, field_name, field_schema, wait))

    client = FakeClient()
    report = ensure_payload_indexes(client, "company_documents_staging")  # type: ignore[arg-type]

    assert report["created_indexes"] == ["year", "company", "report_type", "language"]
    assert {item[1] for item in client.created} == set(REQUIRED_PAYLOAD_INDEXES) - {"ticker"}
    assert all(item[0] == "company_documents_staging" and item[3] for item in client.created)
