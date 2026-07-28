"""Graph Researcher Agent for Company Intelligence Multi-Agent System."""


from company_graphrag.agents.contracts import AgentRole
from company_graphrag.agents.researchers.deduplicator import EvidenceDeduplicator
from company_graphrag.agents.researchers.models import ResearcherExecutionResult
from company_graphrag.agents.schema import EvidenceItem, ResearchState, ResearchTaskStep, ToolCallRecord
from company_graphrag.agents.tools.models import GraphSearchInput
from company_graphrag.agents.tools.search_tools import GraphSearchTool, InspectCompanyTool


class GraphResearcherAgent:
    """Graph Researcher Agent executing multi-hop Knowledge Graph retrieval subtasks."""

    role = AgentRole.GRAPH_RESEARCHER

    def __init__(
        self,
        graph_search_tool: GraphSearchTool | None = None,
        inspect_company_tool: InspectCompanyTool | None = None,
    ):
        self._graph_tool = graph_search_tool or GraphSearchTool()
        self._inspect_tool = inspect_company_tool or InspectCompanyTool()

    def execute_task(self, step: ResearchTaskStep, state: ResearchState) -> ResearcherExecutionResult:
        """Execute multi-hop graph search task step and add deduplicated evidence to shared state."""
        task_id = step.task_id
        tool_calls_count = 0
        failed_attempts = 0
        used_queries: list[str] = []
        warnings: list[str] = []
        gathered_evidence: list[EvidenceItem] = []

        entities = step.required_entities or {}
        ticker = entities.get("ticker")
        year = entities.get("year")

        primary_query = step.question
        used_queries.append(primary_query)
        tool_calls_count += 1

        g_input = GraphSearchInput(
            starting_ticker=ticker,
            year_filter=year,
            max_hops=2,
            limit=10,
            raw_query=primary_query,
        )
        res = self._graph_tool.run(g_input)

        state.tool_calls.append(
            ToolCallRecord(
                agent_role=self.role.value,
                tool_name=self._graph_tool.name,
                input_params=g_input.model_dump(),
                output_summary=f"Success={res.success}, Paths={res.record_count}",
                execution_time_ms=res.execution_time_ms,
                success=res.success,
                error=res.error_message,
            )
        )
        state.execution_budget.record_search_call()

        if res.success and res.data and res.data.hits:
            gathered_evidence.extend(res.data.hits)
        else:
            failed_attempts += 1
            warnings.append(f"GraphResearcher: Query '{primary_query}' returned 0 paths or failed.")

        # Deduplicate evidence
        deduped_evidence = EvidenceDeduplicator.deduplicate(gathered_evidence)

        quality_score = 0.0
        if deduped_evidence:
            scores = [item.relevance_score for item in deduped_evidence if item.relevance_score is not None]
            quality_score = round(sum(scores) / len(scores), 4) if scores else 0.0

            for ev in deduped_evidence:
                state.add_evidence(ev)

        status = "COMPLETED" if deduped_evidence else "NO_RESULTS"

        return ResearcherExecutionResult(
            task_id=task_id,
            evidence=deduped_evidence,
            used_queries=used_queries,
            tool_calls_count=tool_calls_count,
            failed_attempts=failed_attempts,
            warnings=warnings,
            retrieval_quality_score=quality_score,
            status=status,
        )
