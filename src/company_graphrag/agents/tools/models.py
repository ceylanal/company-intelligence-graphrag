"""Typed input and output Pydantic contracts for Agent Tools."""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from company_graphrag.agents.schema import EvidenceItem


# --- 1. vector_search ---
class VectorSearchInput(BaseModel):
    """Input parameters for vector_search tool."""

    query: str = Field(description="Search query string")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of hits to return")
    company: str | None = Field(default=None, description="Optional company name filter")
    ticker: str | None = Field(default=None, description="Optional stock ticker filter e.g. ASELS")
    year: int | None = Field(default=None, description="Optional report year filter e.g. 2024")
    report_type: str | None = Field(default=None, description="Optional document report type filter")
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0, description="Similarity score cutoff")

    @field_validator("top_k", mode="before")
    @classmethod
    def clamp_top_k(cls, v: Any) -> Any:
        if isinstance(v, int) and v > 50:
            return 50
        return v


class VectorSearchOutput(BaseModel):
    """Output results from vector_search tool."""

    query: str = Field(description="Original search query")
    hits: list[EvidenceItem] = Field(default_factory=list, description="Retrieved evidence items sorted by score")
    total_hits: int = Field(default=0, ge=0, description="Total matching chunks found")


# --- 2. graph_search ---
class GraphSearchInput(BaseModel):
    """Input parameters for graph_search tool."""

    starting_ticker: str | None = Field(default=None, description="Starting BIST company ticker e.g. ASELS")
    starting_entity_ids: list[str] = Field(default_factory=list, description="Explicit starting graph node IDs")
    target_node_labels: list[str] = Field(default_factory=list, description="Target entity node labels e.g. Product")
    year_filter: int | None = Field(default=None, description="Report year filter e.g. 2024")
    max_hops: int = Field(default=2, ge=1, le=3, description="Traversal depth limit (1 to 3)")
    limit: int = Field(default=10, ge=1, le=50, description="Max paths to return")
    raw_query: str | None = Field(default=None, description="Optional raw question for Cypher intent extraction")

    @field_validator("limit", mode="before")
    @classmethod
    def clamp_limit(cls, v: Any) -> Any:
        if isinstance(v, int) and v > 50:
            return 50
        return v


class GraphSearchOutput(BaseModel):
    """Output results from graph_search tool."""

    query: str = Field(default="", description="Original query or generated intent")
    hits: list[EvidenceItem] = Field(default_factory=list, description="Evidence items derived from graph paths")
    paths_found: int = Field(default=0, ge=0, description="Number of graph paths retrieved")


# --- 3. hybrid_search ---
class HybridSearchInput(BaseModel):
    """Input parameters for hybrid_search tool."""

    query: str = Field(description="Search query string")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum combined hits")
    company: str | None = Field(default=None, description="Optional company filter")
    ticker: str | None = Field(default=None, description="Optional ticker filter")
    year: int | None = Field(default=None, description="Optional year filter")
    report_type: str | None = Field(default=None, description="Optional report type filter")
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0, description="Vector search RRF weight")
    graph_weight: float = Field(default=0.5, ge=0.0, le=1.0, description="Graph search RRF weight")


class HybridSearchOutput(BaseModel):
    """Output results from hybrid_search tool."""

    query: str = Field(description="Original search query")
    hits: list[EvidenceItem] = Field(default_factory=list, description="Fused evidence items from vector & graph")
    total_hits: int = Field(default=0, ge=0, description="Total fused hits count")


# --- 4. fetch_chunk ---
class FetchChunkInput(BaseModel):
    """Input parameter for fetch_chunk tool."""

    chunk_id: str = Field(description="Unique chunk identifier e.g. chk_12345")


class FetchChunkOutput(BaseModel):
    """Output result from fetch_chunk tool."""

    chunk_id: str = Field(description="Requested chunk ID")
    evidence: EvidenceItem | None = Field(default=None, description="Evidence item if found")
    found: bool = Field(default=False, description="True if chunk exists")


# --- 5. fetch_source_context ---
class FetchSourceContextInput(BaseModel):
    """Input parameters for fetch_source_context tool."""

    chunk_id: str = Field(description="Target chunk ID")
    window: int = Field(default=1, ge=1, le=5, description="Number of preceding and succeeding chunks to fetch")


class FetchSourceContextOutput(BaseModel):
    """Output result from fetch_source_context tool."""

    target_chunk_id: str = Field(description="Target chunk ID")
    target_chunk: EvidenceItem | None = Field(default=None, description="Target evidence item")
    surrounding_chunks: list[EvidenceItem] = Field(default_factory=list, description="Context window chunks")
    combined_text: str = Field(default="", description="Concatenated text snippet of target + window chunks")


# --- 6. validate_citation ---
class ValidateCitationInput(BaseModel):
    """Input parameters for validate_citation tool."""

    citation_text: str = Field(description="Statement or sentence containing citation e.g. Cirosu 120B TL'dir.")
    claimed_source_number: int = Field(ge=1, description="Claimed source index e.g. 1 for [Source 1]")
    cited_chunk_id: str = Field(description="Chunk ID being cited")
    available_sources: list[EvidenceItem] = Field(default_factory=list, description="List of active state evidence")


class ValidateCitationOutput(BaseModel):
    """Output result from validate_citation tool."""

    is_valid: bool = Field(description="True if citation is grounded in available evidence")
    citation_status: str = Field(description="Status: verified, rejected, unverified")
    reason: str = Field(description="Detailed verification explanation")
    matched_evidence: EvidenceItem | None = Field(default=None, description="Matching evidence item if verified")


# --- 7. inspect_company ---
class InspectCompanyInput(BaseModel):
    """Input parameters for inspect_company tool."""

    ticker: str = Field(description="BIST stock ticker symbol e.g. ASELS")
    company_name: str | None = Field(default=None, description="Optional commercial company name")


class InspectCompanyOutput(BaseModel):
    """Output result from inspect_company tool."""

    ticker: str = Field(description="Stock ticker symbol")
    company_name: str = Field(description="Canonical commercial company name")
    available_years: list[int] = Field(default_factory=list, description="List of report years available")
    total_chunks: int = Field(default=0, ge=0, description="Total vector chunks stored")
    graph_node_count: int = Field(default=0, ge=0, description="Total knowledge graph nodes for company")
    graph_relations: list[str] = Field(default_factory=list, description="Types of relationships present")


# --- 8. inspect_report ---
class InspectReportInput(BaseModel):
    """Input parameters for inspect_report tool."""

    ticker: str = Field(description="BIST stock ticker symbol e.g. ASELS")
    year: int = Field(description="Report year e.g. 2024")
    report_type: str = Field(default="annual_report", description="Document type e.g. annual_report")


class InspectReportOutput(BaseModel):
    """Output result from inspect_report tool."""

    ticker: str = Field(description="Stock ticker symbol")
    year: int = Field(description="Report year")
    report_type: str = Field(description="Report type")
    source_file: str = Field(default="", description="Source PDF filename")
    total_pages: int = Field(default=1, ge=1, description="Total pages in report")
    chunk_count: int = Field(default=0, ge=0, description="Total chunks indexed for this report")
    sections_summary: list[str] = Field(default_factory=list, description="Key sections or topic headings present")
