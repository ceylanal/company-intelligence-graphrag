"""Pydantic contracts for Multi-Hop Graph Retrieval, Intent Extraction, and Path Lineage."""

from typing import Any

from pydantic import BaseModel, Field


class GraphQueryIntent(BaseModel):
    """Extracted query intent parameters for parameterized Cypher generation."""

    raw_query: str
    starting_ticker: str | None = Field(default=None, description="Starting BIST company ticker e.g. ASELS")
    starting_entity_ids: list[str] = Field(default_factory=list, description="Explicit starting node IDs")
    target_node_labels: list[str] = Field(
        default_factory=list, description="Target node labels e.g. Product, Sector, FinancialMetric"
    )
    allowed_rel_types: list[str] = Field(
        default_factory=list, description="Allowed relationship types e.g. PRODUCES, OPERATES_IN"
    )
    year_filter: int | None = Field(default=None, description="Year filter e.g. 2024")
    metric_name_filter: str | None = Field(default=None, description="Financial metric name filter e.g. ciro")
    max_hops: int = Field(default=2, ge=1, le=3, description="Maximum traversal depth (1 to 3)")
    limit: int = Field(default=10, ge=1, le=50, description="Max path results limit")
    timeout_ms: int = Field(default=5000, description="Query execution timeout limit")


class LineageMetadata(BaseModel):
    """Source grounding metadata retained from graph nodes/edges."""

    chunk_id: str = Field(default="chunk_unknown")
    source_file: str = Field(default="source_unknown.pdf")
    page_number: int = Field(default=1)
    evidence_text: str = Field(default="")


class GraphPathNode(BaseModel):
    """Node entity along a multi-hop graph path."""

    id: str
    label: str
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphPathEdge(BaseModel):
    """Relationship edge along a multi-hop graph path."""

    id: str
    type: str
    source_id: str
    target_id: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphSearchResult(BaseModel):
    """Single multi-hop graph path search result with relevance score and lineage."""

    path_id: str
    hops: int
    nodes: list[GraphPathNode]
    edges: list[GraphPathEdge]
    relevance_score: float = Field(ge=0, le=1)
    lineage: LineageMetadata = Field(default_factory=LineageMetadata)
    path_summary: str = ""


class GraphSearchResponse(BaseModel):
    """Full response for multi-hop graph search."""

    query: str
    intent: GraphQueryIntent
    results: list[GraphSearchResult] = Field(default_factory=list)
    total_paths_found: int = 0
    execution_time_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)
