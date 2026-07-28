"""Pydantic models for PDF metadata and parsed page records."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PDFMetadata(BaseModel):
    """Standard document metadata extracted from a PDF header."""

    title: str | None = None
    author: str | None = None
    subject: str | None = None
    keywords: str | None = None
    creator: str | None = None
    producer: str | None = None
    creation_date: str | None = None
    mod_date: str | None = None

    @classmethod
    def from_fitz_metadata(cls, meta: dict[str, Any] | None) -> "PDFMetadata":
        """Create PDFMetadata instance from PyMuPDF document metadata dict."""
        if not meta:
            return cls()
        return cls(
            title=meta.get("title") or None,
            author=meta.get("author") or None,
            subject=meta.get("subject") or None,
            keywords=meta.get("keywords") or None,
            creator=meta.get("creator") or None,
            producer=meta.get("producer") or None,
            creation_date=meta.get("creationDate") or None,
            mod_date=meta.get("modDate") or None,
        )


class ParsedPage(BaseModel):
    """Schema for a single parsed PDF page JSONL record."""

    document_id: str = Field(description="Canonical document identifier, e.g. stem of filename")
    page_id: str = Field(description="Unique identifier for the page, e.g. {document_id}_p{page_number}")
    source_path: str = Field(description="Absolute string path to source PDF file")
    filename: str = Field(description="PDF filename")
    file_hash: str = Field(description="SHA-256 hash of PDF file")
    ticker: str = Field(description="Stock ticker symbol")
    year: int = Field(description="Report year")
    report_type: str = Field(description="Document type, e.g. annual_report")
    language: str = Field(description="Language code, e.g. tr or en")
    page_number: int = Field(description="1-based page number")
    total_pages: int = Field(description="Total pages in document")
    text: str = Field(description="Normalized text content of page")
    character_count: int = Field(description="Number of characters in page text")
    word_count: int = Field(description="Number of words in page text")
    is_empty: bool = Field(description="True if page contains no text")
    needs_ocr: bool = Field(description="True if page has no extractable text or falls below threshold")
    pdf_metadata: PDFMetadata = Field(default_factory=PDFMetadata, description="Standard PDF header metadata")


class ParseSummary(BaseModel):
    """Summary of batch PDF parsing operation."""

    total_files: int = 0
    succeeded_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    total_pages: int = 0
    ocr_needed_pages: int = 0
    processed_paths: list[Path] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)
