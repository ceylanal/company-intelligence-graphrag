"""Pydantic models for RAG context building, source packaging, answer generation, and pipeline orchestration."""

from pydantic import BaseModel, Field

from company_graphrag.retrieval.models import QueryPlan


class SourceReference(BaseModel):
    """Structured reference for a single source chunk embedded in RAG context."""

    source_number: int = Field(description="1-based index of source block [Source N]")
    chunk_id: str = Field(description="Unique chunk identifier")
    company: str = Field(description="Commercial company name")
    ticker: str = Field(description="Stock ticker symbol")
    year: int = Field(description="Report year")
    report_type: str = Field(default="annual_report", description="Document type")
    page_number: int = Field(description="Primary page number")
    source_file: str = Field(description="Source PDF filename")
    text: str = Field(description="Chunk text snippet")
    retrieval_score: float = Field(description="Cosine similarity score")
    character_count: int = Field(description="Length of text snippet in characters")


class ContextPackage(BaseModel):
    """Complete RAG context package ready for LLM prompt injection."""

    query: str = Field(description="Original search query string")
    formatted_context: str = Field(description="Formatted context string for LLM prompt")
    total_sources: int = Field(description="Number of valid source chunks included")
    total_characters: int = Field(description="Total character count of formatted context")
    excluded_duplicates: int = Field(default=0, description="Count of duplicate chunks filtered out")
    sources: list[SourceReference] = Field(default_factory=list, description="Metadata list of included sources")


class RAGAnswer(BaseModel):
    """Grounded RAG answer payload with citations and source metadata."""

    query: str = Field(description="Original user search query")
    answer: str = Field(description="Grounded LLM answer text")
    citations: list[int] = Field(default_factory=list, description="List of cited source numbers [Source N]")
    sources: list[SourceReference] = Field(
        default_factory=list, description="List of cited or included source references"
    )
    used_source_count: int = Field(description="Count of sources actually cited or used")
    insufficient_context: bool = Field(default=False, description="True if context was insufficient to answer")
    execution_time_ms: float = Field(description="Total generation duration in milliseconds")
    llm_provider: str = Field(default="mock", description="LLM provider name")
    llm_model: str = Field(default="mock-v1", description="LLM model identifier")
    fallback_used: bool = Field(default=False, description="True when deterministic safe fallback produced the answer")
    fallback_reason: str | None = Field(default=None, description="Sanitized fallback reason category")


class VectorRAGResult(BaseModel):
    """End-to-end Vector RAG Pipeline execution result payload."""

    query: str = Field(description="Original user search query")
    answer: str = Field(description="Final grounded answer text")
    citations: list[int] = Field(default_factory=list, description="List of validated citation numbers")
    sources: list[SourceReference] = Field(default_factory=list, description="List of cited source references")
    retrieved_count: int = Field(default=0, description="Total number of hits retrieved from Qdrant")
    used_source_count: int = Field(default=0, description="Number of sources actually cited/used in answer")
    insufficient_context: bool = Field(default=False, description="True if context was insufficient")
    execution_time_ms: float = Field(description="Total pipeline execution duration in milliseconds")
    stage_timings_ms: dict[str, float] = Field(default_factory=dict, description="Stage duration breakdown in ms")
    query_plan: QueryPlan | None = Field(default=None, description="Query transformation and entity plan")
    warnings: list[str] = Field(default_factory=list, description="Execution warnings or non-fatal issues")
