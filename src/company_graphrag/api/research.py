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
from company_graphrag.observability.tracing import span

router = APIRouter(prefix="/research", tags=["Research"])
_semaphore = asyncio.Semaphore(settings.max_concurrent_research_tasks)
_request_times: dict[str, deque[float]] = defaultdict(deque)


class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=4000)


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
    idempotency_key = request.headers.get("idempotency-key")
    if idempotency_key:
        digest = hashlib.sha256(f"{idempotency_key}\0{payload.query}".encode()).hexdigest()[:20]
        run_id = f"run_{digest}"
    else:
        run_id = None

    async with _semaphore:
        ACTIVE_RESEARCH.inc()
        try:
            with span("research_workflow", **{"request.id": request_id}):
                state = await anyio.to_thread.run_sync(ResearchWorkflow().run, payload.query, run_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Research workflow failed: {type(exc).__name__}") from None
        finally:
            ACTIVE_RESEARCH.dec()

    record_opik_run(
        run_id=state.run_id,
        status=state.status.value,
        workflow_version=state.workflow_version,
        prompt_bundle_version=state.prompt_bundle_version,
        config_hash=state.config_hash,
    )
    return ResearchResponse(
        run_id=state.run_id,
        request_id=request_id,
        status=state.status.value,
        answer=state.final_answer,
        metadata={
            "application_version": state.application_version,
            "workflow_version": state.workflow_version,
            "prompt_bundle_version": state.prompt_bundle_version,
            "config_hash": state.config_hash,
        },
    )
