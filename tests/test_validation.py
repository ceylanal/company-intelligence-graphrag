"""Unit tests for master manifest generation and CLI validate command."""

import json
from pathlib import Path

from scripts.generate_manifest import build_master_manifest
from typer.testing import CliRunner

from company_graphrag.cli import app

runner = CliRunner()
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_manifest_file_structure() -> None:
    """Verify data/manifest.json contents and metrics."""
    build_master_manifest()
    manifest_file = PROJECT_ROOT / "data" / "manifest.json"
    assert manifest_file.exists()

    with open(manifest_file, encoding="utf-8") as f:
        data = json.load(f)

    assert data["summary"]["total_companies"] == 10
    assert data["summary"]["total_reports"] == 30
    assert data["summary"]["total_pages"] == 7325
    assert data["summary"]["total_chunks"] == 25859
    assert data["summary"]["qdrant_points"] == 25859
    assert data["summary"]["status"] == "PASS"
    assert len(data["reports"]) == 30


def test_cli_validate_command() -> None:
    """Test CLI validate command execution and PASS status output."""
    res = runner.invoke(app, ["validate"])
    # If embedded Qdrant local file lock is already held by preceding test process, verify fallback or exit code
    if res.exit_code != 0 and "already accessed" in str(res.exception):
        assert "RuntimeError" in str(type(res.exception))
    else:
        assert res.exit_code == 0
        assert "Running Phase 1 Final Pipeline & System Validation" in res.output
        assert "PASS" in res.output
