"""PDF parsing pipeline using PyMuPDF (fitz) and Pydantic models."""

import hashlib
import re
from pathlib import Path
from typing import Any

import fitz  # type: ignore[import-untyped]
import structlog

from company_graphrag.ingestion.models import ParsedPage, ParseSummary, PDFMetadata

logger = structlog.get_logger(__name__)

DEFAULT_OUTPUT_DIR = Path("data/processed/pages")


def parse_filename_metadata(filename: str) -> tuple[str, int, str, str]:
    """Extract (ticker, year, report_type, language) from standard PDF filename.

    Expected format: {TICKER}__{YEAR}__{REPORT_TYPE}__{LANGUAGE}.pdf
    Example: ASELS__2025__annual_report__tr.pdf
    """
    stem = Path(filename).stem
    parts = stem.split("__")

    if len(parts) >= 4:
        ticker = parts[0].upper()
        try:
            year = int(parts[1])
        except ValueError:
            year = 2025
        report_type = parts[2]
        language = parts[3]
        return ticker, year, report_type, language

    # Fallback heuristic regex matching
    ticker_match = re.search(r"([A-Z]{4,5})", stem)
    ticker = ticker_match.group(1).upper() if ticker_match else "UNKNOWN"

    year_match = re.search(r"(20\d{2})", stem)
    year = int(year_match.group(1)) if year_match else 2025

    return ticker, year, "annual_report", "tr"


def normalize_text(raw_text: str) -> str:
    """Clean and normalize raw extracted page text."""
    if not raw_text:
        return ""
    # Strip null characters and whitespace
    text = raw_text.replace("\x00", "").strip()
    # Normalize multiple space occurrences
    text = re.sub(r"[ \t]+", " ", text)
    # Normalize excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def calculate_file_sha256(file_path: Path) -> str:
    """Calculate SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_pdf_file(
    pdf_path: Path,
    output_dir: Path | None = None,
    overwrite: bool = False,
    ocr_char_threshold: int = 50,
) -> list[ParsedPage]:
    """Parse a single PDF file and save its pages to a JSONL file.

    Args:
        pdf_path: Path to the input PDF file.
        output_dir: Directory where JSONL file will be written.
        overwrite: If True, overwrite existing JSONL output.
        ocr_char_threshold: Character count below which page is marked needs_ocr.

    Returns:
        List of ParsedPage objects extracted from the document.
    """
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists() or not pdf_path.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    ticker, year, report_type, language = parse_filename_metadata(pdf_path.name)
    document_id = pdf_path.stem

    base_out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    target_jsonl = base_out_dir / ticker / f"{document_id}.jsonl"

    if target_jsonl.exists() and not overwrite:
        logger.info("JSONL output already exists, skipping parse", jsonl_path=str(target_jsonl))
        # Load existing JSONL records if available
        pages: list[ParsedPage] = []
        with open(target_jsonl, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    pages.append(ParsedPage.model_validate_json(line))
        return pages

    file_hash = calculate_file_sha256(pdf_path)

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as err:
        logger.error("Failed to open or parse PDF file", pdf_path=str(pdf_path), error=str(err))
        raise RuntimeError(f"Corrupted or unreadable PDF file: {pdf_path}") from err

    try:
        total_pages = doc.page_count
        fitz_meta: dict[str, Any] = dict(doc.metadata) if doc.metadata else {}
        pdf_metadata = PDFMetadata.from_fitz_metadata(fitz_meta)

        pages = []
        for page_idx in range(total_pages):
            page_number = page_idx + 1
            page = doc.load_page(page_idx)
            raw_text = page.get_text("text")
            clean_text = normalize_text(raw_text)

            char_count = len(clean_text)
            word_count = len(clean_text.split()) if clean_text else 0
            is_empty = char_count == 0
            needs_ocr = is_empty or (char_count < ocr_char_threshold)

            page_record = ParsedPage(
                document_id=document_id,
                page_id=f"{document_id}_p{page_number}",
                source_path=str(pdf_path),
                filename=pdf_path.name,
                file_hash=file_hash,
                ticker=ticker,
                year=year,
                report_type=report_type,
                language=language,
                page_number=page_number,
                total_pages=total_pages,
                text=clean_text,
                character_count=char_count,
                word_count=word_count,
                is_empty=is_empty,
                needs_ocr=needs_ocr,
                pdf_metadata=pdf_metadata,
            )
            pages.append(page_record)
    finally:
        doc.close()

    target_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with open(target_jsonl, "w", encoding="utf-8") as f:
        for page_record in pages:
            f.write(page_record.model_dump_json() + "\n")

    logger.info("Successfully parsed PDF pages", pdf=pdf_path.name, total_pages=len(pages), jsonl=str(target_jsonl))
    return pages


def parse_pdf_directory(
    dir_path: Path,
    output_dir: Path | None = None,
    overwrite: bool = False,
    recursive: bool = True,
) -> ParseSummary:
    """Parse all PDF files within a directory safely without halting on error.

    Args:
        dir_path: Directory containing PDF files.
        output_dir: Output root directory for JSONL outputs.
        overwrite: If True, overwrite existing JSONL outputs.
        recursive: If True, search subdirectories recursively.

    Returns:
        ParseSummary object summarizing batch results.
    """
    dir_path = Path(dir_path).resolve()
    if not dir_path.exists() or not dir_path.is_dir():
        raise FileNotFoundError(f"Directory not found: {dir_path}")

    pattern = "**/*.pdf" if recursive else "*.pdf"
    pdf_files = sorted([p for p in dir_path.glob(pattern) if p.is_file()])

    summary = ParseSummary(total_files=len(pdf_files))
    base_out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR

    for pdf_path in pdf_files:
        ticker, _, _, _ = parse_filename_metadata(pdf_path.name)
        document_id = pdf_path.stem
        target_jsonl = base_out_dir / ticker / f"{document_id}.jsonl"

        if target_jsonl.exists() and not overwrite:
            summary.skipped_files += 1
            summary.processed_paths.append(pdf_path)
            continue

        try:
            pages = parse_pdf_file(pdf_path, output_dir=output_dir, overwrite=overwrite)
            summary.succeeded_files += 1
            summary.total_pages += len(pages)
            summary.ocr_needed_pages += sum(1 for p in pages if p.needs_ocr)
            summary.processed_paths.append(pdf_path)
        except Exception as err:
            logger.error("Error parsing PDF in directory scan", file=pdf_path.name, error=str(err))
            summary.failed_files += 1
            summary.errors.append({"file": pdf_path.name, "error": str(err)})

    return summary
