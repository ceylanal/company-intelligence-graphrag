"""Agent contracts and role specifications for Company Intelligence Multi-Agent System.

Defines input/output payloads, tool permission boundaries, forbidden operations,
success/termination criteria, and error policies for all 6 agent roles.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from company_graphrag.agents.schema import (
    CitationItem,
    Contradiction,
    EvidenceItem,
    RejectedClaim,
    SubQuestion,
    VerifiedClaim,
)


class AgentRole(StrEnum):
    """Defined agent roles in the research assistant system."""

    SUPERVISOR = "Supervisor / Orchestrator"
    PLANNER = "Planner"
    VECTOR_RESEARCHER = "Vector Researcher"
    GRAPH_RESEARCHER = "Graph Researcher"
    EVIDENCE_VERIFIER = "Evidence Verifier / Critic"
    REPORT_WRITER = "Report Writer"


class AgentContract(BaseModel):
    """Declarative specification contract governing an individual agent role."""

    role: AgentRole = Field(description="Unique agent role identifier")
    description: str = Field(description="Role overview and primary responsibility")
    allowed_tools: list[str] = Field(
        default_factory=list, description="List of typed tool names this agent is authorized to use"
    )
    forbidden_actions: list[str] = Field(
        default_factory=list, description="Explicitly prohibited operations or direct database access"
    )
    success_criteria: str = Field(description="Conditions required to mark agent task successful")
    termination_criteria: str = Field(description="Stopping rules to prevent infinite loops")
    error_behavior: str = Field(description="Action to take when error or exception occurs")


# --- Agent Specific Input & Output Payload Contracts ---


class SupervisorInput(BaseModel):
    """Input payload for Supervisor / Orchestrator agent."""

    user_query: str = Field(description="Original research question")
    max_steps: int = Field(default=15, description="Maximum allowed workflow steps")


class SupervisorOutput(BaseModel):
    """Output payload for Supervisor / Orchestrator agent."""

    next_agent: AgentRole | None = Field(
        default=None, description="Next agent role to dispatch, or None if terminated"
    )
    is_complete: bool = Field(default=False, description="True if research workflow is complete")
    workflow_status: str = Field(description="Updated AgentWorkflowStatus string")
    reasoning: str = Field(description="Orchestration decision rationale")


class PlannerInput(BaseModel):
    """Input payload for Planner agent."""

    user_query: str = Field(description="User search query")
    normalized_query: str = Field(default="", description="Normalized query")


class PlannerOutput(BaseModel):
    """Output payload for Planner agent."""

    normalized_query: str = Field(description="Cleaned, lowercased, entity-detected query string")
    research_plan: list[str] = Field(description="Step-by-step plan execution steps")
    subquestions: list[SubQuestion] = Field(description="Decomposed subquestions for researchers")


class VectorResearcherInput(BaseModel):
    """Input payload for Vector Researcher agent."""

    subquestion: SubQuestion = Field(description="Target subquestion to research via Vector RAG")
    candidate_k: int = Field(default=20, ge=1, le=50)
    top_k: int = Field(default=5, ge=1, le=20)


class VectorResearcherOutput(BaseModel):
    """Output payload for Vector Researcher agent."""

    subquestion_id: str = Field(description="ID of subquestion researched")
    evidence_items: list[EvidenceItem] = Field(default_factory=list, description="Retrieved evidence items")
    success: bool = Field(default=True)
    summary: str = Field(default="")


class GraphResearcherInput(BaseModel):
    """Input payload for Graph Researcher agent."""

    subquestion: SubQuestion = Field(description="Target subquestion to research via Knowledge Graph")
    max_hops: int = Field(default=2, ge=1, le=3)
    limit: int = Field(default=10, ge=1, le=30)


class GraphResearcherOutput(BaseModel):
    """Output payload for Graph Researcher agent."""

    subquestion_id: str = Field(description="ID of subquestion researched")
    evidence_items: list[EvidenceItem] = Field(default_factory=list, description="Graph path evidence items")
    success: bool = Field(default=True)
    summary: str = Field(default="")


class VerifierInput(BaseModel):
    """Input payload for Evidence Verifier / Critic agent."""

    user_query: str = Field(description="User query")
    evidence: list[EvidenceItem] = Field(default_factory=list, description="All gathered evidence items")


class VerifierOutput(BaseModel):
    """Output payload for Evidence Verifier / Critic agent."""

    verified_claims: list[VerifiedClaim] = Field(default_factory=list, description="Groundable claims")
    rejected_claims: list[RejectedClaim] = Field(default_factory=list, description="Ungrounded claims")
    contradictions: list[Contradiction] = Field(default_factory=list, description="Source conflicts detected")
    sufficient_evidence: bool = Field(description="True if evidence is sufficient to draft final report")
    critique_notes: str = Field(default="", description="Critic feedback for additional research or writing")


class ReportWriterInput(BaseModel):
    """Input payload for Report Writer agent."""

    user_query: str = Field(description="Original user query")
    verified_claims: list[VerifiedClaim] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)


class ReportWriterOutput(BaseModel):
    """Output payload for Report Writer agent."""

    final_report: str = Field(description="Synthesized markdown research report")
    citations: list[CitationItem] = Field(default_factory=list, description="Grounded citations")
    source_coverage_ratio: float = Field(ge=0.0, le=1.0, description="Ratio of verified claims cited")


# --- Registry of Agent Specifications ---

AGENT_CONTRACTS: dict[AgentRole, AgentContract] = {
    AgentRole.SUPERVISOR: AgentContract(
        role=AgentRole.SUPERVISOR,
        description="Coordinates overall workflow execution, state transitions, dispatching, and budget monitoring.",
        allowed_tools=["inspect_state_tool", "update_status_tool"],
        forbidden_actions=[
            "Direct Qdrant database queries",
            "Direct Neo4j Cypher execution",
            "Direct PDF text extraction",
            "Bypassing verifier step before report generation",
        ],
        success_criteria="State status transitions to COMPLETED with a non-empty grounded final answer.",
        termination_criteria="Budget max_steps reached, tokens exhausted, or agent error retry limit exceeded.",
        error_behavior="Log error, set status to FAILED, record global error message, and return cleanly.",
    ),
    AgentRole.PLANNER: AgentContract(
        role=AgentRole.PLANNER,
        description="Analyzes raw user query, normalizes entities, and decomposes problem into targeted subquestions.",
        allowed_tools=["entity_detector_tool", "query_transformation_tool"],
        forbidden_actions=[
            "Direct vector search execution",
            "Direct graph database traversal",
            "Writing final user report",
        ],
        success_criteria="Generates normalized query, non-empty research plan, and typed subquestions.",
        termination_criteria="Plan successfully generated or 1 retry attempted on parse failure.",
        error_behavior="Fallback to single default subquestion matching the normalized user query.",
    ),
    AgentRole.VECTOR_RESEARCHER: AgentContract(
        role=AgentRole.VECTOR_RESEARCHER,
        description="Executes dense semantic retrieval over Qdrant collections to gather textual evidence chunks.",
        allowed_tools=["vector_search_tool", "hybrid_rerank_tool", "vector_search", "fetch_chunk", "fetch_source_context", "inspect_report"],
        forbidden_actions=[
            "Direct instantiate qdrant_client.QdrantClient",
            "Executing Cypher queries",
            "Modifying vector index or collection schema",
        ],
        success_criteria="Retrieves search hits matching subquestion and returns valid EvidenceItems with provenance.",
        termination_criteria="Subquestion processed or max search calls budget reached.",
        error_behavior="Record warning in state, return empty evidence list for failed subquestion, and proceed.",
    ),
    AgentRole.GRAPH_RESEARCHER: AgentContract(
        role=AgentRole.GRAPH_RESEARCHER,
        description="Traverses Neo4j Knowledge Graph to retrieve multi-hop relational evidence paths.",
        allowed_tools=["graph_search_tool", "cypher_intent_tool", "graph_search", "inspect_company", "inspect_report"],
        forbidden_actions=[
            "Direct instantiate neo4j.GraphDatabase driver",
            "Executing raw UNWIND/DELETE Cypher queries",
            "Modifying graph node or relationship data",
        ],
        success_criteria="Retrieves path search results matching subquestion and returns valid EvidenceItems.",
        termination_criteria="Subquestion processed or max search calls budget reached.",
        error_behavior="Record warning in state, return empty graph evidence list, and proceed.",
    ),
    AgentRole.EVIDENCE_VERIFIER: AgentContract(
        role=AgentRole.EVIDENCE_VERIFIER,
        description="Critically audits gathered evidence against claims, detects contradictions, and filters ungrounded statements.",
        allowed_tools=["claim_verifier_tool", "contradiction_detector_tool", "validate_citation"],
        forbidden_actions=[
            "Executing new database searches",
            "Writing final user answer",
            "Removing source provenance fields from evidence",
        ],
        success_criteria="Produces verified_claims list and identifies any contradictions or evidence gaps.",
        termination_criteria="All claims evaluated against evidence pool.",
        error_behavior="Mark all unverified claims as rejected and request supplementary vector search if budget permits.",
    ),
    AgentRole.REPORT_WRITER: AgentContract(
        role=AgentRole.REPORT_WRITER,
        description="Synthesizes verified claims into a cohesive, structured markdown research report with mandatory citations.",
        allowed_tools=["report_formatter_tool", "citation_linker_tool"],
        forbidden_actions=[
            "Invoking vector or graph search tools",
            "Including unverified claims not in verified_claims list",
            "Fabricating citation numbers without matching EvidenceItem",
        ],
        success_criteria="Generates comprehensive markdown final answer with valid inline citations [Source N].",
        termination_criteria="Final report generated and validated against citation integrity check.",
        error_behavior="Generate fallback report using raw verified claims with explicit grounding disclaimer.",
    ),
}
