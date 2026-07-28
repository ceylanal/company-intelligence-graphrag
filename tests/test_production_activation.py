"""Production activation contract and evidence tests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from scripts.generate_activation_manifest import build_activation_manifest


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
