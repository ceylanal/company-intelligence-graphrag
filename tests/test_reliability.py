"""Reliability policy and budget tests."""

import httpx
import pytest

from company_graphrag.reliability import BudgetExceededError, ResearchBudget, retry_call


def test_transient_timeout_retries_with_backoff() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ReadTimeout("temporary")
        return "ok"

    assert retry_call(
        operation,
        max_retries=2,
        base_seconds=0.1,
        sleep=sleeps.append,
        random_value=lambda: 0.5,
    ) == "ok"
    assert attempts == 3
    assert sleeps == pytest.approx([0.1, 0.2])


def test_permanent_failure_is_not_retried() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid request")

    with pytest.raises(ValueError):
        retry_call(operation, max_retries=3, base_seconds=0.01, sleep=lambda _: None)
    assert attempts == 1


def test_budget_exhaustion_stops_controlled() -> None:
    budget = ResearchBudget(
        max_duration_seconds=60,
        max_model_calls=1,
        max_input_tokens=10,
        max_output_tokens=10,
        max_total_tokens=20,
    )
    budget.consume_model_call(input_tokens=5, output_tokens=5)
    with pytest.raises(BudgetExceededError, match="model_calls"):
        budget.consume_model_call(input_tokens=1, output_tokens=1)
