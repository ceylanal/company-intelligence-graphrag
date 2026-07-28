"""Typed Shared State schema for Company Intelligence Multi-Agent architecture.

Defines the central ResearchState and supporting models for evidence provenance,
claim validation, execution budgeting, and audit logging across agent roles.
"""

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class AgentWorkflowStatus(StrEnum):
    """Execution status of multi-agent research workflow."""

    PENDING = "pending"
    PLANNING = "planning"
    RESEARCHING = "researching"
    VERIFYING = "verifying"
    WRITING = "writing"
    PAUSED = "paused"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class EvidenceItem(BaseModel):
    """Structured evidence record with mandatory source provenance tracking."""

    evidence_id: str = Field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:8]}")
    company: str = Field(description="Commercial company name e.g. Aselsan")
    ticker: str = Field(description="BIST stock ticker e.g. ASELS")
    year: int = Field(description="Report year e.g. 2024")
    report: str = Field(default="annual_report", description="Document type e.g. annual_report, audit_report")
    report_type: str = Field(default="annual_report", description="Document type alias")
    chunk_id: str = Field(description="Unique source chunk identifier")
    page_number: int = Field(ge=1, description="Source page number")
    source_file: str = Field(description="Source PDF filename")
    retrieval_method: str = Field(
        description="Retrieval method used: vector_search, graph_traversal, hybrid_search, multi_hop"
    )
    content: str = Field(default="", description="Raw retrieved text snippet or context path description")
    text: str = Field(default="", description="Text snippet alias")
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Relevance score assigned by retriever")
    graph_path: dict[str, Any] | list[Any] | str | None = Field(
        default=None, description="Path representation for graph search evidence"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional context metadata")
    citation_status: str = Field(
        default="unverified", description="Citation status: unverified, verified, rejected"
    )

    @model_validator(mode="after")
    def validate_provenance_fields(self) -> "EvidenceItem":
        """Ensure critical provenance fields are non-empty and sync text/content and report/report_type."""
        # Sync text and content
        if not self.content and self.text:
            self.content = self.text
        elif not self.text and self.content:
            self.text = self.content

        # Sync report and report_type
        if self.report != "annual_report" and self.report_type == "annual_report":
            self.report_type = self.report
        elif self.report_type != "annual_report" and self.report == "annual_report":
            self.report = self.report_type

        missing = []
        if not self.company or not self.company.strip():
            missing.append("company")
        if not self.ticker or not self.ticker.strip():
            missing.append("ticker")
        if not self.chunk_id or not self.chunk_id.strip():
            missing.append("chunk_id")
        if not self.source_file or not self.source_file.strip():
            missing.append("source_file")
        if not self.retrieval_method or not self.retrieval_method.strip():
            missing.append("retrieval_method")

        if missing:
            raise ValueError(f"EvidenceItem is missing mandatory provenance fields: {', '.join(missing)}")
        return self


class VerifiedClaim(BaseModel):
    """Fact or claim verified by Evidence Verifier / Critic agent."""

    claim_id: str = Field(default_factory=lambda: f"clm_{uuid.uuid4().hex[:8]}")
    claim_text: str = Field(description="Statement or claim extracted from research")
    claim_type: str = Field(default="financial_metric", description="Claim type: financial_metric, operational, relational")
    supporting_evidence_ids: list[str] = Field(
        default_factory=list, description="IDs of evidence items supporting this claim"
    )
    contradicting_evidence_ids: list[str] = Field(
        default_factory=list, description="IDs of evidence items contradicting this claim"
    )
    verification_status: str = Field(
        default="verified",
        description="Status: verified, partially_verified, unsupported, contradicted, ambiguous",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Verification confidence score")
    verification_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Alias for confidence")
    company: str = Field(default="", description="Company name or ticker associated with claim")
    year: int = Field(default=2024, description="Report year associated with claim")
    metric: str | None = Field(default=None, description="Metric name if applicable e.g. ciro")
    value: Any = Field(default=None, description="Numerical or text value extracted")
    unit: str | None = Field(default=None, description="Metric unit e.g. TL, Milyar TL, %")
    warnings: list[str] = Field(default_factory=list, description="Verification warnings or diagnostics")
    required_follow_up: str | None = Field(default=None, description="Topic description for targeted follow-up research")
    verified_by: str = Field(default="Evidence Verifier / Critic", description="Agent role verifying this claim")

    @model_validator(mode="after")
    def sync_confidence(self) -> "VerifiedClaim":
        """Sync confidence and verification_confidence fields."""
        if self.confidence != 1.0 and self.verification_confidence == 1.0:
            self.verification_confidence = self.confidence
        elif self.verification_confidence != 1.0 and self.confidence == 1.0:
            self.confidence = self.verification_confidence
        return self


class RejectedClaim(BaseModel):
    """Claim rejected due to insufficient or ungrounded evidence."""

    claim_id: str = Field(default_factory=lambda: f"rej_{uuid.uuid4().hex[:8]}")
    claim_text: str = Field(description="Rejected claim text")
    reason: str = Field(description="Detailed reason for rejection")
    contradicting_evidence_ids: list[str] = Field(default_factory=list)


class Contradiction(BaseModel):
    """Detected conflict or discrepancy across evidence sources."""

    contradiction_id: str = Field(default_factory=lambda: f"cnt_{uuid.uuid4().hex[:8]}")
    description: str = Field(description="Description of the conflicting statements")
    conflicting_evidence_ids: list[str] = Field(default_factory=list)
    severity: str = Field(default="medium", description="Severity level: low, medium, high, critical")


class CitationItem(BaseModel):
    """Grounded citation mapping for report writing."""

    citation_index: int = Field(ge=1, description="1-based citation index e.g. [1]")
    chunk_id: str = Field(description="Source chunk ID")
    company: str = Field(description="Company name")
    ticker: str = Field(description="Stock ticker")
    year: int = Field(description="Report year")
    source_file: str = Field(description="Source PDF file")
    page_number: int = Field(ge=1, description="Page number")
    retrieval_method: str = Field(description="Retrieval method")
    snippet: str = Field(description="Cited text excerpt")


class ReportOutput(BaseModel):
    """Structured report output payload generated by Citation-First Report Writer Agent."""

    answer: str = Field(description="Full synthesized Markdown research answer text")
    executive_summary: str = Field(default="", description="High-level executive summary paragraph")
    findings: list[str] = Field(default_factory=list, description="Key verified findings")
    comparison: str | None = Field(default=None, description="Comparative synthesis if query is comparison")
    uncertainties: list[str] = Field(default_factory=list, description="Data gaps or uncertainties")
    contradictions: list[str] = Field(default_factory=list, description="Source discrepancies or conflicts")
    citations: list[CitationItem] = Field(default_factory=list, description="Active citation references used in answer")
    evidence_appendix: list[dict[str, Any]] = Field(
        default_factory=list, description="Evidence appendix detailing chunk metadata"
    )
    unanswered_questions: list[str] = Field(
        default_factory=list, description="Aspects or subquestions unable to answer due to missing data"
    )
    quality_warnings: list[str] = Field(
        default_factory=list, description="Warnings generated by citation completeness checker"
    )


class ToolCallRecord(BaseModel):
    """Audit log entry for tool executions by agents."""

    call_id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    agent_role: str = Field(description="Role of the agent invoking the tool")
    tool_name: str = Field(description="Name of the invoked tool")
    input_params: dict[str, Any] = Field(default_factory=dict, description="Inputs passed to tool")
    output_summary: str = Field(default="", description="Summary of tool output")
    execution_time_ms: float = Field(default=0.0, ge=0.0, description="Duration in ms")
    success: bool = Field(default=True, description="True if tool executed without unhandled exception")
    error: str | None = Field(default=None, description="Error message if execution failed")


class ExecutionBudget(BaseModel):
    """Resource budget and loop exhaustion guards for research execution."""

    max_steps: int = Field(default=15, ge=1, le=50, description="Maximum total agent state steps allowed")
    current_step: int = Field(default=0, ge=0, description="Current step index")
    max_retries_per_agent: int = Field(default=3, ge=1, le=10, description="Max retries allowed per agent role")
    max_search_calls: int = Field(default=10, ge=1, le=30, description="Max search tool invocations allowed")
    search_calls_count: int = Field(default=0, ge=0, description="Number of search tool calls executed so far")
    max_tokens: int = Field(default=32000, ge=1000, description="Token budget cap for workflow")
    tokens_used: int = Field(default=0, ge=0, description="Estimated total tokens used")
    max_duration_seconds: float = Field(default=300.0, gt=0)
    max_model_calls: int = Field(default=12, ge=1)
    model_calls_count: int = Field(default=0, ge=0)
    max_input_tokens: int = Field(default=64000, ge=1)
    input_tokens_used: int = Field(default=0, ge=0)
    max_output_tokens: int = Field(default=16000, ge=1)
    output_tokens_used: int = Field(default=0, ge=0)
    max_cost_usd: float | None = Field(default=None, gt=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0)

    def is_exhausted(self) -> bool:
        """Check if any budget limits have been breached."""
        return (
            self.current_step >= self.max_steps
            or self.search_calls_count >= self.max_search_calls
            or self.tokens_used >= self.max_tokens
            or self.model_calls_count >= self.max_model_calls
            or self.input_tokens_used >= self.max_input_tokens
            or self.output_tokens_used >= self.max_output_tokens
            or (self.max_cost_usd is not None and self.estimated_cost_usd >= self.max_cost_usd)
        )

    def increment_step(self) -> int:
        """Increment current step count."""
        self.current_step += 1
        return self.current_step

    def record_search_call(self) -> int:
        """Record a search tool execution."""
        self.search_calls_count += 1
        return self.search_calls_count


class ResearchTaskStep(BaseModel):
    """Structured step within a typed research plan."""

    task_id: str = Field(description="Unique task identifier e.g. task_1")
    question: str = Field(description="Target subquestion natural language string")
    objective: str = Field(default="", description="Specific research objective for this task")
    required_entities: dict[str, Any] = Field(
        default_factory=dict, description="Extracted entities: company, ticker, year, metric"
    )
    retrieval_strategy: str = Field(
        default="vector_search",
        description="Strategy: vector_search, graph_search, hybrid_search",
    )
    required_tools: list[str] = Field(
        default_factory=list, description="Names of tools required e.g. ['vector_search']"
    )
    depends_on: list[str] = Field(default_factory=list, description="Task IDs that must complete before this step")
    priority: int = Field(default=1, ge=1, le=5, description="Priority level: 1 (highest) to 5 (lowest)")
    max_tool_calls: int = Field(default=2, ge=0, le=10, description="Max tool executions allowed for this step")
    expected_evidence: str = Field(default="", description="Description of evidence expected from this step")
    status: str = Field(default="PENDING", description="Task status: PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED")
    retry_count: int = Field(default=0, ge=0, description="Number of retries executed for this task")
    result_summary: str | None = Field(default=None, description="Summary of retrieved evidence for this step")


class ResearchPlan(BaseModel):
    """Typed research plan generated by Planner Agent."""

    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}")
    user_query: str = Field(description="Raw user search query")
    normalized_query: str = Field(description="Cleaned, lowercased, normalized query")
    detected_companies: list[str] = Field(default_factory=list)
    detected_tickers: list[str] = Field(default_factory=list)
    detected_years: list[int] = Field(default_factory=list)
    detected_metrics: list[str] = Field(default_factory=list)
    is_out_of_domain: bool = Field(default=False)
    is_comparison: bool = Field(default=False)
    is_multi_hop: bool = Field(default=False)
    steps: list[ResearchTaskStep] = Field(default_factory=list)
    total_estimated_tool_calls: int = Field(default=0, ge=0)

    def get_ready_tasks(self, completed_task_ids: list[str]) -> list[ResearchTaskStep]:
        """Return PENDING tasks whose dependencies are satisfied."""
        ready: list[ResearchTaskStep] = []
        completed_set = set(completed_task_ids)

        for step in self.steps:
            if step.status != "PENDING" or step.task_id in completed_set:
                continue
            deps_satisfied = all(dep in completed_set for dep in step.depends_on)
            if deps_satisfied:
                ready.append(step)

        return sorted(ready, key=lambda s: (s.priority, s.task_id))

    def validate_dependencies(self) -> bool:
        """Validate that all depends_on references exist and there are no self-dependencies."""
        all_task_ids = {step.task_id for step in self.steps}
        for step in self.steps:
            if step.task_id in step.depends_on:
                return False
            for dep in step.depends_on:
                if dep not in all_task_ids:
                    return False
        return True


class SubQuestion(BaseModel):
    """Decomposed research subquestion assigned to specific researcher agents."""

    id: str = Field(default_factory=lambda: f"sq_{uuid.uuid4().hex[:8]}")
    question: str = Field(description="Targeted natural language subquestion")
    target_agent: str = Field(description="Target researcher: VECTOR_RESEARCHER or GRAPH_RESEARCHER")
    company: str | None = Field(default=None, description="Filtered company name if applicable")
    ticker: str | None = Field(default=None, description="Filtered ticker if applicable")
    year: int | None = Field(default=None, description="Filtered year if applicable")
    status: str = Field(default="PENDING", description="Status: PENDING, IN_PROGRESS, COMPLETED, FAILED")
    result_summary: str | None = Field(default=None, description="Summary of evidence gathered for subquestion")


class ResearchState(BaseModel):
    """Typed shared state container passed across multi-agent research workflow."""

    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    user_query: str = Field(description="Raw initial search query from user")
    normalized_query: str = Field(default="", description="Cleaned, lowercased, and entity-extracted query")

    # Planning & Tasks
    research_plan: list[str] = Field(default_factory=list, description="Step-by-step plan generated by Planner")
    structured_plan: ResearchPlan | None = Field(
        default=None, description="Typed ResearchPlan object generated by Planner"
    )
    subquestions: list[SubQuestion] = Field(default_factory=list, description="Decomposed subquestions")
    completed_tasks: list[str] = Field(default_factory=list, description="List of task IDs or descriptions completed")
    pending_tasks: list[str] = Field(default_factory=list, description="List of task IDs or descriptions pending")

    # Evidence & Verification
    evidence: list[EvidenceItem] = Field(default_factory=list, description="Gathered evidence with source tracking")
    verified_claims: list[VerifiedClaim] = Field(default_factory=list, description="Claims verified by Evidence Critic")
    rejected_claims: list[RejectedClaim] = Field(default_factory=list, description="Unsubstantiated or rejected claims")
    contradictions: list[Contradiction] = Field(default_factory=list, description="Detected source contradictions")
    citations: list[CitationItem] = Field(default_factory=list, description="Final structured report citations")

    # Diagnostics & Budget
    warnings: list[str] = Field(default_factory=list, description="Execution warnings or warnings log")
    retry_count: dict[str, int] = Field(default_factory=dict, description="Retry count per agent role name")
    tool_calls: list[ToolCallRecord] = Field(default_factory=list, description="Audit log of all tool executions")
    execution_budget: ExecutionBudget = Field(default_factory=ExecutionBudget, description="Resource limits")

    # Output & Status
    workflow_version: str = Field(default="1.0.0", description="Workflow schema version")
    application_version: str = Field(default="0.1.0", description="Application version used for the run")
    prompt_bundle_version: str = Field(default="legacy", description="Prompt bundle used for the run")
    config_hash: str = Field(default="legacy", description="Public critical-configuration hash")
    run_manifest_path: str | None = Field(default=None, description="Public provenance manifest path")
    current_stage: str = Field(default="QUERY_INTAKE", description="Current workflow stage name")
    interrupt_reason: str | None = Field(default=None, description="Reason if workflow is PAUSED for HITL input")
    final_answer: str | None = Field(default=None, description="Grounded multi-agent synthesis report")
    structured_report: ReportOutput | None = Field(
        default=None, description="Typed ReportOutput object generated by Report Writer"
    )
    status: AgentWorkflowStatus = Field(default=AgentWorkflowStatus.PENDING, description="Current workflow status")
    error: str | None = Field(default=None, description="Global failure reason if status is FAILED")

    def record_retry(self, agent_role: str) -> int:
        """Increment retry count for specified agent role and return new count."""
        count = self.retry_count.get(agent_role, 0) + 1
        self.retry_count[agent_role] = count
        return count

    def is_retry_exceeded(self, agent_role: str) -> bool:
        """Check if agent role has exceeded maximum retries allowed by budget."""
        return self.retry_count.get(agent_role, 0) >= self.execution_budget.max_retries_per_agent

    def add_evidence(self, item: EvidenceItem) -> None:
        """Add an evidence item to state."""
        self.evidence.append(item)
