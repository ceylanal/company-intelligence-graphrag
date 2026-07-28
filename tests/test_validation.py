"""Hermetic tests for master manifest generation and CLI validation."""

import json
from pathlib import Path

from scripts import generate_manifest
from typer.testing import CliRunner

from company_graphrag.cli import app

runner = CliRunner()


def test_manifest_file_structure(tmp_path: Path, monkeypatch) -> None:
    """Build a manifest from isolated page and chunk fixtures."""
    data_dir = tmp_path / "data"
    pages_dir = data_dir / "processed" / "pages"
    chunks_dir = data_dir / "processed" / "chunks"
    source_manifest = data_dir / "report_manifest.jsonl"
    output_manifest = data_dir / "manifest.json"
    source_manifest.parent.mkdir(parents=True)

    reports = [
        {
            "company_name": "Company A",
            "canonical_ticker": "CMPA",
            "year": 2024,
            "document_type": "annual_report",
            "language": "tr",
            "source_url": "https://example.com/a.pdf",
            "sha256": "a" * 64,
        },
        {
            "company_name": "Company B",
            "canonical_ticker": "CMPB",
            "year": 2024,
            "document_type": "annual_report",
            "language": "tr",
            "source_url": "https://example.com/b.pdf",
            "sha256": "b" * 64,
        },
    ]
    source_manifest.write_text(
        "".join(json.dumps(report) + "\n" for report in reports),
        encoding="utf-8",
    )
    for report, page_count, chunk_count in zip(reports, [2, 3], [4, 5], strict=True):
        ticker = report["canonical_ticker"]
        doc_id = f"{ticker}__2024__annual_report__tr"
        page_file = pages_dir / ticker / f"{doc_id}.jsonl"
        chunk_file = chunks_dir / ticker / f"{doc_id}_chunks.jsonl"
        page_file.parent.mkdir(parents=True, exist_ok=True)
        chunk_file.parent.mkdir(parents=True, exist_ok=True)
        page_file.write_text("{}\n" * page_count, encoding="utf-8")
        chunk_file.write_text("{}\n" * chunk_count, encoding="utf-8")

    monkeypatch.setattr(generate_manifest, "MANIFEST_JSONL", source_manifest)
    monkeypatch.setattr(generate_manifest, "OUTPUT_MANIFEST_JSON", output_manifest)
    monkeypatch.setattr(generate_manifest, "PAGES_DIR", pages_dir)
    monkeypatch.setattr(generate_manifest, "CHUNKS_DIR", chunks_dir)
    generate_manifest.build_master_manifest()

    data = json.loads(output_manifest.read_text(encoding="utf-8"))
    assert data["summary"] == {
        "total_companies": 2,
        "total_reports": 2,
        "total_pages": 5,
        "total_chunks": 9,
        "qdrant_points": 9,
        "status": "PASS",
    }
    assert len(data["reports"]) == 2


def test_cli_validate_command_fails_without_dataset(tmp_path: Path, monkeypatch) -> None:
    """Validation must fail honestly when the production dataset is absent."""
    monkeypatch.chdir(tmp_path)
    manifest_path = tmp_path / "data" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{}", encoding="utf-8")

    result = runner.invoke(app, ["validate"])

    assert result.exit_code == 1
    assert "FAIL" in result.output
    assert "validation failed" in result.output
