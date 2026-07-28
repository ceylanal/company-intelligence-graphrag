"""Pydantic models for document chunks and chunking summaries."""

from pathlib import Path

from pydantic import BaseModel, Field


class ChunkRecord(BaseModel):
    """Schema for a single text chunk record."""

    chunk_id: str = Field(description="Deterministic and unique chunk identifier")
    document_id: str = Field(description="Canonical document identifier")
    company: str = Field(description="Full commercial company name or ticker")
    ticker: str = Field(description="Stock ticker symbol")
    year: int = Field(description="Report year")
    report_type: str = Field(description="Document type, e.g. annual_report")
    language: str = Field(description="Language code, e.g. tr or en")
    page_number: int = Field(description="Primary page number where chunk starts")
    chunk_index: int = Field(description="0-based index of chunk within document")
    text: str = Field(description="Extracted chunk text content")
    token_count: int = Field(description="Token count of chunk text")
    source_file: str = Field(description="Source PDF filename or path")


class ChunkSummary(BaseModel):
    """Summary of batch document chunking operation."""

    total_documents: int = 0
    total_pages_processed: int = 0
    total_chunks_created: int = 0
    avg_tokens_per_chunk: float = 0.0
    min_tokens: int = 0
    max_tokens: int = 0
    skipped_documents: int = 0
    failed_documents: int = 0
    processed_paths: list[Path] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)
