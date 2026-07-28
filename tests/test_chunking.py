"""Unit tests for document chunking module."""

from pathlib import Path

from typer.testing import CliRunner

from company_graphrag.chunking import (
    ChunkRecord,
    chunk_document_directory,
    chunk_document_file,
    chunk_page_records,
    compute_deterministic_chunk_id,
    get_company_name,
)
from company_graphrag.cli import app
from company_graphrag.ingestion.models import ParsedPage

runner = CliRunner()


def test_get_company_name() -> None:
    """Test company name resolution for tickers."""
    assert get_company_name("ASELS") == "Aselsan Elektronik Sanayi ve Ticaret A.Ş."
    assert get_company_name("AKBNK") == "Akbank T.A.Ş."
    assert get_company_name("UNKNOWN_TICKER") == "UNKNOWN_TICKER"


def test_compute_deterministic_chunk_id() -> None:
    """Test chunk ID determinism."""
    doc_id = "AKBNK__2024__annual_report__tr"
    idx = 0
    text = "Akbank 2024 yılı entegre faaliyet raporu giriş bölümü."

    id1 = compute_deterministic_chunk_id(doc_id, idx, text)
    id2 = compute_deterministic_chunk_id(doc_id, idx, text)

    assert id1 == id2
    assert len(id1) == 16


def test_chunking_short_text() -> None:
    """Test chunking a short document (< 500 tokens)."""
    p1 = ParsedPage(
        document_id="TEST__2025__report__tr",
        page_id="TEST__2025__report__tr_p1",
        source_path="/path/test.pdf",
        filename="TEST__2025__report__tr.pdf",
        file_hash="123456",
        ticker="ASELS",
        year=2025,
        report_type="annual_report",
        language="tr",
        page_number=1,
        total_pages=1,
        text="Aselsan Elektronik 2025 yılı ilk çeyrek faaliyet raporu genel açıklaması.",
        character_count=73,
        word_count=10,
        is_empty=False,
        needs_ocr=False,
    )

    chunks = chunk_page_records([p1], target_tokens=500, overlap_tokens=50)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].ticker == "ASELS"
    assert chunks[0].company == "Aselsan Elektronik Sanayi ve Ticaret A.Ş."
    assert chunks[0].page_number == 1
    assert "Aselsan Elektronik" in chunks[0].text


def test_chunking_long_text_and_overlap() -> None:
    """Test chunking a long multi-page text into multiple chunks with overlap."""
    paragraph = (
        "Bu paragraf Şişecam 2025 sürdürülebilirlik ve finansal analiz raporu detaylı metnini içermektedir. " * 15
    )

    pages = []
    for i in range(1, 4):
        pages.append(
            ParsedPage(
                document_id="SISE__2025__annual_report__tr",
                page_id=f"SISE__2025__annual_report__tr_p{i}",
                source_path="/path/sise.pdf",
                filename="SISE__2025__annual_report__tr.pdf",
                file_hash="abcdef",
                ticker="SISE",
                year=2025,
                report_type="annual_report",
                language="tr",
                page_number=i,
                total_pages=3,
                text=f"Sayfa {i} Metni: {paragraph}",
                character_count=len(paragraph),
                word_count=len(paragraph.split()),
                is_empty=False,
                needs_ocr=False,
            )
        )

    chunks = chunk_page_records(pages, target_tokens=200, overlap_tokens=30)

    assert len(chunks) > 1
    # Verify sequential chunk indices
    for i, c in enumerate(chunks):
        assert c.chunk_index == i
        assert c.token_count > 0

    # Verify overlap: consecutive chunks share trailing/leading sentences/text
    first_chunk_words = set(chunks[0].text.split())
    second_chunk_words = set(chunks[1].text.split())
    shared_words = first_chunk_words.intersection(second_chunk_words)
    assert len(shared_words) > 0


def test_chunking_empty_and_noise_text() -> None:
    """Test filtering out empty pages and noise text."""
    p_empty = ParsedPage(
        document_id="EMPTY__2025__report__tr",
        page_id="EMPTY__2025__report__tr_p1",
        source_path="/path/empty.pdf",
        filename="EMPTY__2025__report__tr.pdf",
        file_hash="000000",
        ticker="THYAO",
        year=2025,
        report_type="annual_report",
        language="tr",
        page_number=1,
        total_pages=1,
        text="   \n\x00   ",
        character_count=0,
        word_count=0,
        is_empty=True,
        needs_ocr=True,
    )

    chunks = chunk_page_records([p_empty], target_tokens=500)
    assert len(chunks) == 0


def test_chunk_document_file_and_directory(tmp_path: Path) -> None:
    """Test chunking file and directory processing with JSONL output."""
    pages_dir = tmp_path / "pages"
    ticker_dir = pages_dir / "AKBNK"
    ticker_dir.mkdir(parents=True)

    page_file = ticker_dir / "AKBNK__2024__annual_report__tr.jsonl"
    p1 = ParsedPage(
        document_id="AKBNK__2024__annual_report__tr",
        page_id="AKBNK__2024__annual_report__tr_p1",
        source_path="/path/akbank.pdf",
        filename="AKBNK__2024__annual_report__tr.pdf",
        file_hash="hash123",
        ticker="AKBNK",
        year=2024,
        report_type="annual_report",
        language="tr",
        page_number=1,
        total_pages=1,
        text="Akbank 2024 yılı finansal tablolar açıklaması. " * 20,
        character_count=500,
        word_count=80,
        is_empty=False,
        needs_ocr=False,
    )

    with open(page_file, "w", encoding="utf-8") as f:
        f.write(p1.model_dump_json() + "\n")

    chunks_out = tmp_path / "chunks"

    # Test single file chunking
    chunks = chunk_document_file(page_file, output_dir=chunks_out, overwrite=True)
    assert len(chunks) >= 1

    expected_chunk_jsonl = chunks_out / "AKBNK" / "AKBNK__2024__annual_report__tr_chunks.jsonl"
    assert expected_chunk_jsonl.exists()

    with open(expected_chunk_jsonl, encoding="utf-8") as f:
        line = f.readline()
        record = ChunkRecord.model_validate_json(line)
        assert record.ticker == "AKBNK"

    # Test directory batch chunking
    summary = chunk_document_directory(pages_dir, output_dir=chunks_out, overwrite=True)
    assert summary.total_documents == 1
    assert summary.total_chunks_created >= 1
    assert summary.avg_tokens_per_chunk > 0


def test_cli_chunk_command(tmp_path: Path) -> None:
    """Test CLI chunk command for single file and directory inputs."""
    pages_dir = tmp_path / "pages_cli"
    ticker_dir = pages_dir / "TUPRS"
    ticker_dir.mkdir(parents=True)

    page_file = ticker_dir / "TUPRS__2025__annual_report__tr.jsonl"
    p1 = ParsedPage(
        document_id="TUPRS__2025__annual_report__tr",
        page_id="TUPRS__2025__annual_report__tr_p1",
        source_path="/path/tupras.pdf",
        filename="TUPRS__2025__annual_report__tr.pdf",
        file_hash="tupras123",
        ticker="TUPRS",
        year=2025,
        report_type="annual_report",
        language="tr",
        page_number=1,
        total_pages=1,
        text="Tüpraş 2025 yılı net karı ve üretimi detayları. " * 15,
        character_count=600,
        word_count=90,
        is_empty=False,
        needs_ocr=False,
    )
    with open(page_file, "w", encoding="utf-8") as f:
        f.write(p1.model_dump_json() + "\n")

    chunks_out = tmp_path / "chunks_cli"

    # Test CLI file chunking
    res_file = runner.invoke(app, ["chunk", str(page_file), "--output-dir", str(chunks_out), "--overwrite"])
    assert res_file.exit_code == 0
    assert "Chunking single JSONL file" in res_file.output

    # Test CLI directory chunking
    res_dir = runner.invoke(app, ["chunk", str(pages_dir), "--output-dir", str(chunks_out), "--overwrite"])
    assert res_dir.exit_code == 0
    assert "Directory Chunking Summary" in res_dir.output
