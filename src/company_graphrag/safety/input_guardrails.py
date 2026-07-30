"""Fail-closed validation and sanitization for user-controlled inputs."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from company_graphrag.safety.models import (
    ConversationTurn,
    GuardrailAction,
    GuardrailDecision,
    InputGuardrailResult,
    QueryFilters,
    aggregate_action,
)
from company_graphrag.safety.prompt_injection import PromptInjectionDetector

_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\b(?:reveal|print|show|dump|repeat)\s+(?:the\s+)?system\s+prompt\b", re.IGNORECASE),
    re.compile(r"\b(?:developer|system)\s+message\s*:", re.IGNORECASE),
    re.compile(r"\b(?:disregard|forget)\s+(?:all\s+)?(?:rules|constraints|instructions)\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\s+(?:in\s+)?(?:developer|unfiltered|dan)\s+mode\b", re.IGNORECASE),
    re.compile(r"\bönceki\s+(?:tüm\s+)?talimatları\s+(?:yok\s+say|unut)\b", re.IGNORECASE),
    re.compile(r"\bsistem\s+promptunu\s+(?:göster|yazdır|açıkla)\b", re.IGNORECASE),
)
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,9}$")
_COMPANY_RE = re.compile(r"^[^\x00-\x1f\x7f-\x9f<>]{1,120}$")
_REPORT_TYPES = {"annual_report", "audit_report", "financial_statement", "investor_presentation", "sustainability_report"}
_SUPPORTED_CONTENT_TYPES = {
    "application/json",
    "application/pdf",
    "multipart/form-data",
    "text/csv",
    "text/markdown",
    "text/plain",
}
_SUPPORTED_EXTENSIONS = {".csv", ".json", ".md", ".pdf", ".txt"}
_WORD_RE = re.compile(r"\w+", re.UNICODE)


class InputGuardrails:
    """Apply request bounds, injection detection, and retrieval-filter validation."""

    def __init__(
        self,
        *,
        max_question_chars: int = 4_000,
        max_request_chars: int = 32_000,
        max_history_turns: int = 20,
        max_history_chars: int = 16_000,
        max_estimated_tokens: int = 8_000,
    ) -> None:
        self.max_question_chars = max_question_chars
        self.max_request_chars = max_request_chars
        self.max_history_turns = max_history_turns
        self.max_history_chars = max_history_chars
        self.max_estimated_tokens = max_estimated_tokens

    def evaluate(
        self,
        question: str,
        *,
        history: Sequence[ConversationTurn | dict[str, str]] | None = None,
        filters: QueryFilters | dict[str, Any] | None = None,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> InputGuardrailResult:
        """Evaluate input and return a fail-closed, sanitized result."""
        try:
            return self._evaluate(
                question,
                history=history,
                filters=filters,
                content_type=content_type,
                filename=filename,
            )
        except Exception:
            decision = GuardrailDecision(
                code="input_guardrail_failure",
                action=GuardrailAction.BLOCK,
                message="Input safety validation could not be completed.",
            )
            return InputGuardrailResult(
                action=GuardrailAction.BLOCK,
                question="",
                decisions=[decision],
            )

    def _evaluate(
        self,
        question: str,
        *,
        history: Sequence[ConversationTurn | dict[str, str]] | None,
        filters: QueryFilters | dict[str, Any] | None,
        content_type: str | None,
        filename: str | None,
    ) -> InputGuardrailResult:
        decisions: list[GuardrailDecision] = []
        if not isinstance(question, str):
            return self._blocked_result("invalid_question_type", "Question must be a string.")

        clean_question, question_changed = self._clean_text(question)
        if question_changed:
            decisions.append(
                GuardrailDecision(
                    code="control_characters_removed",
                    action=GuardrailAction.REDACT,
                    message="Null bytes or unsafe control characters were removed.",
                    field="question",
                )
            )

        if not clean_question.strip():
            decisions.append(
                GuardrailDecision(
                    code="empty_question",
                    action=GuardrailAction.BLOCK,
                    message="Question is empty after sanitization.",
                    field="question",
                )
            )
        if len(question) > self.max_question_chars:
            decisions.append(
                GuardrailDecision(
                    code="question_too_long",
                    action=GuardrailAction.BLOCK,
                    message=f"Question exceeds the {self.max_question_chars} character limit.",
                    field="question",
                )
            )

        clean_history: list[ConversationTurn] = []
        raw_history = history or []
        if len(raw_history) > self.max_history_turns:
            decisions.append(
                GuardrailDecision(
                    code="history_too_many_turns",
                    action=GuardrailAction.BLOCK,
                    message=f"Conversation history exceeds {self.max_history_turns} turns.",
                    field="history",
                )
            )
        try:
            for index, raw_turn in enumerate(raw_history):
                turn = raw_turn if isinstance(raw_turn, ConversationTurn) else ConversationTurn.model_validate(raw_turn)
                clean_content, changed = self._clean_text(turn.content)
                clean_history.append(ConversationTurn(role=turn.role, content=clean_content))
                if changed:
                    decisions.append(
                        GuardrailDecision(
                            code="control_characters_removed",
                            action=GuardrailAction.REDACT,
                            message="Unsafe control characters were removed from conversation history.",
                            field=f"history[{index}].content",
                        )
                    )
        except (ValidationError, TypeError):
            decisions.append(
                GuardrailDecision(
                    code="invalid_history_schema",
                    action=GuardrailAction.BLOCK,
                    message="Conversation history does not match the required schema.",
                    field="history",
                )
            )

        history_chars = sum(len(turn.content) for turn in clean_history)
        if history_chars > self.max_history_chars:
            decisions.append(
                GuardrailDecision(
                    code="history_too_long",
                    action=GuardrailAction.BLOCK,
                    message=f"Conversation history exceeds the {self.max_history_chars} character limit.",
                    field="history",
                )
            )
        total_chars = len(question) + history_chars
        if total_chars > self.max_request_chars:
            decisions.append(
                GuardrailDecision(
                    code="request_too_long",
                    action=GuardrailAction.BLOCK,
                    message=f"Request exceeds the {self.max_request_chars} character limit.",
                )
            )

        combined_text = "\n".join([clean_question, *(turn.content for turn in clean_history)])
        estimated_tokens = self._estimate_tokens(combined_text)
        if estimated_tokens > self.max_estimated_tokens:
            decisions.append(
                GuardrailDecision(
                    code="token_flooding",
                    action=GuardrailAction.BLOCK,
                    message=f"Estimated input tokens exceed the {self.max_estimated_tokens} token limit.",
                )
            )
        if self._has_excessive_repetition(combined_text):
            decisions.append(
                GuardrailDecision(
                    code="excessive_repetition",
                    action=GuardrailAction.BLOCK,
                    message="Input contains excessive repetition consistent with token flooding.",
                )
            )
        detector_result = PromptInjectionDetector().detect(combined_text, source="user")
        if detector_result.suspicious or any(pattern.search(combined_text) for pattern in _PROMPT_INJECTION_PATTERNS):
            decisions.append(
                GuardrailDecision(
                    code="prompt_injection",
                    action=GuardrailAction.BLOCK,
                    message="Explicit prompt-injection instructions were detected.",
                )
            )

        self._validate_content(content_type, filename, decisions)
        clean_filters = self._validate_filters(filters, decisions)
        return InputGuardrailResult(
            action=aggregate_action(decisions),
            question=clean_question.strip(),
            history=clean_history,
            filters=clean_filters,
            decisions=decisions,
        )

    @staticmethod
    def _clean_text(text: str) -> tuple[str, bool]:
        normalized = unicodedata.normalize("NFKC", text)
        clean = "".join(
            character
            for character in normalized
            if character in {"\n", "\t"} or not unicodedata.category(character).startswith("C")
        )
        return clean, clean != text

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        # Deliberately conservative and tokenizer-independent.
        return max(len(_WORD_RE.findall(text)), (len(text) + 3) // 4)

    @staticmethod
    def _has_excessive_repetition(text: str) -> bool:
        if re.search(r"(.)\1{63,}", text, flags=re.DOTALL):
            return True
        words = [word.casefold() for word in _WORD_RE.findall(text)]
        if len(words) < 100:
            return False
        counts = Counter(words)
        unique_ratio = len(counts) / len(words)
        most_common_ratio = counts.most_common(1)[0][1] / len(words)
        return unique_ratio < 0.08 or most_common_ratio > 0.35

    @staticmethod
    def _validate_content(
        content_type: str | None,
        filename: str | None,
        decisions: list[GuardrailDecision],
    ) -> None:
        if content_type:
            base_type = content_type.split(";", 1)[0].strip().lower()
            if base_type not in _SUPPORTED_CONTENT_TYPES:
                decisions.append(
                    GuardrailDecision(
                        code="unsupported_content_type",
                        action=GuardrailAction.BLOCK,
                        message="The supplied content type is not supported.",
                        field="content_type",
                    )
                )
        if filename:
            dot_index = filename.rfind(".")
            extension = filename[dot_index:].lower() if dot_index >= 0 else ""
            if extension not in _SUPPORTED_EXTENSIONS:
                decisions.append(
                    GuardrailDecision(
                        code="unsupported_file_type",
                        action=GuardrailAction.BLOCK,
                        message="The supplied file type is not supported.",
                        field="filename",
                    )
                )

    @staticmethod
    def _validate_filters(
        raw_filters: QueryFilters | dict[str, Any] | None,
        decisions: list[GuardrailDecision],
    ) -> QueryFilters | None:
        if raw_filters is None:
            return None
        try:
            validated = raw_filters if isinstance(raw_filters, QueryFilters) else QueryFilters.model_validate(raw_filters)
            if validated.company and not _COMPANY_RE.fullmatch(validated.company):
                raise ValueError("invalid company")
            tickers = [validated.ticker] if isinstance(validated.ticker, str) else (validated.ticker or [])
            if len(tickers) > 20 or any(not _TICKER_RE.fullmatch(ticker) for ticker in tickers):
                raise ValueError("invalid ticker")
            years = [validated.year] if isinstance(validated.year, int) else (validated.year or [])
            max_year = datetime.now(UTC).year + 1
            if len(years) > 20 or any(year < 1900 or year > max_year for year in years):
                raise ValueError("invalid year")
            if validated.report_type and validated.report_type not in _REPORT_TYPES:
                raise ValueError("invalid report type")
            return validated
        except (ValidationError, TypeError, ValueError):
            decisions.append(
                GuardrailDecision(
                    code="invalid_filter_schema",
                    action=GuardrailAction.BLOCK,
                    message="Company, ticker, year, or report type filter is invalid.",
                    field="filters",
                )
            )
            return None

    @staticmethod
    def _blocked_result(code: str, message: str) -> InputGuardrailResult:
        decision = GuardrailDecision(code=code, action=GuardrailAction.BLOCK, message=message, field="question")
        return InputGuardrailResult(
            action=GuardrailAction.BLOCK,
            question="",
            decisions=[decision],
        )
