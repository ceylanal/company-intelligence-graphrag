"""Base tool contracts, error codes, and result containers for Agent Tools."""

import time
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from company_graphrag.agents.schema import EvidenceItem
from company_graphrag.safety.tool_policy import ToolExecutionContext, ToolPolicy, ToolPolicyError

T = TypeVar("T")


class ToolErrorCode(StrEnum):
    """Standardized error codes for Agent Tool executions."""

    INVALID_INPUT = "INVALID_INPUT"
    NOT_FOUND = "NOT_FOUND"
    READ_ONLY_VIOLATION = "READ_ONLY_VIOLATION"
    TIMEOUT = "TIMEOUT"
    BACKEND_ERROR = "BACKEND_ERROR"
    MAX_RESULTS_EXCEEDED = "MAX_RESULTS_EXCEEDED"
    POLICY_VIOLATION = "POLICY_VIOLATION"


class ToolResult[T](BaseModel):
    """Standardized output wrapper for all Agent Tool executions."""

    tool_name: str = Field(description="Name of the executed tool")
    success: bool = Field(default=True, description="True if tool executed successfully")
    data: T | None = Field(default=None, description="Typed output payload if success is True")
    error_code: ToolErrorCode | None = Field(default=None, description="Error code if success is False")
    error_message: str | None = Field(default=None, description="Human-readable error description")
    execution_time_ms: float = Field(default=0.0, ge=0.0, description="Execution duration in milliseconds")
    record_count: int = Field(default=0, ge=0, description="Number of items returned")


def sort_evidence_deterministically(evidence_list: list[EvidenceItem]) -> list[EvidenceItem]:
    """Sort evidence records deterministically by relevance_score desc, chunk_id asc, evidence_id asc."""

    def sort_key(item: EvidenceItem):
        score = item.relevance_score if item.relevance_score is not None else 0.0
        chunk_id = item.chunk_id if item.chunk_id else ""
        evidence_id = item.evidence_id if item.evidence_id else ""
        return (-score, chunk_id, evidence_id)

    return sorted(evidence_list, key=sort_key)


class BaseTool[T](ABC):
    """Abstract base class for all typed Agent Tools."""

    name: str
    description: str
    timeout_seconds: float = 5.0
    max_retries: int = 2
    input_model: type[BaseModel] | None = None

    @abstractmethod
    def _run(self, input_payload: Any) -> T:
        """Internal execution logic to be implemented by specific tools."""
        pass

    def run(self, input_payload: Any, *, policy_context: ToolExecutionContext | None = None) -> ToolResult[T]:
        """Safely execute tool with timing, error handling, and deterministic output formatting."""
        start_time = time.perf_counter()
        retries = 0

        try:
            validated_payload = ToolPolicy().validate_call(self.name, input_payload, context=policy_context)
        except ToolPolicyError as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return ToolResult(
                tool_name=self.name,
                success=False,
                error_code=(
                    ToolErrorCode.READ_ONLY_VIOLATION
                    if "READ_ONLY_VIOLATION" in str(exc)
                    else ToolErrorCode.POLICY_VIOLATION
                ),
                error_message=(
                    "READ_ONLY_VIOLATION: Tool call violates the read-only policy."
                    if "READ_ONLY_VIOLATION" in str(exc)
                    else "Tool call denied by safety policy."
                ),
                execution_time_ms=round(elapsed_ms, 2),
            )

        while True:
            try:
                result_data = self._run(validated_payload)
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                record_count = 0
                if hasattr(result_data, "hits") and isinstance(result_data.hits, list):
                    record_count = len(result_data.hits)
                elif hasattr(result_data, "records") and isinstance(result_data.records, list):
                    record_count = len(result_data.records)
                elif isinstance(result_data, list):
                    record_count = len(result_data)

                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    data=result_data,
                    execution_time_ms=round(elapsed_ms, 2),
                    record_count=record_count,
                )

            except TimeoutError as te:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error_code=ToolErrorCode.TIMEOUT,
                    error_message=f"Tool execution timed out: {te}",
                    execution_time_ms=round(elapsed_ms, 2),
                )
            except ValueError as ve:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                err_code = ToolErrorCode.INVALID_INPUT
                if "READ_ONLY_VIOLATION" in str(ve) or "read-only" in str(ve).lower():
                    err_code = ToolErrorCode.READ_ONLY_VIOLATION
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error_code=err_code,
                    error_message=str(ve),
                    execution_time_ms=round(elapsed_ms, 2),
                )
            except Exception as e:
                if retries < self.max_retries:
                    retries += 1
                    time.sleep(0.05 * retries)
                    continue
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error_code=ToolErrorCode.BACKEND_ERROR,
                    error_message=f"Backend execution error: {e}",
                    execution_time_ms=round(elapsed_ms, 2),
                )
