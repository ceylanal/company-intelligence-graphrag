"""Durable Multi-Agent Research Workflow Orchestrator."""

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from company_graphrag.agents.planner import PlannerAgent
from company_graphrag.agents.researchers import (
    EvidenceDeduplicator,
    GraphResearcherAgent,
    VectorResearcherAgent,
)
from company_graphrag.agents.schema import AgentWorkflowStatus, ResearchState
from company_graphrag.agents.supervisor import SupervisorAgent
from company_graphrag.agents.verifier import EvidenceVerifierAgent
from company_graphrag.agents.workflow.checkpoint import JSONCheckpointSaver
from company_graphrag.agents.writer import ReportWriterAgent
from company_graphrag.config import settings
from company_graphrag.observability.tracing import span
from company_graphrag.safety.agent_limits import AgentLimitError, AgentLimits
from company_graphrag.versioning.manifest import build_run_manifest, save_run_manifest


class WorkflowStage(StrEnum):
    """Workflow execution stage enumeration."""

    QUERY_INTAKE = "QUERY_INTAKE"
    PLANNING = "PLANNING"
    PLAN_VALIDATION = "PLAN_VALIDATION"
    RESEARCH_EXECUTION = "RESEARCH_EXECUTION"
    EVIDENCE_MERGE = "EVIDENCE_MERGE"
    VERIFICATION = "VERIFICATION"
    TARGETED_FOLLOWUP = "TARGETED_FOLLOWUP"
    REPORT_GENERATION = "REPORT_GENERATION"
    FINAL_QUALITY_GATE = "FINAL_QUALITY_GATE"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkflowInterruptReason(StrEnum):
    """Human-In-The-Loop interrupt reason enumeration."""

    AMBIGUOUS_QUERY = "AMBIGUOUS_QUERY"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    HIGH_CONTRADICTIONS = "HIGH_CONTRADICTIONS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    OVERLY_BROAD_PLAN = "OVERLY_BROAD_PLAN"


class ResearchWorkflow:
    """Durable multi-agent research state machine workflow."""

    def __init__(
        self,
        checkpoint_saver: JSONCheckpointSaver | None = None,
        auto_approve_interrupts: bool = True,
        planner: PlannerAgent | None = None,
        supervisor: SupervisorAgent | None = None,
        vector_researcher: VectorResearcherAgent | None = None,
        graph_researcher: GraphResearcherAgent | None = None,
        verifier: EvidenceVerifierAgent | None = None,
        writer: ReportWriterAgent | None = None,
        event_handler: Callable[[str, ResearchState, dict[str, Any]], None] | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
        answer_delta_transformer: Callable[[str, ResearchState], str] | None = None,
    ):
        self.saver = checkpoint_saver or JSONCheckpointSaver(settings.checkpoint_dir)
        self.auto_approve_interrupts = auto_approve_interrupts

        self.planner = planner or PlannerAgent()
        self.supervisor = supervisor or SupervisorAgent()
        self.vector_researcher = vector_researcher or VectorResearcherAgent()
        self.graph_researcher = graph_researcher or GraphResearcherAgent()
        self.verifier = verifier or EvidenceVerifierAgent()
        self.writer = writer or ReportWriterAgent()
        self.event_handler = event_handler
        self.cancellation_requested = cancellation_requested
        self.answer_delta_transformer = answer_delta_transformer
        self.agent_limits = AgentLimits(
            max_tool_calls=10,
            max_agent_steps=15,
            max_duration_seconds=settings.research_max_duration_seconds,
        )

    def _emit(self, event_type: str, state: ResearchState, **payload: Any) -> None:
        """Publish an in-process workflow event without coupling the domain to HTTP."""
        if self.event_handler is not None:
            self.event_handler(event_type, state, payload)

    def _cancel_if_requested(self, state: ResearchState) -> bool:
        """Cooperatively stop between bounded workflow operations."""
        if self.cancellation_requested is None or not self.cancellation_requested():
            return False
        state.status = AgentWorkflowStatus.CANCELLED
        state.current_stage = WorkflowStage.CANCELLED.value
        state.warnings.append(f"Workflow '{state.run_id}' was cancelled by the connected client.")
        self.saver.save_checkpoint(state)
        self._emit(
            "stage",
            state,
            stage=state.current_stage,
            status=state.status.value,
        )
        return True

    def run(self, user_query: str, run_id: str | None = None) -> ResearchState:
        """Start a new durable research workflow execution for user_query."""
        self.agent_limits.restart_timer()
        if run_id:
            try:
                existing = self.saver.load_checkpoint(run_id)
                if existing.user_query != user_query:
                    raise ValueError("Idempotency key is already associated with a different query")
                return existing if existing.status == AgentWorkflowStatus.COMPLETED else self.resume(run_id)
            except Exception as exc:
                from company_graphrag.agents.workflow.checkpoint import CheckpointNotFoundError

                if not isinstance(exc, CheckpointNotFoundError):
                    raise
        state = ResearchState(user_query=user_query)
        if run_id:
            state.run_id = run_id
        manifest = build_run_manifest(state.run_id)
        state.application_version = manifest.application_version
        state.workflow_version = manifest.workflow_version
        state.prompt_bundle_version = manifest.prompt_bundle_version
        state.config_hash = manifest.config_hash
        state.run_manifest_path = str(save_run_manifest(manifest))
        state.status = AgentWorkflowStatus.PENDING
        state.current_stage = WorkflowStage.QUERY_INTAKE.value
        self.saver.save_checkpoint(state)
        self._emit(
            "stage",
            state,
            stage=state.current_stage,
            status=state.status.value,
        )

        return self._execute_from_current_stage(state)

    def resume(self, run_id: str) -> ResearchState:
        """Resume an interrupted or paused workflow execution from last saved checkpoint."""
        self.agent_limits.restart_timer()
        state = self.saver.load_checkpoint(run_id)
        state.evidence = EvidenceDeduplicator.deduplicate(state.evidence)

        if state.status == AgentWorkflowStatus.COMPLETED:
            self.saver.save_checkpoint(state)
            return state
        if state.status == AgentWorkflowStatus.CANCELLED:
            return state

        # If resuming from PAUSED, clear interrupt state and transition to active
        if state.status == AgentWorkflowStatus.PAUSED:
            state.status = AgentWorkflowStatus.RESEARCHING
            state.interrupt_reason = None
            if state.structured_plan is None:
                state.status = AgentWorkflowStatus.FAILED
                state.current_stage = WorkflowStage.FAILED.value
                state.error = "Paused workflow does not contain a resumable validated plan."
                self.saver.save_checkpoint(state)
                return state
            state.current_stage = WorkflowStage.PLAN_VALIDATION.value

        return self._execute_from_current_stage(state)

    def cancel(self, run_id: str) -> ResearchState:
        """Cancel a running or paused workflow execution."""
        state = self.saver.load_checkpoint(run_id)
        state.status = AgentWorkflowStatus.CANCELLED
        state.current_stage = WorkflowStage.CANCELLED.value
        state.warnings.append(f"Workflow '{run_id}' was cancelled by user/system request.")
        self.saver.save_checkpoint(state)
        return state

    def _execute_from_current_stage(self, state: ResearchState) -> ResearchState:
        """Main state machine loop advancing through workflow stages."""
        stage_sequence = [
            WorkflowStage.QUERY_INTAKE,
            WorkflowStage.PLANNING,
            WorkflowStage.PLAN_VALIDATION,
            WorkflowStage.RESEARCH_EXECUTION,
            WorkflowStage.EVIDENCE_MERGE,
            WorkflowStage.VERIFICATION,
            WorkflowStage.TARGETED_FOLLOWUP,
            WorkflowStage.REPORT_GENERATION,
            WorkflowStage.FINAL_QUALITY_GATE,
            WorkflowStage.COMPLETED,
        ]

        current_idx = 0
        for i, st in enumerate(stage_sequence):
            if st.value == state.current_stage:
                current_idx = i
                break

        for st in stage_sequence[current_idx:]:
            if self._cancel_if_requested(state):
                return state
            state.current_stage = st.value

            if st == WorkflowStage.QUERY_INTAKE:
                state.status = AgentWorkflowStatus.PENDING
                self._emit("stage", state, stage=st.value, status=state.status.value)

            elif st == WorkflowStage.PLANNING:
                state.status = AgentWorkflowStatus.PLANNING
                self._emit("stage", state, stage=st.value, status=state.status.value)
                with span(
                    "planner_agent",
                    **{
                        "run.id": state.run_id,
                        "workflow.version": state.workflow_version,
                        "config.hash": state.config_hash,
                    },
                ):
                    plan = self.planner.plan(state.user_query)
                state.normalized_query = plan.normalized_query
                if self._cancel_if_requested(state):
                    return state

                # Check HITL interrupt for ambiguous or out-of-domain query
                if plan.is_out_of_domain:
                    state.status = AgentWorkflowStatus.COMPLETED
                    state.current_stage = WorkflowStage.COMPLETED.value
                    answer = (
                        "### ⚠️ Yetersiz Kanıt Uyarısı\n\n"
                        "Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli kanıt bulunamadı."
                    )
                    if self.answer_delta_transformer:
                        answer = self.answer_delta_transformer(answer, state)
                    state.final_answer = answer
                    self.saver.save_checkpoint(state)
                    self._emit("answer_delta", state, delta=answer)
                    self._emit(
                        "stage",
                        state,
                        stage=state.current_stage,
                        status=state.status.value,
                    )
                    self._emit("workflow_complete", state)
                    return state

                if len(plan.steps) > 5 and not self.auto_approve_interrupts:
                    from company_graphrag.agents.schema import ResearchPlan

                    if isinstance(plan, ResearchPlan):
                        state.structured_plan = plan
                    return self._pause_workflow(state, WorkflowInterruptReason.OVERLY_BROAD_PLAN)
                state.structured_plan = plan
                self._emit("plan", state, plan=plan.model_dump())

            elif st == WorkflowStage.PLAN_VALIDATION:
                self._emit("stage", state, stage=st.value, status=state.status.value)
                self.supervisor.validate_plan(state)

            elif st == WorkflowStage.RESEARCH_EXECUTION:
                state.status = AgentWorkflowStatus.RESEARCHING
                self._emit("stage", state, stage=st.value, status=state.status.value)
                # Execute ready tasks iteratively
                while True:
                    if self._cancel_if_requested(state):
                        return state
                    if state.execution_budget.is_exhausted():
                        if not self.auto_approve_interrupts:
                            return self._pause_workflow(state, WorkflowInterruptReason.BUDGET_EXCEEDED)
                        break

                    ready_tasks = self.supervisor.select_next_tasks(state)
                    if not ready_tasks:
                        break

                    for task_step in ready_tasks:
                        if self._cancel_if_requested(state):
                            return state
                        # Skip if already completed (idempotency)
                        if task_step.task_id in state.completed_tasks:
                            continue

                        try:
                            self.agent_limits.record_agent_step(state)
                            self.agent_limits.check(state)
                        except AgentLimitError as exc:
                            state.status = AgentWorkflowStatus.FAILED
                            state.current_stage = WorkflowStage.FAILED.value
                            state.error = "Agent safety limit reached."
                            state.warnings.append(f"Agent safety limit: {type(exc).__name__}")
                            self.saver.save_checkpoint(state)
                            return state

                        # Execute with appropriate researcher
                        evidence_count_before = len(state.evidence)
                        if "graph_search" in task_step.required_tools:
                            with span("graph_retrieval", **{"run.id": state.run_id}):
                                self.graph_researcher.execute_task(task_step, state)
                        else:
                            with span("vector_retrieval", **{"run.id": state.run_id}):
                                self.vector_researcher.execute_task(task_step, state)

                        state.completed_tasks.append(task_step.task_id)
                        new_evidence = state.evidence[evidence_count_before:]
                        self._emit(
                            "task",
                            state,
                            task_id=task_step.task_id,
                            status=task_step.status,
                            result_summary=task_step.result_summary,
                        )
                        if new_evidence:
                            self._emit(
                                "evidence",
                                state,
                                items=[item.model_dump() for item in state.evidence],
                            )
                        try:
                            self.agent_limits.check(state)
                        except AgentLimitError as exc:
                            state.status = AgentWorkflowStatus.FAILED
                            state.current_stage = WorkflowStage.FAILED.value
                            state.error = "Agent safety limit reached."
                            state.warnings.append(f"Agent safety limit: {type(exc).__name__}")
                            self.saver.save_checkpoint(state)
                            return state

            elif st == WorkflowStage.EVIDENCE_MERGE:
                self._emit("stage", state, stage=st.value, status=state.status.value)
                # Deduplicate evidence to prevent duplicate items upon resume/retry
                with span("hybrid_result_fusion", **{"run.id": state.run_id}):
                    state.evidence = EvidenceDeduplicator.deduplicate(state.evidence)
                self._emit(
                    "evidence",
                    state,
                    items=[item.model_dump() for item in state.evidence],
                )

                if not state.evidence and not self.auto_approve_interrupts:
                    return self._pause_workflow(state, WorkflowInterruptReason.INSUFFICIENT_EVIDENCE)

            elif st == WorkflowStage.VERIFICATION:
                state.status = AgentWorkflowStatus.VERIFYING
                self._emit("stage", state, stage=st.value, status=state.status.value)
                with span("citation_validation", **{"run.id": state.run_id}):
                    self.verifier.verify_research_state(state)

                if len(state.contradictions) >= 2 and not self.auto_approve_interrupts:
                    return self._pause_workflow(state, WorkflowInterruptReason.HIGH_CONTRADICTIONS)

            elif st == WorkflowStage.TARGETED_FOLLOWUP:
                self._emit("stage", state, stage=st.value, status=state.status.value)
                # Check if follow up tasks were requested
                pass

            elif st == WorkflowStage.REPORT_GENERATION:
                state.status = AgentWorkflowStatus.WRITING
                self._emit("stage", state, stage=st.value, status=state.status.value)
                with span("answer_synthesis", **{"run.id": state.run_id}):
                    self.writer.generate_report(
                        state,
                        on_delta=lambda delta: self._emit("answer_delta", state, delta=delta),
                        transform_delta=self.answer_delta_transformer,
                    )
                self._emit(
                    "citations",
                    state,
                    items=[item.model_dump() for item in state.citations],
                )

            elif st == WorkflowStage.FINAL_QUALITY_GATE:
                self._emit("stage", state, stage=st.value, status=state.status.value)
                # Final audit
                pass

            elif st == WorkflowStage.COMPLETED:
                state.status = AgentWorkflowStatus.COMPLETED
                self._emit("stage", state, stage=st.value, status=state.status.value)

            # Save checkpoint after completing each stage
            self.saver.save_checkpoint(state)

        self._emit("workflow_complete", state)
        return state

    def _pause_workflow(self, state: ResearchState, reason: WorkflowInterruptReason) -> ResearchState:
        """Pause workflow execution for Human-In-The-Loop input."""
        state.status = AgentWorkflowStatus.PAUSED
        state.interrupt_reason = reason.value
        state.current_stage = WorkflowStage.PAUSED.value
        state.warnings.append(f"Workflow paused for Human-In-The-Loop review. Reason: {reason.value}")
        self.saver.save_checkpoint(state)
        return state
