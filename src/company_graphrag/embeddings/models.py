"""Pydantic models for embedding configuration and ingestion statistics."""

from pydantic import BaseModel, Field


class EmbeddingConfig(BaseModel):
    """Configuration for vector embedding generation and Qdrant storage."""

    model_name: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        description="FastEmbed / HuggingFace model name",
    )
    vector_size: int = Field(default=384, description="Vector dimension size")
    distance: str = Field(default="Cosine", description="Vector distance metric (Cosine, Dot, Euclid)")
    batch_size: int = Field(default=64, description="Batch size for embedding generation and Qdrant upsert")
    collection_name: str = Field(default="company_documents", description="Target Qdrant collection name")


class IngestionSummary(BaseModel):
    """Summary metrics of vector embedding and Qdrant upsert pipeline."""

    total_chunks: int = 0
    total_points_upserted: int = 0
    collection_name: str = ""
    vector_size: int = 384
    batch_size: int = 64
    duration_seconds: float = 0.0
    skipped_chunks: int = 0
    failed_chunks: int = 0
    errors: list[dict[str, str]] = Field(default_factory=list)
