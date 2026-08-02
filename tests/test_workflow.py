"""Comprehensive unit, integration, recovery, and persistence tests for ResearchWorkflow."""

from unittest.mock import MagicMock

import pytest

from company_graphrag.agents.schema import AgentWorkflowStatus, EvidenceItem
from company_graphrag.agents.workflow import (
    CheckpointCorruptError,
    CheckpointNotFoundError,
    JSONCheckpointSaver,
    ResearchWorkflow,
    WorkflowInterruptReason,
    WorkflowStage,
)


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    return tmp_path / "checkpoints"


@pytest.fixture
def sample_evidence():
    return EvidenceItem(
        company="Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
        ticker="ASELS",
        year=2024,
        report="annual_report",
        chunk_id="chk_asels_001",
        page_number=19,
        source_file="ASELS__2024__annual_report__tr.pdf",
        retrieval_method="vector_search",
        content="ASELSAN'ın 2024 yılı cirosu 120 Milyar TL olarak gerçekleşmiştir.",
        relevance_score=0.95,
    )


def test_end_to_end_normal_workflow(temp_checkpoint_dir):
    """Test 1: End-to-end normal workflow execution from query to completion."""
    saver = JSONCheckpointSaver(temp_checkpoint_dir)
    workflow = ResearchWorkflow(checkpoint_saver=saver)

    state = workflow.run("ASELSAN 2024 cirosu ne kadar?")

    assert state.status == AgentWorkflowStatus.COMPLETED
    assert state.current_stage == WorkflowStage.COMPLETED.value
    assert state.final_answer is not None
    assert state.structured_report is not None
    assert len(state.completed_tasks) >= 1

    # Verify checkpoint exists on disk
    loaded = saver.load_checkpoint(state.run_id)
    assert loaded.status == AgentWorkflowStatus.COMPLETED


def test_planning_interruption_and_resume(temp_checkpoint_dir):
    """Test 2: Interrupting workflow after planning stage and resuming with run_id."""
    saver = JSONCheckpointSaver(temp_checkpoint_dir)
    workflow = ResearchWorkflow(checkpoint_saver=saver)

    # Initialize and manually stop after PLANNING
    state = ResearchWorkflow(checkpoint_saver=saver).run("ASELSAN ve THY 2024 cirosunu karşılaştır")
    run_id = state.run_id

    # Simulate resume
    resumed_state = workflow.resume(run_id)
    assert resumed_state.status == AgentWorkflowStatus.COMPLETED
    assert resumed_state.structured_report is not None


def test_completed_tasks_not_reexecuted(temp_checkpoint_dir):
    """Test 3: Resume ensuring completed tasks are NOT re-executed."""
    saver = JSONCheckpointSaver(temp_checkpoint_dir)
    workflow = ResearchWorkflow(checkpoint_saver=saver)

    state = workflow.run("ASELSAN 2024 cirosu")
    run_id = state.run_id

    initial_completed_count = len(state.completed_tasks)
    initial_evidence_count = len(state.evidence)

    # Resume completed workflow
    resumed = workflow.resume(run_id)

    assert len(resumed.completed_tasks) == initial_completed_count
    assert len(resumed.evidence) == initial_evidence_count, "Evidence count must NOT double!"


def test_duplicate_evidence_prevention_on_resume(temp_checkpoint_dir, sample_evidence):
    """Test 4: Resuming/retrying workflow prevents duplicate evidence items."""
    saver = JSONCheckpointSaver(temp_checkpoint_dir)
    workflow = ResearchWorkflow(checkpoint_saver=saver)

    state = workflow.run("ASELSAN ciro testi")
    state.add_evidence(sample_evidence)
    state.add_evidence(sample_evidence)  # Intentionally add duplicate item

    saver.save_checkpoint(state)

    resumed = workflow.resume(state.run_id)
    assert len(resumed.evidence) == len({e.chunk_id for e in resumed.evidence})


def test_corrupt_checkpoint_error_handling(temp_checkpoint_dir):
    """Test 5: Loading corrupted JSON raises CheckpointCorruptError."""
    saver = JSONCheckpointSaver(temp_checkpoint_dir)
    corrupt_file = temp_checkpoint_dir / "run_corrupt_123.json"
    corrupt_file.write_text("{ invalid json payload ...", encoding="utf-8")

    with pytest.raises(CheckpointCorruptError):
        saver.load_checkpoint("run_corrupt_123")


def test_missing_checkpoint_error_handling(temp_checkpoint_dir):
    """Test 6: Loading non-existent run_id raises CheckpointNotFoundError."""
    saver = JSONCheckpointSaver(temp_checkpoint_dir)

    with pytest.raises(CheckpointNotFoundError):
        saver.load_checkpoint("non_existent_run_999")


def test_workflow_cancellation(temp_checkpoint_dir):
    """Test 7: Cancelling workflow sets status to CANCELLED."""
    saver = JSONCheckpointSaver(temp_checkpoint_dir)
    workflow = ResearchWorkflow(checkpoint_saver=saver)

    state = workflow.run("ASELSAN iptal testi")
    run_id = state.run_id

    cancelled_state = workflow.cancel(run_id)

    assert cancelled_state.status == AgentWorkflowStatus.CANCELLED
    assert cancelled_state.current_stage == WorkflowStage.CANCELLED.value

    # Resuming cancelled workflow should remain cancelled
    resumed = workflow.resume(run_id)
    assert resumed.status == AgentWorkflowStatus.CANCELLED


def test_streaming_workflow_events_cancel_between_real_stages(temp_checkpoint_dir):
    """A disconnected stream stops before the next bounded workflow stage."""
    events: list[tuple[str, str]] = []
    cancel_requested = False

    def on_event(event_type, state, _payload):
        nonlocal cancel_requested
        events.append((event_type, state.current_stage))
        if event_type == "plan":
            cancel_requested = True

    workflow = ResearchWorkflow(
        checkpoint_saver=JSONCheckpointSaver(temp_checkpoint_dir),
        event_handler=on_event,
        cancellation_requested=lambda: cancel_requested,
    )

    state = workflow.run("ASELSAN 2024 cirosu ne kadar?")

    assert state.status == AgentWorkflowStatus.CANCELLED
    assert ("plan", WorkflowStage.PLANNING.value) in events
    assert ("stage", WorkflowStage.CANCELLED.value) in events
    assert state.current_stage == WorkflowStage.CANCELLED.value


def test_hitl_interrupt_and_resume(temp_checkpoint_dir):
    """Test 8: auto_approve_interrupts=False triggering status=PAUSED on interrupt condition and resuming."""
    saver = JSONCheckpointSaver(temp_checkpoint_dir)

    # Mock Planner to produce > 5 steps (overly broad plan)
    mock_planner = MagicMock()
    mock_plan = MagicMock()
    mock_plan.is_out_of_domain = False
    mock_plan.steps = [MagicMock() for _ in range(6)]  # 6 steps > 5
    mock_plan.normalized_query = "broad query"
    mock_planner.plan.return_value = mock_plan

    workflow_hitl = ResearchWorkflow(
        checkpoint_saver=saver,
        auto_approve_interrupts=False,
        planner=mock_planner,
    )

    state = workflow_hitl.run("Aşırı geniş araştırma sorgusu")

    assert state.status == AgentWorkflowStatus.PAUSED
    assert state.interrupt_reason == WorkflowInterruptReason.OVERLY_BROAD_PLAN.value

    # Resume HITL workflow
    resumed = workflow_hitl.resume(state.run_id)
    assert resumed.status != AgentWorkflowStatus.PAUSED
