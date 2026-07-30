"""Tests for durable workflow step, loop, duration, and budget controls."""

import pytest

from company_graphrag.agents.schema import ExecutionBudget, ResearchState, ToolCallRecord
from company_graphrag.safety.agent_limits import AgentLimitError, AgentLimits


def _record() -> ToolCallRecord:
    return ToolCallRecord(agent_role="Vector Researcher", tool_name="vector_search", input_params={"query": "ASELS"})


def test_identical_tool_loop_is_blocked() -> None:
    state = ResearchState(user_query="ASELS geliri")
    state.tool_calls.extend([_record(), _record(), _record()])

    with pytest.raises(AgentLimitError, match="Repeated identical"):
        AgentLimits(max_repeated_operation=2).check(state)


def test_tool_chain_and_token_budget_are_blocked() -> None:
    state = ResearchState(user_query="ASELS geliri", execution_budget=ExecutionBudget(max_tokens=1000, tokens_used=1000))
    state.tool_calls.extend([_record(), _record(), _record()])

    with pytest.raises(AgentLimitError):
        AgentLimits(max_tool_calls=2).check(state)


def test_duration_and_agent_step_limits_are_enforced() -> None:
    now = [0.0]
    limits = AgentLimits(max_duration_seconds=5.0, max_agent_steps=1, clock=lambda: now[0])
    state = ResearchState(user_query="ASELS")

    limits.record_agent_step(state)
    with pytest.raises(AgentLimitError, match="step"):
        limits.record_agent_step(state)

    now[0] = 6.0
    with pytest.raises(AgentLimitError, match="duration"):
        limits.check(state)


def test_normal_bounded_workflow_state_passes() -> None:
    state = ResearchState(user_query="ASELS", execution_budget=ExecutionBudget(max_steps=5, max_search_calls=5))
    state.tool_calls.append(_record())
    limits = AgentLimits(max_tool_calls=5, max_agent_steps=5, max_repeated_operation=2)

    limits.record_agent_step(state)
    limits.check(state)
