"""Vector Researcher Agent for Company Intelligence Multi-Agent System."""


import re

from company_graphrag.agents.contracts import AgentRole
from company_graphrag.agents.researchers.deduplicator import EvidenceDeduplicator
from company_graphrag.agents.researchers.models import ResearcherExecutionResult
from company_graphrag.agents.schema import EvidenceItem, ResearchState, ResearchTaskStep, ToolCallRecord
from company_graphrag.agents.tools.models import VectorSearchInput
from company_graphrag.agents.tools.search_tools import FetchSourceContextTool, VectorSearchTool
from company_graphrag.safety.tool_policy import ToolExecutionContext, ToolPolicy


def build_intent_expansion(query: str, ticker: str | None, company: str | None) -> str | None:
    """Build one bounded, domain-aware retrieval query for fact/relationship intents."""
    lowered = query.casefold()
    subject = company or ticker or "şirket"

    if re.search(r"\b(enerji|energy)\b", lowered) and any(
        phrase in lowered for phrase in ("bağlı ortak", "iştirak", "şirket")
    ):
        terms = "sektörler ve şirketler enerji şirketleri bağlı ortaklıklar iç piyasa pozisyonları"
    elif any(
        phrase in lowered
        for phrase in (
            "ana hissedar",
            "ana ortak",
            "ortaklık yapısı",
            "pay sahibi",
            "sahibi olan",
        )
    ):
        terms = (
            "hakim şirket şirketler topluluğu bağlılık raporu "
            "ortaklık yapısı ana hissedar pay sahipleri"
        )
    elif any(phrase in lowered for phrase in ("hangi yıl", "ne zaman")) and any(
        phrase in lowered for phrase in ("hizmet", "faaliyet", "kurul", "başla")
    ):
        terms = "kuruluş tarihi faaliyetlere başlama tarihçe bir bakışta"
    elif any(
        phrase in lowered
        for phrase in (
            "ortak yatırım",
            "ortak girişim",
            "iştirak",
            "bağlı ortak",
        )
    ):
        terms = "iştirakler bağlı ortaklıklar ortak girişimler ortak yatırımlar faaliyet alanları"
        if "soda" in lowered:
            terms += " kimyasallar doğal soda külü ABD"
    else:
        return None

    return f"{subject} {query} {terms}"


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
        self._tool_policy = ToolPolicy()

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
            top_k=10,
            company=company,
            ticker=ticker,
            year=year,
            report_type=report_type,
        )
        context = ToolExecutionContext(
            agent_role=self.role.value,
            allowed_tickers=frozenset({str(ticker).upper()}) if ticker else frozenset(),
            allowed_companies=frozenset({str(company)}) if company else frozenset(),
        )
        res = self._vector_tool.run(v_input, policy_context=context)

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
            gathered_evidence.extend(item for item in res.data.hits if self._tool_policy.validate_tool_output(item.content))
        else:
            failed_attempts += 1
            warnings.append(f"VectorResearcher: Primary query '{primary_query}' returned 0 hits or failed.")

        # 2. Use one bounded intent expansion for fact/relationship questions.
        # Fall back to the legacy broad query only when the primary search is empty.
        intent_query = build_intent_expansion(primary_query, ticker, company)
        if tool_calls_count < max_tool_calls and (intent_query or not gathered_evidence):
            alt_query = intent_query or f"{ticker or 'Company'} {year or '2024'} finansal göstergeler raporu"
            used_queries.append(alt_query)
            tool_calls_count += 1

            v_input_alt = VectorSearchInput(
                query=alt_query,
                top_k=25 if intent_query else 5,
                company=company,
                ticker=ticker,
                year=year,
                report_type=report_type,
            )
            res_alt = self._vector_tool.run(v_input_alt, policy_context=context)

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
                gathered_evidence.extend(
                    item for item in res_alt.data.hits if self._tool_policy.validate_tool_output(item.content)
                )
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
