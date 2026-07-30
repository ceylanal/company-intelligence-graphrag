"""Unit tests for config module."""

import pytest

from company_graphrag.config import Settings


def test_settings_default_values() -> None:
    """Verify defaults independently of a developer's local environment file."""
    default_settings = Settings(_env_file=None)
    assert default_settings.environment in ["development", "test", "staging", "production"]
    assert default_settings.qdrant_host == "localhost"
    assert default_settings.qdrant_port == 6333
    assert default_settings.qdrant_url == "http://localhost:6333"
    assert default_settings.qdrant_collection_name == "company_documents"
    assert default_settings.neo4j_uri == "bolt://localhost:7687"
    assert default_settings.neo4j_http_url == "http://localhost:7474"
    assert default_settings.neo4j_username == "neo4j"
    assert default_settings.neo4j_password == "password"
    assert default_settings.neo4j_database == "neo4j"
    assert default_settings.checkpoint_dir == "data/checkpoints"


def test_settings_effective_urls() -> None:
    """Verify helper properties for canonical URLs."""
    s = Settings(qdrant_url="http://qdrant:6333/", neo4j_http_url="http://neo4j:7474/")
    assert s.effective_qdrant_url == "http://qdrant:6333"
    assert s.effective_neo4j_http_url == "http://neo4j:7474"


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify settings can be overridden via environment variables."""
    monkeypatch.setenv("QDRANT_HOST", "qdrant.local")
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j.local:7687")
    monkeypatch.setenv("CHECKPOINT_DIR", "/tmp/company-graphrag/checkpoints")

    custom_settings = Settings()
    assert custom_settings.qdrant_host == "qdrant.local"
    assert custom_settings.neo4j_uri == "bolt://neo4j.local:7687"
    assert custom_settings.checkpoint_dir == "/tmp/company-graphrag/checkpoints"


def test_local_neo4j_compose_credentials_must_align() -> None:
    """Reject local host/Compose credential drift without exposing either secret."""
    settings = Settings(
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="application-password",
        compose_neo4j_username="neo4j",
        compose_neo4j_password="compose-password",
    )

    with pytest.raises(ValueError, match="Local Neo4j credentials are misaligned"):
        settings.validate_local_neo4j_credential_alignment()


def test_cloud_neo4j_does_not_apply_local_compose_validation() -> None:
    """Keep cloud deployment settings independent of local Compose aliases."""
    settings = Settings(
        neo4j_uri="neo4j+s://example.databases.neo4j.io",
        neo4j_use_cloud=True,
        neo4j_password="cloud-password",
        compose_neo4j_password="local-password",
    )

    settings.validate_local_neo4j_credential_alignment()
