"""Unit tests for PDF ingestion pipeline."""

from pathlib import Path

import fitz  # type: ignore[import-untyped]
import pytest
from typer.testing import CliRunner

from company_graphrag.cli import app
from company_graphrag.ingestion import (
    ParsedPage,
    normalize_text,
    parse_filename_metadata,
    parse_pdf_directory,
    parse_pdf_file,
)

runner = CliRunner()


def create_dummy_pdf(tmp_path: Path, filename: str, pages_content: list[str]) -> Path:
    """Helper to create a dummy PDF file using PyMuPDF."""
    pdf_path = tmp_path / filename
    doc = fitz.open()
    for content in pages_content:
        page = doc.new_page()
        if content:
            page.insert_text((50, 50), content)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_parse_filename_metadata_standard() -> None:
    """Test parsing standard filename convention {TICKER}__{YEAR}__{TYPE}__{LANG}.pdf."""
    ticker, year, report_type, lang = parse_filename_metadata("ASELS__2025__annual_report__tr.pdf")
    assert ticker == "ASELS"
    assert year == 2025
    assert report_type == "annual_report"
    assert lang == "tr"


def test_parse_filename_metadata_fallback() -> None:
    """Test fallback heuristic parsing for non-standard filenames."""
    ticker, year, report_type, lang = parse_filename_metadata("Akbank_Report_2024.pdf")
    assert ticker == "AKBAN" or ticker == "UNKNOWN" or "AKB" in ticker
    assert year == 2024
    assert report_type == "annual_report"
    assert lang == "tr"


def test_normalize_text() -> None:
    """Test text normalization utility."""
    raw = "  Hello   World \x00 \n\n\n\n Paragraph 2  "
    clean = normalize_text(raw)
    assert "Hello World" in clean
    assert "\x00" not in clean
    assert "\n\n\n" not in clean


def test_parse_pdf_file_success(tmp_path: Path) -> None:
    """Test parsing a valid PDF file and generating JSONL output."""
    pdf_path = create_dummy_pdf(
        tmp_path,
        "AKBNK__2024__annual_report__tr.pdf",
        [
            "Akbank 2024 Faaliyet Raporu Sayfa 1 Metni " * 5,
            "Finansal Tablolar ve Bilanço " * 5,
        ],
    )
    out_dir = tmp_path / "processed"

    pages = parse_pdf_file(pdf_path, output_dir=out_dir, overwrite=True)

    assert len(pages) == 2
    assert pages[0].document_id == "AKBNK__2024__annual_report__tr"
    assert pages[0].page_id == "AKBNK__2024__annual_report__tr_p1"
    assert pages[0].page_number == 1
    assert pages[0].total_pages == 2
    assert pages[0].ticker == "AKBNK"
    assert pages[0].year == 2024
    assert pages[0].report_type == "annual_report"
    assert pages[0].language == "tr"
    assert pages[0].is_empty is False
    assert pages[0].needs_ocr is False

    # Check JSONL output file exists and is valid
    expected_jsonl = out_dir / "AKBNK" / "AKBNK__2024__annual_report__tr.jsonl"
    assert expected_jsonl.exists()

    with open(expected_jsonl, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
        assert len(lines) == 2
        p1 = ParsedPage.model_validate_json(lines[0])
        assert p1.page_number == 1


def test_parse_pdf_file_empty_pages_and_ocr(tmp_path: Path) -> None:
    """Test parsing PDF pages with empty or low text marking needs_ocr=True."""
    pdf_path = create_dummy_pdf(
        tmp_path,
        "THYAO__2025__annual_report__en.pdf",
        [
            "",  # Empty page
            "Short",  # Below 50 char threshold
        ],
    )
    out_dir = tmp_path / "processed"

    pages = parse_pdf_file(pdf_path, output_dir=out_dir, overwrite=True)

    assert len(pages) == 2
    assert pages[0].is_empty is True
    assert pages[0].needs_ocr is True

    assert pages[1].is_empty is False
    assert pages[1].needs_ocr is True


def test_parse_pdf_file_skip_existing(tmp_path: Path) -> None:
    """Test skipping existing JSONL output when overwrite is False."""
    pdf_path = create_dummy_pdf(
        tmp_path,
        "SISE__2023__annual_report__tr.pdf",
        ["Şişecam 2023 Faaliyet Raporu Metni " * 10],
    )
    out_dir = tmp_path / "processed"

    # First parse
    pages1 = parse_pdf_file(pdf_path, output_dir=out_dir, overwrite=False)
    assert len(pages1) == 1

    # Second parse with overwrite=False should skip and return cached/read pages
    pages2 = parse_pdf_file(pdf_path, output_dir=out_dir, overwrite=False)
    assert len(pages2) == 1
    assert pages2[0].document_id == pages1[0].document_id


def test_parse_pdf_file_missing(tmp_path: Path) -> None:
    """Test error when parsing a non-existent PDF file."""
    non_existent = tmp_path / "does_not_exist.pdf"
    with pytest.raises(FileNotFoundError):
        parse_pdf_file(non_existent)


def test_parse_pdf_file_corrupted(tmp_path: Path) -> None:
    """Test error when parsing a corrupted PDF file."""
    corrupted_path = tmp_path / "corrupted.pdf"
    corrupted_path.write_bytes(b"NOT A VALID PDF FILE CONTENT")

    with pytest.raises(RuntimeError) as exc_info:
        parse_pdf_file(corrupted_path)
    assert "Corrupted or unreadable PDF" in str(exc_info.value)


def test_parse_pdf_directory_batch(tmp_path: Path) -> None:
    """Test parsing a directory containing valid, missing, and corrupted PDFs."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    # Valid PDF 1
    create_dummy_pdf(raw_dir, "FROTO__2024__annual_report__en.pdf", ["Ford Otosan 2024 " * 10])

    # Valid PDF 2
    create_dummy_pdf(raw_dir, "TCELL__2025__annual_report__tr.pdf", ["Turkcell 2025 " * 10])

    # Corrupted PDF
    corrupted = raw_dir / "BAD__2025__annual_report__tr.pdf"
    corrupted.write_bytes(b"INVALID PDF DATA")

    out_dir = tmp_path / "processed"

    summary = parse_pdf_directory(raw_dir, output_dir=out_dir, overwrite=True)

    assert summary.total_files == 3
    assert summary.succeeded_files == 2
    assert summary.failed_files == 1
    assert len(summary.errors) == 1
    assert summary.errors[0]["file"] == "BAD__2025__annual_report__tr.pdf"


def test_cli_parse_file_and_dir(tmp_path: Path) -> None:
    """Test CLI parse command for both file and directory inputs."""
    pdf_path = create_dummy_pdf(
        tmp_path,
        "KCHOL__2025__annual_report__tr.pdf",
        ["Koç Holding 2025 Faaliyet Raporu " * 10],
    )
    out_dir = tmp_path / "processed_cli"

    # Test file parse
    res_file = runner.invoke(app, ["parse", str(pdf_path), "--output-dir", str(out_dir), "--overwrite"])
    assert res_file.exit_code == 0
    assert "Parsing single PDF file" in res_file.output
    assert "Document ID" in res_file.output

    # Test directory parse
    res_dir = runner.invoke(app, ["parse", str(tmp_path), "--output-dir", str(out_dir), "--overwrite"])
    assert res_dir.exit_code == 0
    assert "Parsing PDF directory" in res_dir.output
    assert "Directory Parse Summary" in res_dir.output


def test_cli_parse_skip_and_overwrite(tmp_path: Path) -> None:
    """Test CLI skipping existing outputs and forcing overwrite."""
    sub_dir = tmp_path / "subdir"
    sub_dir.mkdir()
    _ = create_dummy_pdf(
        sub_dir,
        "MGROS__2024__annual_report__tr.pdf",
        ["Migros 2024 Faaliyet Raporu " * 10],
    )
    out_dir = tmp_path / "processed_cli_skip"

    # First run creates output
    res1 = runner.invoke(app, ["parse", str(sub_dir), "--output-dir", str(out_dir)])
    assert res1.exit_code == 0
    assert "Succeeded Files" in res1.output

    # Second run without --overwrite should skip file
    res2 = runner.invoke(app, ["parse", str(sub_dir), "--output-dir", str(out_dir)])
    assert res2.exit_code == 0
    assert "Skipped Files" in res2.output

    # Third run with --overwrite should re-parse file
    res3 = runner.invoke(app, ["parse", str(sub_dir), "--output-dir", str(out_dir), "--overwrite"])
    assert res3.exit_code == 0
    assert "Succeeded Files" in res3.output


def test_cli_parse_corrupted_isolation(tmp_path: Path) -> None:
    """Test CLI batch directory handling of corrupted PDF without exiting non-zero."""
    raw_dir = tmp_path / "raw_corrupted"
    raw_dir.mkdir()

    create_dummy_pdf(raw_dir, "GOOD__2025__annual_report__tr.pdf", ["Good PDF Content " * 10])
    bad_pdf = raw_dir / "BAD__2025__annual_report__tr.pdf"
    bad_pdf.write_bytes(b"CORRUPTED CONTENT")

    out_dir = tmp_path / "processed_cli_bad"

    res = runner.invoke(app, ["parse", str(raw_dir), "--output-dir", str(out_dir), "--overwrite"])
    assert res.exit_code == 0
    assert "Failed Files" in res.output
    assert "BAD__2025__annual_report__tr.pdf" in res.output
