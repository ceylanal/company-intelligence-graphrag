"""Guarded synchronous research endpoint with durable idempotency."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import anyio
import yaml
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from starlette.responses import FileResponse, StreamingResponse

from company_graphrag.agents.schema import ResearchState
from company_graphrag.agents.workflow.checkpoint import CheckpointNotFoundError, JSONCheckpointSaver
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


class CompanyCatalogItem(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    official_domains: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)


class SourceDetail(BaseModel):
    citation_index: int
    chunk_id: str
    company: str
    ticker: str
    year: int
    source_file: str
    page_number: int
    retrieval_method: str
    snippet: str
    relevance_score: float | None = None
    citation_status: str | None = None
    report_type: str | None = None
    graph_path: dict[str, Any] | list[Any] | str | None = None
    document_available: bool = False
    document_url: str | None = None


def _enforce_rate_limit(client_key: str) -> None:
    now = time.monotonic()
    cutoff = now - settings.rate_limit_window_seconds
    entries = _request_times[client_key]
    while entries and entries[0] < cutoff:
        entries.popleft()
    if len(entries) >= settings.rate_limit_requests:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
    entries.append(now)


def _resolve_run_id(query: str, idempotency_key: str | None) -> str:
    if idempotency_key:
        digest = hashlib.sha256(f"{idempotency_key}\0{query}".encode()).hexdigest()[:20]
        return f"run_{digest}"
    return f"run_{uuid.uuid4().hex[:12]}"


def _resolve_source_document(source_file: str) -> Path | None:
    """Resolve an exact trusted source filename without exposing quarantine or arbitrary paths."""
    filename = Path(source_file).name
    if not filename or filename != source_file or not filename.lower().endswith(".pdf"):
        return None
    for trusted_root_name in ("data/raw", "data/archive"):
        trusted_root = Path(trusted_root_name).resolve()
        for candidate in trusted_root.glob(f"*/{filename}"):
            resolved = candidate.resolve()
            if resolved.is_file() and trusted_root in resolved.parents:
                return resolved
    return None


def _source_detail(state: ResearchState, citation_index: int) -> SourceDetail:
    citations = state.structured_report.citations if state.structured_report else state.citations
    citation = next((item for item in citations if item.citation_index == citation_index), None)
    if citation is None:
        raise HTTPException(status_code=404, detail="Citation was not found for this research run.")
    evidence = next((item for item in state.evidence if item.chunk_id == citation.chunk_id), None)
    document = _resolve_source_document(citation.source_file)
    document_url = (
        f"/research/{state.run_id}/sources/{citation.citation_index}/document" if document is not None else None
    )
    return SourceDetail(
        **citation.model_dump(),
        relevance_score=evidence.relevance_score if evidence else None,
        citation_status=evidence.citation_status if evidence else None,
        report_type=evidence.report_type if evidence else None,
        graph_path=evidence.graph_path if evidence else None,
        document_available=document is not None,
        document_url=document_url,
    )


def _serialize_state(state: ResearchState, duration_ms: float) -> dict[str, Any]:
    report = state.structured_report
    citations = report.citations if report else state.citations
    evidence_by_chunk = {item.chunk_id: item for item in state.evidence}
    sources: list[dict[str, Any]] = []
    for citation in citations:
        evidence = evidence_by_chunk.get(citation.chunk_id)
        document_available = _resolve_source_document(citation.source_file) is not None
        item = citation.model_dump()
        item.update(
            {
                "relevance_score": evidence.relevance_score if evidence else None,
                "citation_status": evidence.citation_status if evidence else None,
                "report_type": evidence.report_type if evidence else None,
                "graph_path": evidence.graph_path if evidence else None,
                "document_available": document_available,
                "document_url": (
                    f"/research/{state.run_id}/sources/{citation.citation_index}/document"
                    if document_available
                    else None
                ),
            }
        )
        sources.append(item)
    plan = state.structured_plan.model_dump() if state.structured_plan else None
    coverage = report.source_coverage_ratio if report and hasattr(report, "source_coverage_ratio") else None
    if coverage is None and citations:
        verified = sum(1 for item in sources if item["citation_status"] == "verified")
        coverage = verified / len(citations)
    budget = state.execution_budget
    return {
        "run_id": state.run_id,
        "status": state.status.value,
        "stage": state.current_stage,
        "plan": plan,
        "citations": sources,
        "evidence": [item.model_dump() for item in state.evidence],
        "warnings": state.warnings + (report.quality_warnings if report else []),
        "unanswered_questions": report.unanswered_questions if report else [],
        "metrics": {
            "duration_ms": round(duration_ms, 2),
            "evidence_count": len(state.evidence),
            "citation_count": len(citations),
            "citation_coverage": coverage,
            "search_calls": budget.search_calls_count,
            "model_calls": budget.model_calls_count,
            "input_tokens": budget.input_tokens_used,
            "output_tokens": budget.output_tokens_used,
            "estimated_cost_usd": budget.estimated_cost_usd,
            "retry_count": sum(state.retry_count.values()),
        },
    }


def _run_workflow(query: str, run_id: str, request_id: str) -> tuple[ResearchState, str, float]:
    started = time.monotonic()
    with span("research_workflow", **{"request.id": request_id}) as research_span:
        otel_trace_id = format(research_span.get_span_context().trace_id, "032x")
        state = ResearchWorkflow().run(query, run_id)
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
    return state, otel_trace_id, (time.monotonic() - started) * 1000


def _guard_output(state: ResearchState) -> Any:
    valid_citations = {
        citation.citation_index
        for citation in (state.structured_report.citations if state.structured_report is not None else [])
    }
    retrieved_context = [item.content or item.text for item in state.evidence]
    return _output_guardrails.evaluate(
        state.final_answer or "",
        valid_citations=valid_citations,
        retrieved_context=retrieved_context,
    )


def _record_completed_run(state: ResearchState) -> None:
    record_opik_run(
        run_id=state.run_id,
        status=state.status.value,
        workflow_version=state.workflow_version,
        prompt_bundle_version=state.prompt_bundle_version,
        config_hash=state.config_hash,
    )
    flush_telemetry()


def _ndjson(event_type: str, **payload: Any) -> bytes:
    return (json.dumps({"type": event_type, **payload}, ensure_ascii=False, default=str) + "\n").encode()


def _load_catalog() -> list[CompanyCatalogItem]:
    with Path("config/companies.yaml").open(encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}
    return [CompanyCatalogItem.model_validate(item) for item in payload.get("companies", [])]


@router.get("/companies", response_model=list[CompanyCatalogItem], tags=["Companies"])
async def list_companies() -> list[CompanyCatalogItem]:
    """Return repository-backed company metadata; no live market data is implied."""
    return _load_catalog()


@router.get("/{run_id}/sources/{citation_index}", response_model=SourceDetail)
async def get_source(run_id: str, citation_index: int) -> SourceDetail:
    try:
        state = JSONCheckpointSaver(settings.checkpoint_dir).load_checkpoint(run_id)
    except CheckpointNotFoundError:
        raise HTTPException(status_code=404, detail="Research run was not found.") from None
    return _source_detail(state, citation_index)


@router.get("/{run_id}/sources/{citation_index}/document")
async def get_source_document(run_id: str, citation_index: int) -> FileResponse:
    try:
        state = JSONCheckpointSaver(settings.checkpoint_dir).load_checkpoint(run_id)
    except CheckpointNotFoundError:
        raise HTTPException(status_code=404, detail="Research run was not found.") from None
    source = _source_detail(state, citation_index)
    document = _resolve_source_document(source.source_file)
    if document is None:
        raise HTTPException(status_code=404, detail="Source document is not available.")
    return FileResponse(document, media_type="application/pdf", content_disposition_type="inline")


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

    run_id = _resolve_run_id(input_result.question, request.headers.get("idempotency-key"))

    async with _semaphore:
        ACTIVE_RESEARCH.inc()
        try:
            state, otel_trace_id, _ = await anyio.to_thread.run_sync(
                _run_workflow, input_result.question, run_id, request_id
            )
        except ValueError:
            raise HTTPException(status_code=409, detail="Request conflicts with an existing research run.") from None
        except Exception:
            raise HTTPException(status_code=503, detail="Research workflow is temporarily unavailable.") from None
        finally:
            ACTIVE_RESEARCH.dec()

    output_result = _guard_output(state)
    _record_completed_run(state)
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


@router.post("/stream")
async def stream_research(payload: ResearchRequest, request: Request) -> StreamingResponse:
    """Stream real workflow progress and its guarded result as newline-delimited JSON."""
    client_key = request.client.host if request.client else "unknown"
    _enforce_rate_limit(client_key)
    request_id = current_request_id()
    input_result = _input_guardrails.evaluate(payload.query, history=payload.history)
    if input_result.blocked:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Request was rejected by input safety validation.",
        )
    run_id = _resolve_run_id(input_result.question, request.headers.get("idempotency-key"))

    async def events() -> AsyncGenerator[bytes, None]:
        yield _ndjson(
            "accepted",
            run_id=run_id,
            request_id=request_id,
            safety_action=input_result.action.value,
        )
        yield _ndjson(
            "safety",
            phase="input",
            action=input_result.action.value,
            decision_codes=[decision.code for decision in input_result.decisions],
        )
        task: asyncio.Task[tuple[ResearchState, str, float]] | None = None
        active_counted = False
        last_stage: str | None = None
        checkpoint_saver = JSONCheckpointSaver(settings.checkpoint_dir)
        try:
            async with _semaphore:
                ACTIVE_RESEARCH.inc()
                active_counted = True
                task = asyncio.create_task(
                    anyio.to_thread.run_sync(_run_workflow, input_result.question, run_id, request_id)
                )
                while not task.done():
                    try:
                        checkpoint = checkpoint_saver.load_checkpoint(run_id)
                    except CheckpointNotFoundError:
                        checkpoint = None
                    if checkpoint is not None and checkpoint.current_stage != last_stage:
                        last_stage = checkpoint.current_stage
                        yield _ndjson(
                            "stage",
                            stage=checkpoint.current_stage,
                            status=checkpoint.status.value,
                        )
                        if checkpoint.structured_plan is not None:
                            yield _ndjson("plan", plan=checkpoint.structured_plan.model_dump())
                    await asyncio.sleep(0.1)
                state, otel_trace_id, duration_ms = await task
        except ValueError:
            yield _ndjson(
                "error",
                code="conflict",
                message="Request conflicts with an existing research run.",
                recoverable=False,
            )
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            yield _ndjson(
                "error",
                code="backend_unavailable",
                message="Research workflow is temporarily unavailable.",
                recoverable=True,
            )
            return
        finally:
            if active_counted:
                ACTIVE_RESEARCH.dec()

        if state.current_stage != last_stage:
            yield _ndjson("stage", stage=state.current_stage, status=state.status.value)

        output_result = _guard_output(state)
        serialized = _serialize_state(state, duration_ms)
        yield _ndjson(
            "safety",
            phase="output",
            action=output_result.action.value,
            decision_codes=[decision.code for decision in output_result.decisions],
        )
        if serialized["plan"] is not None:
            yield _ndjson("plan", plan=serialized["plan"])
        yield _ndjson("evidence", items=serialized["evidence"])
        yield _ndjson("citations", items=serialized["citations"])
        yield _ndjson("metrics", metrics=serialized["metrics"])

        answer = output_result.text
        for offset in range(0, len(answer), 512):
            yield _ndjson("answer_delta", delta=answer[offset : offset + 512])
            await asyncio.sleep(0)

        _record_completed_run(state)
        yield _ndjson(
            "complete",
            **serialized,
            answer=answer,
            request_id=request_id,
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

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )
