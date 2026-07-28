"""Pydantic contracts for schema-grounded entity and relation extraction."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictExtractionModel(BaseModel):
    """Reject unexpected LLM fields instead of silently accepting them."""

    model_config = ConfigDict(extra="forbid")


class RawEntityCandidate(StrictExtractionModel):
    """Untrusted entity candidate returned by an extraction provider."""

    ref: str = Field(min_length=1, description="Chunk-local reference used by relation candidates")
    type: str = Field(min_length=1, description="Node label; checked against schema.yaml")
    canonical_name: str = Field(min_length=1)
    properties: dict[str, Any] = Field(default_factory=dict)
    source_chunk_id: str = Field(min_length=1)
    source_file: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    evidence_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @field_validator("ref", "type", "canonical_name", "source_chunk_id", "source_file", "evidence_text")
    @classmethod
    def reject_blank_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class RawRelationCandidate(StrictExtractionModel):
    """Untrusted relationship candidate returned by an extraction provider."""

    type: str = Field(min_length=1, description="Relationship type; checked against schema.yaml")
    source_ref: str = Field(min_length=1)
    target_ref: str = Field(min_length=1)
    properties: dict[str, Any] = Field(default_factory=dict)
    source_chunk_id: str = Field(min_length=1)
    source_file: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    evidence_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @field_validator(
        "type",
        "source_ref",
        "target_ref",
        "source_chunk_id",
        "source_file",
        "evidence_text",
    )
    @classmethod
    def reject_blank_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class EntityExtractionRecord(StrictExtractionModel):
    """Accepted, schema-validated entity extraction output."""

    id: str
    type: str
    canonical_name: str
    properties: dict[str, Any]
    source_chunk_id: str
    source_file: str
    page_number: int = Field(ge=1)
    evidence_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    extraction_version: str = Field(min_length=1)


class RelationExtractionRecord(StrictExtractionModel):
    """Accepted, schema-validated relationship extraction output."""

    id: str
    type: str
    source_entity_id: str
    target_entity_id: str
    properties: dict[str, Any]
    source_chunk_id: str
    source_file: str
    page_number: int = Field(ge=1)
    evidence_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    extraction_version: str = Field(min_length=1)


class RejectionReason(StrEnum):
    """Stable, machine-readable rejection categories."""

    CACHE_INVALID = "CACHE_INVALID"
    CHUNK_MODEL_INVALID = "CHUNK_MODEL_INVALID"
    DUPLICATE_REF = "DUPLICATE_REF"
    ENTITY_MODEL_INVALID = "ENTITY_MODEL_INVALID"
    ENTITY_REFERENCE_NOT_FOUND = "ENTITY_REFERENCE_NOT_FOUND"
    EVIDENCE_NOT_IN_CHUNK = "EVIDENCE_NOT_IN_CHUNK"
    LLM_JSON_INVALID = "LLM_JSON_INVALID"
    LLM_SHAPE_INVALID = "LLM_SHAPE_INVALID"
    PROVENANCE_MISMATCH = "PROVENANCE_MISMATCH"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    RELATION_MODEL_INVALID = "RELATION_MODEL_INVALID"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    UNKNOWN_NODE_TYPE = "UNKNOWN_NODE_TYPE"
    UNKNOWN_RELATION_TYPE = "UNKNOWN_RELATION_TYPE"


class RejectionRecord(StrictExtractionModel):
    """Rejected chunk or candidate with a deterministic ID and explicit reason."""

    rejection_id: str
    chunk_id: str | None = None
    record_kind: Literal["chunk", "entity", "relation", "cache"]
    candidate_index: int | None = Field(default=None, ge=0)
    reason_code: RejectionReason
    reason: str
    candidate: Any | None = None
    source_file: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    extraction_version: str


class CachedChunkResult(StrictExtractionModel):
    """Atomic cache payload for one chunk, schema, and extraction version."""

    chunk_id: str
    chunk_fingerprint: str
    schema_version: str
    extraction_version: str
    entities: list[EntityExtractionRecord] = Field(default_factory=list)
    relations: list[RelationExtractionRecord] = Field(default_factory=list)
    rejections: list[RejectionRecord] = Field(default_factory=list)


class ExtractionMetrics(StrictExtractionModel):
    """Run-level metrics requested by the extraction audit."""

    processed_chunks: int = 0
    entity_count: int = 0
    relation_count: int = 0
    rejected_count: int = 0
    entity_type_distribution: dict[str, int] = Field(default_factory=dict)
    relation_type_distribution: dict[str, int] = Field(default_factory=dict)
    average_confidence: float = 0.0
    cache_hits: int = 0
    provider_calls: int = 0


class ExtractionRunResult(StrictExtractionModel):
    """In-memory result and output locations for one pipeline run."""

    metrics: ExtractionMetrics
    entities: list[EntityExtractionRecord]
    relations: list[RelationExtractionRecord]
    rejections: list[RejectionRecord]
    entities_path: Path
    relations_path: Path
    rejections_path: Path
    checkpoint_path: Path
    metrics_path: Path
