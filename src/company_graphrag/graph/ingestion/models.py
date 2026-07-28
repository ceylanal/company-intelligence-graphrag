"""Pydantic contracts for Neo4j Graph Ingestion, Checkpointing, and Audit Reports."""

from typing import Any

from pydantic import BaseModel, Field


class IngestionEntityItem(BaseModel):
    """Entity item prepared for Neo4j node ingestion."""

    id: str
    type: str = Field(description="Node label e.g. Company, Report, FinancialMetric")
    canonical_name: str
    properties: dict[str, Any] = Field(default_factory=dict)
    source_chunk_id: str
    source_file: str
    page_number: int = Field(ge=1)
    evidence_text: str
    confidence: float = Field(default=1.0, ge=0, le=1)


class IngestionRelationItem(BaseModel):
    """Relationship item prepared for Neo4j edge ingestion."""

    id: str
    type: str = Field(description="Relationship type e.g. PUBLISHED, CONTAINS_METRIC")
    source_id: str
    source_label: str
    target_id: str
    target_label: str
    properties: dict[str, Any] = Field(default_factory=dict)
    source_chunk_id: str
    source_file: str
    page_number: int = Field(ge=1)
    evidence_text: str
    confidence: float = Field(default=1.0, ge=0, le=1)


class IngestionCheckpoint(BaseModel):
    """Checkpoint tracking model for resuming interrupted graph ingestions."""

    completed_entity_ids: set[str] = Field(default_factory=set)
    completed_relation_ids: set[str] = Field(default_factory=set)
    completed_batches: list[int] = Field(default_factory=list)
    last_updated_at: str = ""


class IngestionAuditReport(BaseModel):
    """Summary audit report generated after graph ingestion verification."""

    total_input_entities: int
    total_input_relations: int
    ingested_nodes: int
    ingested_relations: int
    node_counts_by_label: dict[str, int] = Field(default_factory=dict)
    relation_counts_by_type: dict[str, int] = Field(default_factory=dict)
    orphan_node_count: int = 0
    duplicate_merge_attempts: int = 0
    execution_time_ms: float = 0.0
    status: str = "PASS"
    checkpoint_path: str = ""
    errors: list[str] = Field(default_factory=list)
