"""Models and execution contracts for Researcher Agents."""

from pydantic import BaseModel, Field

from company_graphrag.agents.schema import EvidenceItem


class ResearcherExecutionResult(BaseModel):
    """Output execution payload returned by Vector or Graph Researcher Agent."""

    task_id: str = Field(description="ID of the executed research task step")
    evidence: list[EvidenceItem] = Field(default_factory=list, description="Deduplicated gathered evidence items")
    used_queries: list[str] = Field(default_factory=list, description="List of search queries executed")
    tool_calls_count: int = Field(default=0, ge=0, description="Number of tool executions performed")
    failed_attempts: int = Field(default=0, ge=0, description="Number of failed tool or query attempts")
    warnings: list[str] = Field(default_factory=list, description="Execution warnings or diagnostics")
    retrieval_quality_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Average relevance score of gathered evidence"
    )
    status: str = Field(default="COMPLETED", description="Execution status: COMPLETED, FAILED, NO_RESULTS")
