"""Supervisor / Orchestrator Agent for Company Intelligence Multi-Agent System."""


from company_graphrag.agents.contracts import AgentRole, SupervisorOutput
from company_graphrag.agents.schema import AgentWorkflowStatus, ResearchState, ResearchTaskStep


class SupervisorAgent:
    """Supervisor Agent coordinating workflow execution, task selection, and budget control."""

    def __init__(self, max_steps: int = 15):
        self.max_steps = max_steps

    def validate_plan(self, state: ResearchState) -> bool:
        """Validate the structured plan produced by Planner Agent."""
        if not state.structured_plan:
            state.warnings.append("Supervisor: No structured_plan present in ResearchState.")
            return False

        plan = state.structured_plan
        if not plan.validate_dependencies():
            state.status = AgentWorkflowStatus.FAILED
            state.error = "Supervisor: Invalid task dependencies in ResearchPlan."
            return False

        if plan.is_out_of_domain:
            state.status = AgentWorkflowStatus.COMPLETED
            state.final_answer = (
                f"Sorgunuz şirket finansal araştırma kapsamı dışındadır: '{state.user_query}'. "
                "Lütfen BIST şirketleri (örn. ASELS, THYAO, AKBNK) veya finansal rapor göstergeleri hakkında soru sorunuz."
            )
            return True

        state.pending_tasks = [s.task_id for s in plan.steps if s.status == "PENDING"]
        state.status = AgentWorkflowStatus.RESEARCHING
        return True

    def select_next_tasks(self, state: ResearchState) -> list[ResearchTaskStep]:
        """Select PENDING tasks whose dependencies are fully completed."""
        if not state.structured_plan:
            return []

        # Filter tasks
        ready_tasks = state.structured_plan.get_ready_tasks(state.completed_tasks)
        return ready_tasks

    def record_task_completion(self, state: ResearchState, task_id: str, summary: str | None = None) -> None:
        """Record completed task status in plan and state."""
        if not state.structured_plan:
            return

        for step in state.structured_plan.steps:
            if step.task_id == task_id:
                step.status = "COMPLETED"
                step.result_summary = summary or "Task completed successfully."
                break

        if task_id not in state.completed_tasks:
            state.completed_tasks.append(task_id)

        state.pending_tasks = [
            s.task_id for s in state.structured_plan.steps if s.status == "PENDING"
        ]

    def record_task_failure(self, state: ResearchState, task_id: str, error: str) -> None:
        """Apply controlled retry or mark task FAILED if max retries exceeded."""
        if not state.structured_plan:
            return

        for step in state.structured_plan.steps:
            if step.task_id == task_id:
                step.retry_count += 1
                if step.retry_count <= state.execution_budget.max_retries_per_agent:
                    state.warnings.append(
                        f"Supervisor: Retry {step.retry_count} for task {task_id} due to: {error}"
                    )
                    step.status = "PENDING"
                else:
                    step.status = "FAILED"
                    state.warnings.append(
                        f"Supervisor: Task {task_id} failed after {step.retry_count} retries: {error}"
                    )
                break

    def create_followup_task(self, state: ResearchState, missing_topic: str) -> bool:
        """Create targeted follow-up task if evidence is insufficient and budget permits."""
        if state.execution_budget.is_exhausted():
            state.warnings.append("Supervisor: Cannot add follow-up task, budget is exhausted.")
            return False

        if not state.structured_plan:
            return False

        followup_id = f"task_followup_{len(state.structured_plan.steps) + 1}"
        followup_step = ResearchTaskStep(
            task_id=followup_id,
            question=f"Targeted search for missing evidence: {missing_topic}",
            objective=f"Retrieve missing information regarding {missing_topic}",
            retrieval_strategy="vector_search",
            required_tools=["vector_search"],
            depends_on=[],
            priority=1,
            max_tool_calls=2,
            expected_evidence=f"Targeted evidence for {missing_topic}",
            status="PENDING",
        )

        state.structured_plan.steps.append(followup_step)
        state.pending_tasks.append(followup_id)
        state.warnings.append(f"Supervisor: Added targeted follow-up task {followup_id} for '{missing_topic}'.")
        state.status = AgentWorkflowStatus.RESEARCHING
        return True

    def check_budget_and_limits(self, state: ResearchState) -> bool:
        """Check if execution budget limits are breached."""
        state.execution_budget.increment_step()

        if state.execution_budget.is_exhausted():
            state.warnings.append(
                f"Supervisor: Execution budget limit reached (step={state.execution_budget.current_step}, "
                f"searches={state.execution_budget.search_calls_count}). Halting research phase."
            )
            if state.evidence:
                state.status = AgentWorkflowStatus.WRITING
            else:
                state.status = AgentWorkflowStatus.FAILED
                state.error = "Execution budget exhausted with 0 evidence gathered."
            return True
        return False

    def dispatch_next_agent(self, state: ResearchState) -> SupervisorOutput:
        """Determine next agent role and state transition."""
        if state.status == AgentWorkflowStatus.PENDING:
            state.status = AgentWorkflowStatus.PLANNING
            return SupervisorOutput(
                next_agent=AgentRole.PLANNER,
                is_complete=False,
                workflow_status=state.status.value,
                reasoning="Initial state is PENDING. Dispatching Planner Agent to create ResearchPlan.",
            )

        if state.status == AgentWorkflowStatus.PLANNING:
            if not self.validate_plan(state):
                return SupervisorOutput(
                    next_agent=None,
                    is_complete=True,
                    workflow_status=state.status.value,
                    reasoning="Planning failed or out-of-domain query handled directly.",
                )

        if state.status == AgentWorkflowStatus.RESEARCHING:
            if self.check_budget_and_limits(state):
                if state.status == AgentWorkflowStatus.WRITING:
                    return SupervisorOutput(
                        next_agent=AgentRole.REPORT_WRITER,
                        is_complete=False,
                        workflow_status=state.status.value,
                        reasoning="Budget reached. Proceeding to Report Writer with existing evidence.",
                    )
                return SupervisorOutput(
                    next_agent=None,
                    is_complete=True,
                    workflow_status=state.status.value,
                    reasoning="Budget exhausted without sufficient evidence.",
                )

            ready_tasks = self.select_next_tasks(state)
            if ready_tasks:
                current_task = ready_tasks[0]
                if current_task.retrieval_strategy == "graph_search":
                    return SupervisorOutput(
                        next_agent=AgentRole.GRAPH_RESEARCHER,
                        is_complete=False,
                        workflow_status=state.status.value,
                        reasoning=f"Dispatching Graph Researcher for task {current_task.task_id}.",
                    )
                return SupervisorOutput(
                    next_agent=AgentRole.VECTOR_RESEARCHER,
                    is_complete=False,
                    workflow_status=state.status.value,
                    reasoning=f"Dispatching Vector Researcher for task {current_task.task_id}.",
                )

            # All plan tasks completed or pending blocked
            state.status = AgentWorkflowStatus.VERIFYING
            return SupervisorOutput(
                next_agent=AgentRole.EVIDENCE_VERIFIER,
                is_complete=False,
                workflow_status=state.status.value,
                reasoning="All research plan tasks completed. Dispatching Evidence Verifier.",
            )

        if state.status == AgentWorkflowStatus.VERIFYING:
            state.status = AgentWorkflowStatus.WRITING
            return SupervisorOutput(
                next_agent=AgentRole.REPORT_WRITER,
                is_complete=False,
                workflow_status=state.status.value,
                reasoning="Evidence verification complete. Dispatching Report Writer.",
            )

        if state.status == AgentWorkflowStatus.WRITING or state.status == AgentWorkflowStatus.COMPLETED:
            state.status = AgentWorkflowStatus.COMPLETED
            return SupervisorOutput(
                next_agent=None,
                is_complete=True,
                workflow_status=state.status.value,
                reasoning="Workflow completed successfully.",
            )

        return SupervisorOutput(
            next_agent=None,
            is_complete=True,
            workflow_status=state.status.value,
            reasoning=f"Workflow halted in status {state.status.value}.",
        )
