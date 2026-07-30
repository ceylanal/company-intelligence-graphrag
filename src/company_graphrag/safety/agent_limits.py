"""Bounded execution controls for durable agent workflows."""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable
from typing import Any

from company_graphrag.agents.schema import ResearchState


class AgentLimitError(RuntimeError):
    """Raised when an agent workflow exceeds a mandatory safety budget."""


class AgentLimits:
    """Enforce tool, step, duration, token/cost, and repeated-operation limits."""

    def __init__(
        self,
        *,
        max_tool_calls: int = 10,
        max_agent_steps: int = 15,
        max_duration_seconds: float = 300.0,
        max_repeated_operation: int = 2,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_tool_calls = max_tool_calls
        self.max_agent_steps = max_agent_steps
        self.max_duration_seconds = max_duration_seconds
        self.max_repeated_operation = max_repeated_operation
        self._clock = clock
        self._started_at = clock()

    def restart_timer(self) -> None:
        """Start a fresh bounded window for a run or resume operation."""
        self._started_at = self._clock()

    def record_agent_step(self, state: ResearchState) -> None:
        """Increment the durable step counter before dispatching an agent."""
        if state.execution_budget.current_step >= self.max_agent_steps:
            raise AgentLimitError("Maximum agent step count exceeded.")
        state.execution_budget.increment_step()
        self.check(state)

    def check(self, state: ResearchState) -> None:
        """Reject exhausted budgets, tool floods, loops, or elapsed-time overruns."""
        if self._clock() - self._started_at > self.max_duration_seconds:
            raise AgentLimitError("Maximum workflow duration exceeded.")
        if len(state.tool_calls) > self.max_tool_calls:
            raise AgentLimitError("Maximum tool call count exceeded.")
        if state.execution_budget.is_exhausted():
            raise AgentLimitError("Workflow token, model, search, cost, or step budget is exhausted.")
        signatures = Counter(self._operation_signature(record) for record in state.tool_calls)
        if any(count > self.max_repeated_operation for count in signatures.values()):
            raise AgentLimitError("Repeated identical tool operation loop detected.")

    @staticmethod
    def _operation_signature(record: Any) -> str:
        params = getattr(record, "input_params", {})
        tool_name = getattr(record, "tool_name", "unknown")
        try:
            canonical = json.dumps(params, sort_keys=True, default=str, separators=(",", ":"))
        except (TypeError, ValueError):
            canonical = "unserializable"
        return f"{tool_name}:{canonical}"
