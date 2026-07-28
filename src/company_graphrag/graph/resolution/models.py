"""Pydantic contracts for auditable entity resolution and canonicalization."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictResolutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MatchClass(StrEnum):
    """Resolution classes ordered from automatic merge to hard separation."""

    EXACT_MATCH = "EXACT_MATCH"
    HIGH_CONFIDENCE_MATCH = "HIGH_CONFIDENCE_MATCH"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DIFFERENT_ENTITY = "DIFFERENT_ENTITY"


class EntityContext(StrictResolutionModel):
    """Context signals used to prevent name-only merges."""

    company_id: str | None = None
    year: int | None = None
    report_id: str | None = None
    date_id: str | None = None
    scope: str | None = None
    unit: str | None = None
    numeric_value: float | None = None
    model_codes: list[str] = Field(default_factory=list)
    evidence_tokens: list[str] = Field(default_factory=list)


class CanonicalEntityRecord(StrictResolutionModel):
    """One deterministic canonical entity produced from one or more mentions."""

    canonical_id: str
    type: str
    canonical_name: str
    normalized_name: str
    properties: dict[str, Any]
    aliases: list[str]
    source_entity_ids: list[str]
    source_record_keys: list[str]
    source_chunk_ids: list[str]
    report_ids: list[str]
    years: list[int]
    evidence_samples: list[str]
    average_confidence: float = Field(ge=0, le=1)
    resolution_version: str


class AliasRecord(StrictResolutionModel):
    """Auditable mapping from a source mention to a canonical entity."""

    alias_id: str
    source_record_key: str
    source_entity_id: str
    entity_type: str
    alias: str
    normalized_alias: str
    canonical_entity_id: str
    candidate_canonical_id: str | None = None
    match_class: MatchClass
    auto_merged: bool
    source_chunk_id: str
    source_file: str
    page_number: int = Field(ge=1)
    resolution_version: str


class ResolutionDecisionRecord(StrictResolutionModel):
    """Pairwise decision with all positive and conflicting signals retained."""

    decision_id: str
    left_record_key: str
    right_record_key: str
    left_entity_id: str
    right_entity_id: str
    left_name: str
    right_name: str
    entity_type: str
    match_class: MatchClass
    name_similarity: float = Field(ge=0, le=1)
    context_similarity: float = Field(ge=0, le=1)
    signals: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    rationale: str
    merged: bool
    left_canonical_id: str
    right_canonical_id: str
    resolution_version: str


class ResolutionMetrics(StrictResolutionModel):
    input_record_count: int = 0
    canonical_entity_count: int = 0
    merged_record_count: int = 0
    ambiguous_record_count: int = 0
    exact_match_pairs: int = 0
    high_confidence_match_pairs: int = 0
    review_required_pairs: int = 0
    different_entity_pairs: int = 0
    canonical_type_distribution: dict[str, int] = Field(default_factory=dict)


class ResolutionRunResult(StrictResolutionModel):
    metrics: ResolutionMetrics
    canonical_entities: list[CanonicalEntityRecord]
    aliases: list[AliasRecord]
    decisions: list[ResolutionDecisionRecord]
    canonical_entities_path: Path
    aliases_path: Path
    decisions_path: Path
    metrics_path: Path
