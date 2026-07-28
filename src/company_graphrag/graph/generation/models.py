"""Pydantic contracts for GraphRAG Answer Generation, Context Packaging, and Citations."""

from pydantic import BaseModel, Field


class GraphCitation(BaseModel):
    """Detailed source citation metadata for grounded claims."""

    source_number: int
    company: str | None = None
    ticker: str | None = None
    year: int | None = None
    report_type: str | None = None
    source_file: str = "source_unknown.pdf"
    page_number: int = 1
    chunk_id: str = "chunk_unknown"
    evidence_snippet: str = ""


class GraphRAGAnswer(BaseModel):
    """Structured response model for GraphRAG grounded answer generation."""

    query: str
    short_answer: str = Field(description="Concise executive summary answer")
    detailed_explanation: str = Field(description="Comprehensive grounded explanation with citations")
    used_relationships: list[str] = Field(default_factory=list, description="Graph path traversal relationships used")
    citations: list[GraphCitation] = Field(default_factory=list, description="List of full source citations")
    confidence_level: str = Field(default="HIGH", description="Confidence level: HIGH, MEDIUM, LOW, NONE")
    insufficient_context: bool = Field(default=False, description="True if available sources are insufficient")
    contradictions_found: list[str] = Field(
        default_factory=list, description="Identified conflicting evidence across sources"
    )
    used_source_count: int = 0
    execution_time_ms: float = 0.0
    raw_llm_response: str | None = None
