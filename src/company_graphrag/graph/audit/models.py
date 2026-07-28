"""Pydantic contracts for Graph Quality Audit, Repairing, and Reporting."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IssueSeverity(StrEnum):
    """Severity levels for audit findings."""

    CRITICAL = "CRITICAL"  # Dangling relations, schema breaking
    WARNING = "WARNING"  # Missing grounding metadata, orphan nodes, low confidence
    INFO = "INFO"  # Formatting style recommendations


class IssueCategory(StrEnum):
    """Categorized graph quality check types."""

    DUPLICATE_NODE = "DUPLICATE_NODE"
    DUPLICATE_RELATION = "DUPLICATE_RELATION"
    DANGLING_RELATION = "DANGLING_RELATION"
    ORPHAN_NODE = "ORPHAN_NODE"
    MISSING_GROUNDING = "MISSING_GROUNDING"
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    INVALID_PROPERTY = "INVALID_PROPERTY"
    CONFLICTING_DATA = "CONFLICTING_DATA"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class AuditIssue(BaseModel):
    """Individual graph quality anomaly record."""

    issue_id: str
    category: IssueCategory
    severity: IssueSeverity
    item_id: str
    item_type: str  # Node label or Rel type
    description: str
    details: dict[str, Any] = Field(default_factory=dict)
    auto_repairable: bool = False
    repaired: bool = False


class GraphQualityMetrics(BaseModel):
    """Summary metrics of knowledge graph health."""

    total_nodes: int = 0
    total_relations: int = 0
    duplicate_nodes_count: int = 0
    duplicate_relations_count: int = 0
    dangling_relations_count: int = 0
    orphan_nodes_count: int = 0
    missing_grounding_count: int = 0
    schema_violations_count: int = 0
    invalid_properties_count: int = 0
    conflicting_data_count: int = 0
    low_confidence_count: int = 0
    overall_quality_score: float = 100.0
    status: str = "PASS"


class GraphQualityReport(BaseModel):
    """Comprehensive graph quality audit report."""

    audit_date: str
    metrics: GraphQualityMetrics
    issues: list[AuditIssue] = Field(default_factory=list)
    human_review_required_count: int = 0
    repairable_count: int = 0


class RepairSummary(BaseModel):
    """Summary report of automated repair actions."""

    repaired_issues_count: int = 0
    dangling_relations_removed: int = 0
    missing_grounding_patched: int = 0
    low_confidence_tagged: int = 0
    human_review_queue_path: str = ""
