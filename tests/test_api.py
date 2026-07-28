"""Unit and integration tests for FastAPI application and health endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from company_graphrag.api.app import app
from company_graphrag.config import Settings


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI TestClient fixture."""
    return TestClient(app)


def test_liveness_probe(client: TestClient) -> None:
    """Verify /health/live returns HTTP 200 and expected JSON structure."""
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "live"
    assert "environment" in data


def test_version_info(client: TestClient) -> None:
    """Verify /version returns HTTP 200 with metadata."""
    response = client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "company-graphrag"
    assert data["version"] == "0.1.0"
    assert "environment" in data
    assert "python_version" in data


def test_root_endpoint(client: TestClient) -> None:
    """Verify root endpoint returns welcome metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Company Intelligence GraphRAG API"
    assert data["docs"] == "/docs"


@patch("company_graphrag.api.health.check_qdrant_health")
@patch("company_graphrag.api.health.check_neo4j_health")
def test_readiness_probe_healthy(mock_neo4j: AsyncMock, mock_qdrant: AsyncMock, client: TestClient) -> None:
    """Verify /health/ready returns HTTP 200 when both services are healthy."""
    mock_qdrant.return_value = (True, {"status": "ok", "url": "http://localhost:6333", "details": "Online"})
    mock_neo4j.return_value = (True, {"status": "ok", "url": "http://localhost:7474", "details": "Online"})

    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["components"]["qdrant"]["status"] == "ok"
    assert data["components"]["neo4j"]["status"] == "ok"


@patch("company_graphrag.api.health.check_qdrant_health")
@patch("company_graphrag.api.health.check_neo4j_health")
def test_readiness_probe_qdrant_unhealthy(
    mock_neo4j: AsyncMock, mock_qdrant: AsyncMock, client: TestClient
) -> None:
    """Verify /health/ready returns HTTP 503 when Qdrant service is down."""
    mock_qdrant.return_value = (False, {"status": "error", "url": "http://localhost:6333", "details": "Connection error"})
    mock_neo4j.return_value = (True, {"status": "ok", "url": "http://localhost:7474", "details": "Online"})

    response = client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["components"]["qdrant"]["status"] == "error"
    assert data["components"]["neo4j"]["status"] == "ok"


@patch("company_graphrag.api.health.check_qdrant_health")
@patch("company_graphrag.api.health.check_neo4j_health")
def test_readiness_probe_neo4j_unhealthy(mock_neo4j: AsyncMock, mock_qdrant: AsyncMock, client: TestClient) -> None:
    """Verify /health/ready returns HTTP 503 when Neo4j service is down."""
    mock_qdrant.return_value = (True, {"status": "ok", "url": "http://localhost:6333", "details": "Online"})
    mock_neo4j.return_value = (False, {"status": "error", "url": "http://localhost:7474", "details": "Connection error"})

    response = client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["components"]["qdrant"]["status"] == "ok"
    assert data["components"]["neo4j"]["status"] == "error"


def test_settings_environment_modes() -> None:
    """Verify environment setting normalization and properties."""
    dev_settings = Settings(environment="DEVELOPMENT")
    assert dev_settings.is_development
    assert not dev_settings.is_production

    prod_settings = Settings(environment="production")
    assert prod_settings.is_production

    staging_settings = Settings(environment="staging")
    assert staging_settings.is_staging

    test_settings = Settings(environment="test")
    assert test_settings.is_test

    testing_settings = Settings(environment="testing")
    assert testing_settings.is_test

    with pytest.raises(ValueError, match="Invalid environment"):
        Settings(environment="invalid_env")
