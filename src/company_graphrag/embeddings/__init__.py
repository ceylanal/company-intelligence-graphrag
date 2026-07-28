"""Embeddings subpackage for dense vector generation and Qdrant ingestion."""

from company_graphrag.embeddings.encoder import TextEmbeddingEncoder
from company_graphrag.embeddings.models import EmbeddingConfig, IngestionSummary
from company_graphrag.embeddings.pipeline import (
    embed_and_ingest_chunks,
    generate_deterministic_point_id,
)

__all__ = [
    "EmbeddingConfig",
    "IngestionSummary",
    "TextEmbeddingEncoder",
    "embed_and_ingest_chunks",
    "generate_deterministic_point_id",
]
