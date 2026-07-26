"""Unit tests for CLI doctor command."""

from typing import Any

import httpx
from typer.testing import CliRunner

from company_graphrag.cli import app

runner = CliRunner()


def test_doctor_command_success(monkeypatch: Any) -> None:
    """Test doctor command when services return 200."""

    def mock_get(url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", mock_get)

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Service Health Diagnostics" in result.output
    assert "Qdrant Vector DB" in result.output
    assert "Neo4j Knowledge Graph" in result.output


def test_doctor_command_offline(monkeypatch: Any) -> None:
    """Test doctor command when services are unreachable."""

    def mock_get(url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx, "get", mock_get)

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "OFFLINE" in result.output
    assert "Some local services are unreachable" in result.output


def test_doctor_command_strict_flag(monkeypatch: Any) -> None:
    """Test doctor command --strict flag when services fail."""

    def mock_get(url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx, "get", mock_get)

    result = runner.invoke(app, ["doctor", "--strict"])
    assert result.exit_code == 1
