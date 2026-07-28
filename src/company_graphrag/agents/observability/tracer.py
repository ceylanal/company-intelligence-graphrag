"""Structured logging, execution tracing, and metrics for multi-agent system."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from company_graphrag.agents.schema import ResearchState


class TraceRecord(BaseModel):
    """Structured audit log record for agent or tool step execution."""

    trace_id: str = Field(default_factory=lambda: f"trc_{uuid.uuid4().hex[:8]}")
    run_id: str = Field(description="Workflow execution run_id")
    workflow_version: str = Field(default="1.0.0", description="Workflow schema version")
    agent_name: str = Field(description="Name or role of agent executing step")
    task_id: str | None = Field(default=None, description="Task step ID if applicable")
    tool_name: str | None = Field(default=None, description="Executed tool name if applicable")
    start_time: str = Field(description="ISO timestamp start")
    end_time: str = Field(description="ISO timestamp end")
    latency_ms: float = Field(description="Execution duration in milliseconds")
    success: bool = Field(default=True, description="Whether step executed successfully")
    retry_count: int = Field(default=0, description="Retry attempt count")
    input_summary: dict[str, Any] = Field(default_factory=dict, description="Compact summary of inputs")
    output_summary: str = Field(default="", description="Compact summary of output result")
    evidence_count: int = Field(default=0, description="Cumulative evidence count")
    citation_count: int = Field(default=0, description="Cumulative citation count")
    error_type: str | None = Field(default=None, description="Error type or message if failed")
    budget_usage: dict[str, Any] = Field(default_factory=dict, description="Current public budget counters")
    state_transition: str = Field(default="", description="Workflow stage transition e.g. PLANNING -> RESEARCHING")


class RunMetrics(BaseModel):
    """Aggregated observability metrics for a completed workflow run."""

    run_id: str = Field(description="Workflow run_id")
    total_duration_ms: float = Field(default=0.0, description="Total execution duration in ms")
    duration_per_agent: dict[str, float] = Field(default_factory=dict, description="Duration per agent role")
    total_tool_calls: int = Field(default=0, description="Total tool calls executed")
    failed_tool_calls: int = Field(default=0, description="Failed tool calls count")
    failed_tool_rate: float = Field(default=0.0, description="Failed tool calls percentage (0-100)")
    total_retries: int = Field(default=0, description="Total retries performed across agents")
    gathered_evidence_count: int = Field(default=0, description="Total deduplicated evidence collected")
    verified_claim_ratio: float = Field(default=0.0, description="Ratio of verified claims over total claims")
    citation_completeness_percent: float = Field(default=100.0, description="Completeness percent score")
    status: str = Field(default="COMPLETED", description="Final workflow completion status")


class AgentTracer:
    """Manages structured execution traces and observability metrics."""

    def __init__(self):
        self._traces: dict[str, list[TraceRecord]] = {}

    def record_event(
        self,
        state: ResearchState,
        agent_name: str,
        task_id: str | None = None,
        tool_name: str | None = None,
        latency_ms: float = 0.0,
        success: bool = True,
        input_params: dict[str, Any] | None = None,
        output_summary: str = "",
        error: str | None = None,
        state_transition: str = "",
    ) -> TraceRecord:
        """Record a structured execution trace event for a run."""
        run_id = state.run_id
        if run_id not in self._traces:
            self._traces[run_id] = []

        now_str = datetime.now().isoformat()
        clean_inputs = {}
        if input_params:
            # Compact inputs to avoid logging raw PDF text bodies
            for k, v in input_params.items():
                if isinstance(v, str) and len(v) > 100:
                    clean_inputs[k] = f"{v[:97]}..."
                else:
                    clean_inputs[k] = v

        record = TraceRecord(
            run_id=run_id,
            workflow_version=state.workflow_version,
            agent_name=agent_name,
            task_id=task_id,
            tool_name=tool_name,
            start_time=now_str,
            end_time=now_str,
            latency_ms=round(latency_ms, 2),
            success=success,
            retry_count=state.retry_count.get(agent_name, 0),
            input_summary=clean_inputs,
            output_summary=output_summary[:200] if output_summary else "",
            evidence_count=len(state.evidence),
            citation_count=len(state.citations),
            error_type=error,
            budget_usage=state.execution_budget.model_dump(),
            state_transition=state_transition,
        )

        self._traces[run_id].append(record)
        return record

    def get_traces(self, run_id: str) -> list[TraceRecord]:
        """Get all trace records for run_id."""
        return self._traces.get(run_id, [])

    def calculate_metrics(self, state: ResearchState) -> RunMetrics:
        """Aggregate execution trace records into RunMetrics summary."""
        records = self.get_traces(state.run_id)
        total_duration = sum(r.latency_ms for r in records)

        duration_per_agent: dict[str, float] = {}
        total_tools = 0
        failed_tools = 0

        for r in records:
            duration_per_agent[r.agent_name] = duration_per_agent.get(r.agent_name, 0.0) + r.latency_ms
            if r.tool_name:
                total_tools += 1
                if not r.success:
                    failed_tools += 1

        failed_rate = round((failed_tools / total_tools * 100.0), 2) if total_tools > 0 else 0.0

        total_retries = sum(state.retry_count.values())
        total_claims = len(state.verified_claims) + len(state.rejected_claims)
        verified_ratio = round(len(state.verified_claims) / total_claims, 2) if total_claims > 0 else 1.0

        return RunMetrics(
            run_id=state.run_id,
            total_duration_ms=round(total_duration, 2),
            duration_per_agent=duration_per_agent,
            total_tool_calls=total_tools,
            failed_tool_calls=failed_tools,
            failed_tool_rate=failed_rate,
            total_retries=total_retries,
            gathered_evidence_count=len(state.evidence),
            verified_claim_ratio=verified_ratio,
            citation_completeness_percent=100.0 if not state.structured_report or not state.structured_report.quality_warnings else 85.0,
            status=state.status.value if hasattr(state.status, "value") else str(state.status),
        )

    def render_run_trace(self, run_id: str) -> str:
        """Render human-readable CLI trace summary table for run_id."""
        records = self.get_traces(run_id)
        if not records:
            return f"No trace records found for run_id: '{run_id}'"

        lines = [
            f"=== 🔍 Agent Execution Trace: run_id='{run_id}' ===",
            f"{'Agent / Role':<20} | {'Task ID':<10} | {'Tool':<18} | {'Latency':<8} | {'Status':<7} | {'Summary'}",
            "-" * 95,
        ]

        for r in records:
            status_str = "OK" if r.success else "ERR"
            tool_str = r.tool_name or "-"
            task_str = r.task_id or "-"
            lines.append(
                f"{r.agent_name:<20} | {task_str:<10} | {tool_str:<18} | {r.latency_ms:>6.1f}ms | {status_str:<7} | {r.output_summary[:25]}"
            )

        lines.append("-" * 95)
        return "\n".join(lines)
