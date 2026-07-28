"""Pydantic models for semantic search query requests, hit responses, reranking, query transformation, and pipeline execution."""

from pydantic import BaseModel, Field


class QueryPlan(BaseModel):
    """Structured result of query transformation and entity detection."""

    original_query: str = Field(description="Original raw user search query")
    normalized_query: str = Field(description="Normalized lower-cased query text")
    rewritten_query: str = Field(description="Cleaned, expanded standalone search query")
    expanded_queries: list[str] = Field(default_factory=list, description="List of search query variations")
    detected_company: str | None = Field(default=None, description="Auto-detected commercial company name")
    detected_ticker: str | None = Field(default=None, description="Auto-detected stock ticker symbol")
    detected_year: int | None = Field(default=None, description="Auto-detected report year")
    detected_report_type: str | None = Field(default=None, description="Auto-detected document type")
    is_out_of_domain: bool = Field(default=False, description="True if query is out-of-domain or unanswerable")
    warnings: list[str] = Field(
        default_factory=list, description="Transformation warnings or relative date assumptions"
    )


class SearchQuery(BaseModel):
    """Semantic search query parameters."""

    query: str = Field(description="Natural language query string")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of results")
    candidate_k: int = Field(default=20, ge=1, le=100, description="Candidate pool size for reranking")
    score_threshold: float | None = Field(default=None, description="Minimum similarity score cutoff")
    company: str | None = Field(default=None, description="Filter by commercial company name")
    ticker: str | list[str] | None = Field(default=None, description="Filter by stock ticker symbol")
    year: int | list[int] | None = Field(default=None, description="Filter by report year")
    report_type: str | None = Field(default=None, description="Filter by report document type")
    language: str | None = Field(default=None, description="Filter by document language")
    use_reranking: bool = Field(default=False, description="Enable hybrid reranking and diversity selection")
    use_query_rewrite: bool = Field(default=False, description="Enable query rewriting and entity detection")
    use_multi_query: bool = Field(default=False, description="Enable multi-query expansion and RRF fusion")
    max_expanded_queries: int = Field(default=3, ge=1, le=5, description="Maximum expanded queries limit")
    diversity_weight: float = Field(default=0.2, ge=0.0, le=1.0, description="Weight for MMR diversity penalty")


class SearchHit(BaseModel):
    """Single vector search result hit with optional reranking and fusion metadata."""

    chunk_id: str = Field(description="Unique chunk identifier")
    text: str = Field(description="Chunk text content")
    score: float = Field(description="Cosine similarity score or final score")
    company: str = Field(description="Commercial company name")
    ticker: str = Field(description="Stock ticker symbol")
    year: int = Field(description="Report year")
    report_type: str = Field(default="annual_report", description="Document type")
    page_number: int = Field(description="Primary page number")
    source_file: str = Field(description="Source PDF filename")
    document_id: str = Field(default="", description="Canonical document identifier")
    chunk_index: int = Field(default=0, description="Index of chunk within document")
    language: str = Field(default="tr", description="Document language")

    # Reranking Detailed Scores
    original_rank: int | None = Field(default=None, description="1-based candidate pool rank")
    reranked_rank: int | None = Field(default=None, description="1-based rank after reranking")
    vector_score: float | None = Field(default=None, description="Raw normalized vector score")
    lexical_score: float | None = Field(default=None, description="Lexical term overlap score")
    metadata_score: float | None = Field(default=None, description="Metadata match boost score")
    diversity_penalty: float | None = Field(default=None, description="MMR/diversity penalty score")
    final_score: float | None = Field(default=None, description="Combined final score")

    # Fusion Detailed Fields
    matched_queries: list[str] = Field(default_factory=list, description="List of queries that matched this chunk")
    query_count: int = Field(default=0, description="Number of expanded queries that returned this chunk")
    best_original_rank: int | None = Field(default=None, description="Best rank across query candidate lists")
    fusion_score: float | None = Field(default=None, description="RRF (Reciprocal Rank Fusion) score")


class SearchResponse(BaseModel):
    """Response wrapper for semantic search query execution."""

    query: str = Field(description="Original search query string")
    total_hits: int = Field(description="Number of hits returned")
    hits: list[SearchHit] = Field(default_factory=list, description="List of search result hits")
    execution_time_ms: float = Field(description="Query execution duration in milliseconds")
    query_plan: QueryPlan | None = Field(default=None, description="Query transformation plan if enabled")


# Aliases for Vector RAG Retriever Pipeline
RetrievalQueryRequest = SearchQuery
RetrievalHit = SearchHit
RetrievalResponse = SearchResponse
