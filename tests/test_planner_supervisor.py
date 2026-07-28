"""Comprehensive unit tests for PlannerAgent, SupervisorAgent, ResearchPlan, and Task Dependencies."""

from company_graphrag.agents.contracts import AgentRole
from company_graphrag.agents.planner import PlannerAgent
from company_graphrag.agents.schema import AgentWorkflowStatus, EvidenceItem, ExecutionBudget, ResearchState
from company_graphrag.agents.supervisor import SupervisorAgent


def test_single_company_single_metric_plan():
    """Test 1: Single company single metric question planning."""
    planner = PlannerAgent()
    plan = planner.plan("ASELSAN 2024 cirosu ne kadar?")

    assert plan.user_query == "ASELSAN 2024 cirosu ne kadar?"
    assert plan.detected_tickers == ["ASELS"]
    assert plan.detected_years == [2024]
    assert "ciro" in plan.detected_metrics
    assert plan.is_out_of_domain is False
    assert plan.is_comparison is False
    assert len(plan.steps) == 1
    assert plan.steps[0].task_id == "task_1"
    assert plan.steps[0].retrieval_strategy == "vector_search"
    assert plan.steps[0].max_tool_calls == 2


def test_two_company_comparison_plan():
    """Test 2: Two-company comparison question plan decomposition."""
    planner = PlannerAgent()
    plan = planner.plan("ASELSAN ve THY 2024 cirosunu karşılaştır")

    assert plan.is_comparison is True
    assert set(plan.detected_tickers) == {"ASELS", "THYAO"}
    assert len(plan.steps) == 3

    # Parallel tasks for ASELS and THYAO
    assert plan.steps[0].task_id == "task_1"
    assert plan.steps[0].depends_on == []
    assert plan.steps[1].task_id == "task_2"
    assert plan.steps[1].depends_on == []

    # Comparison synthesis task dependent on task_1 and task_2
    assert plan.steps[2].task_id == "task_3"
    assert plan.steps[2].depends_on == ["task_1", "task_2"]
    assert plan.steps[2].priority == 2


def test_multi_year_comparison_plan():
    """Test 3: Multi-year comparison question plan steps."""
    planner = PlannerAgent()
    plan = planner.plan("ASELSAN 2023 ve 2024 Ar-Ge harcamalarını karşılaştır")

    assert plan.detected_tickers == ["ASELS"]
    assert plan.detected_years == [2023, 2024]
    assert len(plan.steps) == 3
    assert plan.steps[0].depends_on == []
    assert plan.steps[1].depends_on == []
    assert plan.steps[2].depends_on == ["task_1", "task_2"]


def test_multi_hop_relationship_plan():
    """Test 4: Multi-hop relationship question assigning graph search strategy."""
    planner = PlannerAgent()
    plan = planner.plan("ASELSAN hangi sektörlerde faaliyet göstermekte ve ilişkili ürünleri nelerdir?")

    assert plan.is_multi_hop is True
    assert plan.detected_tickers == ["ASELS"]
    assert len(plan.steps) >= 2
    assert plan.steps[0].retrieval_strategy == "graph_search"
    assert "graph_search" in plan.steps[0].required_tools


test_ambiguous_company_name_cases = [
    ("Aselsan ne iş yapar?", "ASELS"),
    ("Türk Hava Yolları 2024 filosu", "THYAO"),
    ("Akbank 2024 kar marjı", "AKBNK"),
]


def test_ambiguous_company_name_resolution():
    """Test 5: Ambiguous company names mapping to canonical BIST tickers."""
    planner = PlannerAgent()
    for q, expected_ticker in test_ambiguous_company_name_cases:
        plan = planner.plan(q)
        assert expected_ticker in plan.detected_tickers, f"Failed for query '{q}'"


def test_out_of_domain_query_handling():
    """Test 6: Out-of-domain query handled without database tool execution."""
    planner = PlannerAgent()
    plan = planner.plan("Yarın İstanbul'da hava durumu ve maç skoru nasıl?")

    assert plan.is_out_of_domain is True
    assert len(plan.steps) == 1
    assert plan.steps[0].retrieval_strategy == "none"
    assert plan.total_estimated_tool_calls == 0

    # Test Supervisor handling out-of-domain
    supervisor = SupervisorAgent()
    state = ResearchState(
        user_query="Yarın İstanbul'da hava durumu nasıl?",
        status=AgentWorkflowStatus.PLANNING,
        structured_plan=plan,
    )
    out = supervisor.dispatch_next_agent(state)

    assert out.is_complete is True
    assert state.status == AgentWorkflowStatus.COMPLETED
    assert "kapsamı dışındadır" in state.final_answer


def test_task_dependency_resolution_and_duplicate_prevention():
    """Test 7: Dependency resolution filtering ready tasks and preventing duplicates."""
    planner = PlannerAgent()
    plan = planner.plan("ASELSAN ve THY 2024 cirosunu karşılaştır")

    supervisor = SupervisorAgent()
    state = ResearchState(user_query="ASELSAN ve THY 2024 cirosunu karşılaştır", structured_plan=plan)
    supervisor.validate_plan(state)

    # Initially task_1 and task_2 are ready (depends_on == [])
    ready = supervisor.select_next_tasks(state)
    ready_ids = [t.task_id for t in ready]
    assert "task_1" in ready_ids
    assert "task_2" in ready_ids
    assert "task_3" not in ready_ids

    # Complete task_1
    supervisor.record_task_completion(state, "task_1")
    ready_after_t1 = supervisor.select_next_tasks(state)
    ready_ids_after_t1 = [t.task_id for t in ready_after_t1]

    assert "task_1" not in ready_ids_after_t1  # Completed task not re-scheduled!
    assert "task_2" in ready_ids_after_t1
    assert "task_3" not in ready_ids_after_t1  # Still waiting for task_2

    # Complete task_2
    supervisor.record_task_completion(state, "task_2")
    ready_after_t2 = supervisor.select_next_tasks(state)
    ready_ids_after_t2 = [t.task_id for t in ready_after_t2]

    assert ready_ids_after_t2 == ["task_3"]  # task_3 now unlocked!


def test_execution_budget_exhaustion_halting():
    """Test 8: Supervisor stopping execution when execution budget is exhausted."""
    supervisor = SupervisorAgent()

    state = ResearchState(
        user_query="ASELSAN ciro",
        execution_budget=ExecutionBudget(max_steps=2, max_search_calls=1),
    )

    # Exhaust search calls limit
    state.execution_budget.record_search_call()
    state.execution_budget.record_search_call()

    # Add 1 evidence item so status goes to WRITING instead of FAILED
    state.evidence.append(
        EvidenceItem(
            company="Aselsan",
            ticker="ASELS",
            year=2024,
            chunk_id="c1",
            page_number=1,
            source_file="f.pdf",
            retrieval_method="vector_search",
            content="text",
        )
    )

    stopped = supervisor.check_budget_and_limits(state)
    assert stopped is True
    assert state.status == AgentWorkflowStatus.WRITING
    assert any("limit reached" in w for w in state.warnings)


def test_supervisor_orchestration_workflow():
    """Test 9: End-to-end orchestration flow across Supervisor states."""
    planner = PlannerAgent()
    plan = planner.plan("ASELSAN 2024 cirosu ne kadar?")

    supervisor = SupervisorAgent()
    state = ResearchState(user_query="ASELSAN 2024 cirosu ne kadar?")

    # Step 1: PENDING -> PLANNER
    out1 = supervisor.dispatch_next_agent(state)
    assert out1.next_agent == AgentRole.PLANNER
    assert state.status == AgentWorkflowStatus.PLANNING

    # Attach generated plan
    state.structured_plan = plan

    # Step 2: PLANNING -> RESEARCHING
    out2 = supervisor.dispatch_next_agent(state)
    assert state.status == AgentWorkflowStatus.RESEARCHING
    assert out2.next_agent == AgentRole.VECTOR_RESEARCHER

    # Record research completion
    supervisor.record_task_completion(state, "task_1")

    # Step 3: RESEARCHING -> VERIFYING
    out3 = supervisor.dispatch_next_agent(state)
    assert state.status == AgentWorkflowStatus.VERIFYING
    assert out3.next_agent == AgentRole.EVIDENCE_VERIFIER

    # Step 4: VERIFYING -> WRITING
    out4 = supervisor.dispatch_next_agent(state)
    assert state.status == AgentWorkflowStatus.WRITING
    assert out4.next_agent == AgentRole.REPORT_WRITER

    # Step 5: WRITING -> COMPLETED
    out5 = supervisor.dispatch_next_agent(state)
    assert state.status == AgentWorkflowStatus.COMPLETED
    assert out5.is_complete is True
