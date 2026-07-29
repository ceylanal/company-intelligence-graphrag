"""Unit tests for config module."""

import pytest

from company_graphrag.config import Settings, settings


def test_settings_default_values() -> None:
    """Verify default values for Qdrant and Neo4j connections."""
    assert settings.environment in ["development", "test", "staging", "production"]
    assert settings.qdrant_host == "localhost"
    assert settings.qdrant_port == 6333
    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.qdrant_collection_name == "company_documents"
    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert settings.neo4j_http_url == "http://localhost:7474"
    assert settings.neo4j_username == "neo4j"
    assert settings.neo4j_password == "password"
    assert settings.neo4j_database == "neo4j"
    assert settings.checkpoint_dir == "data/checkpoints"


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
