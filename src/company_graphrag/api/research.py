"""Guarded synchronous research endpoint with durable idempotency."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import defaultdict, deque
from typing import Any

import anyio
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from company_graphrag.agents.workflow.orchestrator import ResearchWorkflow
from company_graphrag.config import settings
from company_graphrag.observability.context import current_request_id
from company_graphrag.observability.metrics import ACTIVE_RESEARCH
from company_graphrag.observability.opik import record_opik_run
from company_graphrag.observability.tracing import flush_telemetry, span
from company_graphrag.safety.input_guardrails import InputGuardrails
from company_graphrag.safety.models import ConversationTurn
from company_graphrag.safety.output_guardrails import OutputGuardrails

router = APIRouter(prefix="/research", tags=["Research"])
_semaphore = asyncio.Semaphore(settings.max_concurrent_research_tasks)
_request_times: dict[str, deque[float]] = defaultdict(deque)
_input_guardrails = InputGuardrails()
_output_guardrails = OutputGuardrails()


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=32_000)
    history: list[ConversationTurn] = Field(default_factory=list)


class ResearchResponse(BaseModel):
    run_id: str
    request_id: str
    status: str
    answer: str | None
    metadata: dict[str, Any]


def _enforce_rate_limit(client_key: str) -> None:
    now = time.monotonic()
    cutoff = now - settings.rate_limit_window_seconds
    entries = _request_times[client_key]
    while entries and entries[0] < cutoff:
        entries.popleft()
    if len(entries) >= settings.rate_limit_requests:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
    entries.append(now)


@router.post("", response_model=ResearchResponse)
async def create_research(payload: ResearchRequest, request: Request) -> ResearchResponse:
    """Execute a bounded durable workflow and return reproducibility metadata."""
    client_key = request.client.host if request.client else "unknown"
    _enforce_rate_limit(client_key)
    request_id = current_request_id()
    input_result = _input_guardrails.evaluate(payload.query, history=payload.history)
    if input_result.blocked:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Request was rejected by input safety validation.",
        )

    idempotency_key = request.headers.get("idempotency-key")
    if idempotency_key:
        digest = hashlib.sha256(f"{idempotency_key}\0{input_result.question}".encode()).hexdigest()[:20]
        run_id = f"run_{digest}"
    else:
        run_id = None

    async with _semaphore:
        ACTIVE_RESEARCH.inc()
        try:
            with span("research_workflow", **{"request.id": request_id}) as research_span:
                otel_trace_id = format(research_span.get_span_context().trace_id, "032x")
                state = await anyio.to_thread.run_sync(ResearchWorkflow().run, input_result.question, run_id)
                retry_count = sum(state.retry_count.values())
                budget = state.execution_budget
                research_span.set_attributes(
                    {
                        "run.id": state.run_id,
                        "llm.input_tokens": budget.input_tokens_used,
                        "llm.output_tokens": budget.output_tokens_used,
                        "llm.total_tokens": budget.tokens_used,
                        "llm.estimated_cost_usd": budget.estimated_cost_usd,
                        "llm.retry_count": retry_count,
                        "llm.fallback_used": False,
                    }
                )
        except ValueError:
            raise HTTPException(status_code=409, detail="Request conflicts with an existing research run.") from None
        except Exception:
            raise HTTPException(status_code=503, detail="Research workflow is temporarily unavailable.") from None
        finally:
            ACTIVE_RESEARCH.dec()

    valid_citations = {
        citation.citation_index
        for citation in (state.structured_report.citations if state.structured_report is not None else [])
    }
    retrieved_context = [item.content or item.text for item in state.evidence]
    output_result = _output_guardrails.evaluate(
        state.final_answer or "",
        valid_citations=valid_citations,
        retrieved_context=retrieved_context,
    )

    record_opik_run(
        run_id=state.run_id,
        status=state.status.value,
        workflow_version=state.workflow_version,
        prompt_bundle_version=state.prompt_bundle_version,
        config_hash=state.config_hash,
    )
    flush_telemetry()
    return ResearchResponse(
        run_id=state.run_id,
        request_id=request_id,
        status=state.status.value,
        answer=output_result.text,
        metadata={
            "application_version": state.application_version,
            "workflow_version": state.workflow_version,
            "prompt_bundle_version": state.prompt_bundle_version,
            "config_hash": state.config_hash,
            "otel_trace_id": otel_trace_id,
            "input_safety_action": input_result.action.value,
            "output_safety_action": output_result.action.value,
            "safety_decision_codes": [
                decision.code for decision in [*input_result.decisions, *output_result.decisions]
            ],
        },
    )
