"""Shared data contracts for deterministic safety guardrails."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class GuardrailAction(StrEnum):
    """Possible outcomes ordered from least to most restrictive."""

    ALLOW = "allow"
    WARN = "warn"
    REDACT = "redact"
    BLOCK = "block"


_ACTION_PRIORITY = {
    GuardrailAction.ALLOW: 0,
    GuardrailAction.WARN: 1,
    GuardrailAction.REDACT: 2,
    GuardrailAction.BLOCK: 3,
}


class GuardrailDecision(BaseModel):
    """One auditable decision emitted by a guardrail rule."""

    code: str
    action: GuardrailAction
    message: str
    field: str | None = None


class ConversationTurn(BaseModel):
    """A bounded user/assistant message supplied as conversation history."""

    role: str
    content: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        """Only accept roles that cannot impersonate the system or tools."""
        normalized = value.strip().lower()
        if normalized not in {"user", "assistant"}:
            raise ValueError("history role must be 'user' or 'assistant'")
        return normalized


class QueryFilters(BaseModel):
    """Validated retrieval filters accepted by the safety boundary."""

    company: str | None = Field(default=None, min_length=1, max_length=120)
    ticker: str | list[str] | None = None
    year: int | list[int] | None = None
    report_type: str | None = None


class InputGuardrailResult(BaseModel):
    """Sanitized input plus its aggregate safety decision."""

    action: GuardrailAction
    question: str
    history: list[ConversationTurn] = Field(default_factory=list)
    filters: QueryFilters | None = None
    decisions: list[GuardrailDecision] = Field(default_factory=list)

    @property
    def blocked(self) -> bool:
        """Return whether downstream execution must stop."""
        return self.action == GuardrailAction.BLOCK


class OutputGuardrailResult(BaseModel):
    """Sanitized model output plus its aggregate safety decision."""

    action: GuardrailAction
    text: str
    citations: list[int] = Field(default_factory=list)
    decisions: list[GuardrailDecision] = Field(default_factory=list)

    @property
    def blocked(self) -> bool:
        """Return whether the original model response was rejected."""
        return self.action == GuardrailAction.BLOCK


def aggregate_action(decisions: list[GuardrailDecision]) -> GuardrailAction:
    """Return the most restrictive action, defaulting to allow."""
    if not decisions:
        return GuardrailAction.ALLOW
    return max((decision.action for decision in decisions), key=_ACTION_PRIORITY.__getitem__)


def safe_error_payload(error_id: str | None = None) -> dict[str, Any]:
    """Build a stable public error without exception, credential, or topology details."""
    payload: dict[str, Any] = {
        "detail": "İstek güvenli biçimde tamamlanamadı. Lütfen girdiyi kontrol edip yeniden deneyin."
    }
    if error_id:
        payload["error_id"] = error_id
    return payload
