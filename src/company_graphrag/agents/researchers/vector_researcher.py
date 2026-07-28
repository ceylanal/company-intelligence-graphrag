"""Vector Researcher Agent for Company Intelligence Multi-Agent System."""


from company_graphrag.agents.contracts import AgentRole
from company_graphrag.agents.researchers.deduplicator import EvidenceDeduplicator
from company_graphrag.agents.researchers.models import ResearcherExecutionResult
from company_graphrag.agents.schema import EvidenceItem, ResearchState, ResearchTaskStep, ToolCallRecord
from company_graphrag.agents.tools.models import VectorSearchInput
from company_graphrag.agents.tools.search_tools import FetchSourceContextTool, VectorSearchTool


class VectorResearcherAgent:
    """Vector Researcher Agent executing dense semantic retrieval subtasks."""

    role = AgentRole.VECTOR_RESEARCHER

    def __init__(
        self,
        vector_search_tool: VectorSearchTool | None = None,
        fetch_context_tool: FetchSourceContextTool | None = None,
    ):
        self._vector_tool = vector_search_tool or VectorSearchTool()
        self._context_tool = fetch_context_tool or FetchSourceContextTool()

    def execute_task(self, step: ResearchTaskStep, state: ResearchState) -> ResearcherExecutionResult:
        """Execute vector search task step and add deduplicated evidence to shared state."""
        task_id = step.task_id
        max_tool_calls = step.max_tool_calls
        tool_calls_count = 0
        failed_attempts = 0
        used_queries: list[str] = []
        warnings: list[str] = []
        gathered_evidence: list[EvidenceItem] = []

        # Extract entities from task step
        entities = step.required_entities or {}
        ticker = entities.get("ticker")
        year = entities.get("year")
        company = entities.get("company")
        report_type = entities.get("report_type")

        # 1. Primary Vector Search Call
        primary_query = step.question
        used_queries.append(primary_query)
        tool_calls_count += 1

        v_input = VectorSearchInput(
            query=primary_query,
            top_k=5,
            company=company,
            ticker=ticker,
            year=year,
            report_type=report_type,
        )
        res = self._vector_tool.run(v_input)

        # Audit log tool call
        state.tool_calls.append(
            ToolCallRecord(
                agent_role=self.role.value,
                tool_name=self._vector_tool.name,
                input_params=v_input.model_dump(),
                output_summary=f"Success={res.success}, Hits={res.record_count}",
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
            warnings.append(f"VectorResearcher: Primary query '{primary_query}' returned 0 hits or failed.")

        # 2. Controlled Query Expansion / Alternative Fallback if 0 hits and budget permits
        if not gathered_evidence and tool_calls_count < max_tool_calls:
            alt_query = f"{ticker or 'Company'} {year or '2024'} finansal göstergeler raporu"
            used_queries.append(alt_query)
            tool_calls_count += 1

            v_input_alt = VectorSearchInput(query=alt_query, top_k=5, ticker=ticker, year=year)
            res_alt = self._vector_tool.run(v_input_alt)

            state.tool_calls.append(
                ToolCallRecord(
                    agent_role=self.role.value,
                    tool_name=self._vector_tool.name,
                    input_params=v_input_alt.model_dump(),
                    output_summary=f"Success={res_alt.success}, Hits={res_alt.record_count}",
                    execution_time_ms=res_alt.execution_time_ms,
                    success=res_alt.success,
                    error=res_alt.error_message,
                )
            )
            state.execution_budget.record_search_call()

            if res_alt.success and res_alt.data and res_alt.data.hits:
                gathered_evidence.extend(res_alt.data.hits)
            else:
                failed_attempts += 1
                warnings.append(f"VectorResearcher: Alternative query '{alt_query}' returned 0 hits.")

        # 3. Deduplicate evidence
        deduped_evidence = EvidenceDeduplicator.deduplicate(gathered_evidence)

        # 4. Calculate quality score and add to shared state
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
