"""Document chunking engine for converting page JSONL files into text chunk JSONL records."""

from pathlib import Path

import structlog

from company_graphrag.chunking.models import ChunkRecord, ChunkSummary
from company_graphrag.chunking.text_splitter import (
    TextBlock,
    compute_deterministic_chunk_id,
    generate_chunks_from_blocks,
    split_text_into_blocks,
)
from company_graphrag.ingestion.models import ParsedPage

logger = structlog.get_logger(__name__)

DEFAULT_PAGES_DIR = Path("data/processed/pages")
DEFAULT_CHUNKS_DIR = Path("data/processed/chunks")

COMPANY_NAME_MAP = {
    "AKBNK": "Akbank T.A.Ş.",
    "ARCLK": "Arçelik A.Ş.",
    "ASELS": "Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
    "FROTO": "Ford Otomotiv Sanayi A.Ş.",
    "KCHOL": "Koç Holding A.Ş.",
    "MGROS": "Migros Ticaret A.Ş.",
    "SISE": "Türkiye Şişe ve Cam Fabrikaları A.Ş.",
    "TCELL": "Turkcell İletişim Hizmetleri A.Ş.",
    "THYAO": "Türk Hava Yolları A.O.",
    "TUPRS": "Türkiye Petrol Rafinerileri A.Ş.",
}


def get_company_name(ticker: str) -> str:
    """Resolve full commercial company name from ticker symbol."""
    return COMPANY_NAME_MAP.get(ticker.upper(), ticker.upper())


def chunk_page_records(
    page_records: list[ParsedPage],
    target_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[ChunkRecord]:
    """Chunk a list of document page records into ChunkRecord instances."""
    if not page_records:
        return []

    first_page = page_records[0]
    document_id = first_page.document_id
    ticker = first_page.ticker
    year = first_page.year
    report_type = first_page.report_type
    language = first_page.language
    source_file = first_page.filename
    company = get_company_name(ticker)

    # Collect all blocks across pages
    all_blocks: list[TextBlock] = []
    for page in page_records:
        if page.text and not page.is_empty:
            blocks = split_text_into_blocks(page.text, page.page_number)
            all_blocks.extend(blocks)

    if not all_blocks:
        return []

    raw_chunks = generate_chunks_from_blocks(all_blocks, target_tokens=target_tokens, overlap_tokens=overlap_tokens)

    chunk_records: list[ChunkRecord] = []
    for idx, c_data in enumerate(raw_chunks):
        c_id = compute_deterministic_chunk_id(document_id, idx, c_data.text)
        record = ChunkRecord(
            chunk_id=c_id,
            document_id=document_id,
            company=company,
            ticker=ticker,
            year=year,
            report_type=report_type,
            language=language,
            page_number=c_data.page_number,
            chunk_index=idx,
            text=c_data.text,
            token_count=c_data.token_count,
            source_file=source_file,
        )
        chunk_records.append(record)

    return chunk_records


def chunk_document_file(
    jsonl_page_path: Path,
    output_dir: Path | None = None,
    target_tokens: int = 500,
    overlap_tokens: int = 50,
    overwrite: bool = False,
) -> list[ChunkRecord]:
    """Process a single document page JSONL file into chunk JSONL records.

    Args:
        jsonl_page_path: Path to input page JSONL file.
        output_dir: Root output directory for chunk JSONL files.
        target_tokens: Target token count per chunk.
        overlap_tokens: Overlap token count between consecutive chunks.
        overwrite: If True, overwrite existing chunk output file.

    Returns:
        List of generated ChunkRecord objects.
    """
    jsonl_page_path = Path(jsonl_page_path).resolve()
    if not jsonl_page_path.exists() or not jsonl_page_path.is_file():
        raise FileNotFoundError(f"Page JSONL file not found: {jsonl_page_path}")

    # Read page records
    page_records: list[ParsedPage] = []
    with open(jsonl_page_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                page_records.append(ParsedPage.model_validate_json(line))

    if not page_records:
        return []

    ticker = page_records[0].ticker
    document_id = page_records[0].document_id

    base_out_dir = Path(output_dir) if output_dir else DEFAULT_CHUNKS_DIR
    target_chunk_jsonl = base_out_dir / ticker / f"{document_id}_chunks.jsonl"

    if target_chunk_jsonl.exists() and not overwrite:
        logger.info("Chunk JSONL file already exists, skipping", path=str(target_chunk_jsonl))
        existing_chunks: list[ChunkRecord] = []
        with open(target_chunk_jsonl, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    existing_chunks.append(ChunkRecord.model_validate_json(line))
        return existing_chunks

    chunk_records = chunk_page_records(page_records, target_tokens=target_tokens, overlap_tokens=overlap_tokens)

    # Atomic write to target JSONL file
    target_chunk_jsonl.parent.mkdir(parents=True, exist_ok=True)
    temp_jsonl = target_chunk_jsonl.with_suffix(".tmp")
    with open(temp_jsonl, "w", encoding="utf-8") as f:
        for record in chunk_records:
            f.write(record.model_dump_json() + "\n")
    temp_jsonl.replace(target_chunk_jsonl)

    logger.info(
        "Successfully chunked document",
        doc=document_id,
        chunks=len(chunk_records),
        jsonl=str(target_chunk_jsonl),
    )
    return chunk_records


def chunk_document_directory(
    pages_dir: Path,
    output_dir: Path | None = None,
    target_tokens: int = 500,
    overlap_tokens: int = 50,
    overwrite: bool = False,
    recursive: bool = True,
) -> ChunkSummary:
    """Process all page JSONL files in a directory safely without halting on error."""
    pages_dir = Path(pages_dir).resolve()
    if not pages_dir.exists() or not pages_dir.is_dir():
        raise FileNotFoundError(f"Page directory not found: {pages_dir}")

    pattern = "**/*.jsonl" if recursive else "*.jsonl"
    jsonl_files = sorted([p for p in pages_dir.glob(pattern) if p.is_file()])

    summary = ChunkSummary(total_documents=len(jsonl_files))
    base_out_dir = Path(output_dir) if output_dir else DEFAULT_CHUNKS_DIR

    all_token_counts: list[int] = []

    for page_file in jsonl_files:
        document_id = page_file.stem
        # Extract ticker from path or parent folder
        ticker = page_file.parent.name
        target_chunk_jsonl = base_out_dir / ticker / f"{document_id}_chunks.jsonl"

        if target_chunk_jsonl.exists() and not overwrite:
            summary.skipped_documents += 1
            summary.processed_paths.append(page_file)
            try:
                chunks = chunk_document_file(
                    page_file,
                    output_dir=output_dir,
                    target_tokens=target_tokens,
                    overlap_tokens=overlap_tokens,
                    overwrite=False,
                )
                summary.total_chunks_created += len(chunks)
                for c in chunks:
                    all_token_counts.append(c.token_count)
            except Exception:
                pass
            continue

        try:
            chunks = chunk_document_file(
                page_file,
                output_dir=output_dir,
                target_tokens=target_tokens,
                overlap_tokens=overlap_tokens,
                overwrite=overwrite,
            )
            summary.total_pages_processed += len(chunks)  # Tracked
            summary.total_chunks_created += len(chunks)
            summary.processed_paths.append(page_file)

            for c in chunks:
                all_token_counts.append(c.token_count)

        except Exception as err:
            logger.error("Error chunking document file", file=page_file.name, error=str(err))
            summary.failed_documents += 1
            summary.errors.append({"file": page_file.name, "error": str(err)})

    if all_token_counts:
        summary.min_tokens = min(all_token_counts)
        summary.max_tokens = max(all_token_counts)
        summary.avg_tokens_per_chunk = round(sum(all_token_counts) / len(all_token_counts), 2)

    return summary
