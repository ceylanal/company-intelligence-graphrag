"""AI artifact reproducibility and compatibility tests."""

import json
from pathlib import Path

import yaml

from company_graphrag.agents.schema import ResearchState
from company_graphrag.config import Settings
from company_graphrag.versioning.manifest import build_run_manifest, config_hash
from company_graphrag.versioning.prompts import PromptRegistry


def test_config_hash_is_deterministic_and_secret_free() -> None:
    first = Settings(
        environment="test",
        api_key="api-secret-one",
        llm_api_key="llm-secret-one",
        qdrant_api_key="qdrant-secret-one",
        neo4j_password="neo4j-secret-one",
    )
    second = Settings(
        environment="test",
        api_key="api-secret-two",
        llm_api_key="llm-secret-two",
        qdrant_api_key="qdrant-secret-two",
        neo4j_password="neo4j-secret-two",
    )
    assert config_hash(first) == config_hash(first)
    assert config_hash(first) == config_hash(second)

    serialized = build_run_manifest("run_test", settings_obj=first).model_dump_json()
    for secret in ("api-secret-one", "llm-secret-one", "qdrant-secret-one", "neo4j-secret-one"):
        assert secret not in serialized


def test_prompt_change_requires_registry_hash_update(tmp_path: Path) -> None:
    source = Path("config/prompts.yaml")
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    payload["prompts"][0]["content"] += "\nUnversioned behavior change"
    target = tmp_path / "prompts.yaml"
    target.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    errors = PromptRegistry(target).validate()
    assert errors
    assert "without a version/hash update" in errors[0]


def test_prompt_change_changes_config_hash(tmp_path: Path) -> None:
    payload = yaml.safe_load(Path("config/prompts.yaml").read_text(encoding="utf-8"))
    payload["bundle_version"] = "1.1.0"
    payload["prompts"][0]["version"] = "1.1.0"
    payload["prompts"][0]["content"] += "\nVersioned change"
    import hashlib

    payload["prompts"][0]["content_hash"] = hashlib.sha256(
        payload["prompts"][0]["content"].encode("utf-8")
    ).hexdigest()
    target = tmp_path / "prompts.yaml"
    target.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    assert config_hash(registry=PromptRegistry(target)) != config_hash()


def test_legacy_research_state_loads_with_version_defaults() -> None:
    legacy = json.dumps({"run_id": "run_legacy", "user_query": "legacy query"})
    state = ResearchState.model_validate_json(legacy)
    assert state.workflow_version == "1.0.0"
    assert state.prompt_bundle_version == "legacy"
    assert state.config_hash == "legacy"
