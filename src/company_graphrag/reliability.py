"""Retry classification and per-run budget enforcement."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx


class BudgetExceededError(RuntimeError):
    """A configured research budget has been exhausted."""


class PermanentProviderError(RuntimeError):
    """A non-retryable provider response."""


def is_transient(exc: BaseException) -> bool:
    """Classify only connection, timeout, rate-limit, and 5xx failures as transient."""
    if isinstance(exc, (TimeoutError, ConnectionError, httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


def retry_call[T](
    operation: Callable[[], T],
    *,
    max_retries: int,
    base_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
) -> T:
    """Retry transient failures with bounded exponential backoff and jitter."""
    attempt = 0
    while True:
        try:
            return operation()
        except Exception as exc:
            if not is_transient(exc) or attempt >= max_retries:
                raise
            sleep(base_seconds * (2**attempt) * (0.5 + random_value()))
            attempt += 1


@dataclass
class ResearchBudget:
    """Mutable request budget with explicit accounting points."""

    max_duration_seconds: float
    max_model_calls: int
    max_input_tokens: int
    max_output_tokens: int
    max_total_tokens: int
    max_cost_usd: float | None = None
    started_at: float = 0.0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = time.monotonic()

    def consume_model_call(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        self.model_calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.estimated_cost_usd += estimated_cost_usd
        self.check()

    def check(self) -> None:
        limits = {
            "duration": time.monotonic() - self.started_at > self.max_duration_seconds,
            "model_calls": self.model_calls > self.max_model_calls,
            "input_tokens": self.input_tokens > self.max_input_tokens,
            "output_tokens": self.output_tokens > self.max_output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens > self.max_total_tokens,
            "cost": self.max_cost_usd is not None and self.estimated_cost_usd > self.max_cost_usd,
        }
        exceeded = [name for name, hit in limits.items() if hit]
        if exceeded:
            raise BudgetExceededError(f"Research budget exceeded: {', '.join(exceeded)}")
