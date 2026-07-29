"""End-to-end embedding generation and Qdrant ingestion pipeline."""

import time
import uuid
from pathlib import Path
from typing import Any

import structlog
from qdrant_client.models import PointStruct

from company_graphrag.chunking.models import ChunkRecord
from company_graphrag.config import settings
from company_graphrag.embeddings.encoder import TextEmbeddingEncoder
from company_graphrag.embeddings.models import EmbeddingConfig, IngestionSummary
from company_graphrag.storage.qdrant import QdrantVectorStore

logger = structlog.get_logger(__name__)

DEFAULT_CHUNKS_DIR = Path("data/processed/chunks")


def generate_deterministic_point_id(chunk_id: str) -> str:
    """Generate a deterministic UUID string from chunk_id for Qdrant point indexing."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))


def embed_and_ingest_chunks(
    input_path: Path | str = DEFAULT_CHUNKS_DIR,
    config: EmbeddingConfig | None = None,
    dry_run: bool = False,
    reset_collection: bool = False,
    mock_encoder: bool = False,
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
) -> IngestionSummary:
    """Read chunk records from JSONL, generate embeddings, and load into Qdrant.

    Args:
        input_path: Path to chunk JSONL file or directory containing chunks.
        config: EmbeddingConfig instance.
        dry_run: If True, simulate batch pipeline without connecting or writing.
        reset_collection: If True, delete and recreate Qdrant collection first.
        mock_encoder: If True, use deterministic mock vectors for testing.
        qdrant_url: Override Qdrant connection URL.
        qdrant_api_key: Override Qdrant API key.

    Returns:
        IngestionSummary object with execution statistics.
    """
    start_time = time.time()
    cfg = config or EmbeddingConfig()
    input_path = Path(input_path).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input chunk path not found: {input_path}")

    # Discover chunk files
    if input_path.is_file():
        chunk_files = [input_path]
    else:
        chunk_files = sorted([p for p in input_path.glob("**/*_chunks.jsonl") if p.is_file()])

    # Read all chunk records
    all_chunks: list[ChunkRecord] = []
    for cf in chunk_files:
        with open(cf, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    all_chunks.append(ChunkRecord.model_validate_json(line))

    summary = IngestionSummary(
        total_chunks=len(all_chunks),
        collection_name=cfg.collection_name,
        vector_size=cfg.vector_size,
        batch_size=cfg.batch_size,
    )

    if dry_run:
        logger.info(
            "Dry-run mode enabled: skipped embedding and Qdrant ingestion",
            total_chunks=len(all_chunks),
            collection=cfg.collection_name,
        )
        summary.duration_seconds = round(time.time() - start_time, 2)
        return summary

    # Initialize Encoder and Store
    encoder = TextEmbeddingEncoder(model_name=cfg.model_name, mock=mock_encoder)
    store = QdrantVectorStore(url=qdrant_url or settings.effective_qdrant_url, api_key=qdrant_api_key or settings.qdrant_api_key)

    # Ensure Collection exists
    store.ensure_collection(
        collection_name=cfg.collection_name,
        vector_size=encoder.vector_size,
        distance_str=cfg.distance,
        reset=reset_collection,
    )
    summary.vector_size = encoder.vector_size

    # Batch embedding and upsert
    batch_size = cfg.batch_size
    for i in range(0, len(all_chunks), batch_size):
        chunk_batch = all_chunks[i : i + batch_size]
        texts = [c.text for c in chunk_batch]

        try:
            vectors = encoder.embed_texts(texts)

            points: list[PointStruct] = []
            for chunk_rec, vec in zip(chunk_batch, vectors, strict=True):
                point_id = generate_deterministic_point_id(chunk_rec.chunk_id)
                payload: dict[str, Any] = {
                    "chunk_id": chunk_rec.chunk_id,
                    "document_id": chunk_rec.document_id,
                    "company": chunk_rec.company,
                    "ticker": chunk_rec.ticker,
                    "year": chunk_rec.year,
                    "report_type": chunk_rec.report_type,
                    "language": chunk_rec.language,
                    "page_number": chunk_rec.page_number,
                    "chunk_index": chunk_rec.chunk_index,
                    "text": chunk_rec.text,
                    "source_file": chunk_rec.source_file,
                }
                points.append(PointStruct(id=point_id, vector=vec, payload=payload))

            store.upsert_points_batch(collection_name=cfg.collection_name, points=points)
            summary.total_points_upserted += len(points)

        except Exception as err:
            logger.error(
                "Batch embedding / Qdrant upsert failed",
                batch_index=i // batch_size,
                error=str(err),
            )
            summary.failed_chunks += len(chunk_batch)
            summary.errors.append({"batch_start": str(i), "error": str(err)})

    summary.duration_seconds = round(time.time() - start_time, 2)
    logger.info(
        "Successfully finished vector embedding and Qdrant ingestion",
        upserted=summary.total_points_upserted,
        total=summary.total_chunks,
        duration=summary.duration_seconds,
    )
    return summary
