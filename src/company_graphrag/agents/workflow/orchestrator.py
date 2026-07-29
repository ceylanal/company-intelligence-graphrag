"""Durable Multi-Agent Research Workflow Orchestrator."""

from enum import StrEnum

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
    ):
        self.saver = checkpoint_saver or JSONCheckpointSaver(settings.checkpoint_dir)
        self.auto_approve_interrupts = auto_approve_interrupts

        self.planner = planner or PlannerAgent()
        self.supervisor = supervisor or SupervisorAgent()
        self.vector_researcher = vector_researcher or VectorResearcherAgent()
        self.graph_researcher = graph_researcher or GraphResearcherAgent()
        self.verifier = verifier or EvidenceVerifierAgent()
        self.writer = writer or ReportWriterAgent()

    def run(self, user_query: str, run_id: str | None = None) -> ResearchState:
        """Start a new durable research workflow execution for user_query."""
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

        return self._execute_from_current_stage(state)

    def resume(self, run_id: str) -> ResearchState:
        """Resume an interrupted or paused workflow execution from last saved checkpoint."""
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
            state.current_stage = st.value

            if st == WorkflowStage.QUERY_INTAKE:
                state.status = AgentWorkflowStatus.PENDING

            elif st == WorkflowStage.PLANNING:
                state.status = AgentWorkflowStatus.PLANNING
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

                # Check HITL interrupt for ambiguous or out-of-domain query
                if plan.is_out_of_domain:
                    state.status = AgentWorkflowStatus.FAILED
                    state.error = "Kapsam dışı veya belirsiz kullanıcı sorgusu."
                    self.saver.save_checkpoint(state)
                    return state

                if len(plan.steps) > 5 and not self.auto_approve_interrupts:
                    from company_graphrag.agents.schema import ResearchPlan

                    if isinstance(plan, ResearchPlan):
                        state.structured_plan = plan
                    return self._pause_workflow(state, WorkflowInterruptReason.OVERLY_BROAD_PLAN)
                state.structured_plan = plan

            elif st == WorkflowStage.PLAN_VALIDATION:
                self.supervisor.validate_plan(state)

            elif st == WorkflowStage.RESEARCH_EXECUTION:
                state.status = AgentWorkflowStatus.RESEARCHING
                # Execute ready tasks iteratively
                while True:
                    if state.execution_budget.is_exhausted():
                        if not self.auto_approve_interrupts:
                            return self._pause_workflow(state, WorkflowInterruptReason.BUDGET_EXCEEDED)
                        break

                    ready_tasks = self.supervisor.select_next_tasks(state)
                    if not ready_tasks:
                        break

                    for task_step in ready_tasks:
                        # Skip if already completed (idempotency)
                        if task_step.task_id in state.completed_tasks:
                            continue

                        # Execute with appropriate researcher
                        if "graph_search" in task_step.required_tools:
                            with span("graph_retrieval", **{"run.id": state.run_id}):
                                self.graph_researcher.execute_task(task_step, state)
                        else:
                            with span("vector_retrieval", **{"run.id": state.run_id}):
                                self.vector_researcher.execute_task(task_step, state)

                        state.completed_tasks.append(task_step.task_id)

            elif st == WorkflowStage.EVIDENCE_MERGE:
                # Deduplicate evidence to prevent duplicate items upon resume/retry
                with span("hybrid_result_fusion", **{"run.id": state.run_id}):
                    state.evidence = EvidenceDeduplicator.deduplicate(state.evidence)

                if not state.evidence and not self.auto_approve_interrupts:
                    return self._pause_workflow(state, WorkflowInterruptReason.INSUFFICIENT_EVIDENCE)

            elif st == WorkflowStage.VERIFICATION:
                state.status = AgentWorkflowStatus.VERIFYING
                with span("citation_validation", **{"run.id": state.run_id}):
                    self.verifier.verify_research_state(state)

                if len(state.contradictions) >= 2 and not self.auto_approve_interrupts:
                    return self._pause_workflow(state, WorkflowInterruptReason.HIGH_CONTRADICTIONS)

            elif st == WorkflowStage.TARGETED_FOLLOWUP:
                # Check if follow up tasks were requested
                pass

            elif st == WorkflowStage.REPORT_GENERATION:
                state.status = AgentWorkflowStatus.WRITING
                with span("answer_synthesis", **{"run.id": state.run_id}):
                    self.writer.generate_report(state)

            elif st == WorkflowStage.FINAL_QUALITY_GATE:
                # Final audit
                pass

            elif st == WorkflowStage.COMPLETED:
                state.status = AgentWorkflowStatus.COMPLETED

            # Save checkpoint after completing each stage
            self.saver.save_checkpoint(state)

        return state

    def _pause_workflow(self, state: ResearchState, reason: WorkflowInterruptReason) -> ResearchState:
        """Pause workflow execution for Human-In-The-Loop input."""
        state.status = AgentWorkflowStatus.PAUSED
        state.interrupt_reason = reason.value
        state.current_stage = WorkflowStage.PAUSED.value
        state.warnings.append(f"Workflow paused for Human-In-The-Loop review. Reason: {reason.value}")
        self.saver.save_checkpoint(state)
        return state
