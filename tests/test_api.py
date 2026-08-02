"""Unit and integration tests for FastAPI application and health endpoints."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from company_graphrag.agents.schema import (
    AgentWorkflowStatus,
    CitationItem,
    EvidenceItem,
    ReportOutput,
    ResearchState,
)
from company_graphrag.agents.workflow.checkpoint import JSONCheckpointSaver
from company_graphrag.api.app import app
from company_graphrag.api.health import check_qdrant_health
from company_graphrag.config import Settings


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI TestClient fixture."""
    return TestClient(app)


def test_liveness_probe(client: TestClient) -> None:
    """Verify /health/live returns HTTP 200 and expected JSON structure."""
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "live"
    assert "environment" in data


def test_version_info(client: TestClient) -> None:
    """Verify /version returns HTTP 200 with metadata."""
    response = client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "company-graphrag"
    assert data["version"] == "0.1.0"
    assert "environment" in data
    assert "python_version" in data


def test_root_endpoint(client: TestClient) -> None:
    """Verify root endpoint returns welcome metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Company Intelligence GraphRAG API"
    assert data["docs"] == "/docs"


def test_cors_allows_configured_local_frontend_origin(client: TestClient) -> None:
    """Keep browser CORS restricted to configured exact origins."""
    response = client.options(
        "/research/stream",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_qdrant_health_authenticates_cloud_request() -> None:
    """Verify the readiness check authenticates against a protected Qdrant cluster."""
    response = Response(200)
    client = AsyncMock()
    client.get.return_value = response
    context_manager = Mock()
    context_manager.__aenter__ = AsyncMock(return_value=client)
    context_manager.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("company_graphrag.api.health.settings.qdrant_api_key", "secret-qdrant-key"),
        patch("company_graphrag.api.health.httpx.AsyncClient", return_value=context_manager),
    ):
        healthy, details = asyncio.run(check_qdrant_health())

    assert healthy
    assert details["status"] == "ok"
    client.get.assert_awaited_once()
    assert client.get.await_args.kwargs["headers"] == {"api-key": "secret-qdrant-key"}


@patch("company_graphrag.api.health.check_qdrant_health")
@patch("company_graphrag.api.health.check_neo4j_health")
def test_readiness_probe_healthy(mock_neo4j: AsyncMock, mock_qdrant: AsyncMock, client: TestClient) -> None:
    """Verify /health/ready returns HTTP 200 when both services are healthy."""
    mock_qdrant.return_value = (True, {"status": "ok", "url": "http://localhost:6333", "details": "Online"})
    mock_neo4j.return_value = (True, {"status": "ok", "url": "http://localhost:7474", "details": "Online"})

    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["components"]["qdrant"]["status"] == "ok"
    assert data["components"]["neo4j"]["status"] == "ok"


@patch("company_graphrag.api.health.check_qdrant_health")
@patch("company_graphrag.api.health.check_neo4j_health")
def test_readiness_probe_qdrant_unhealthy(
    mock_neo4j: AsyncMock, mock_qdrant: AsyncMock, client: TestClient
) -> None:
    """Verify /health/ready returns HTTP 503 when Qdrant service is down."""
    mock_qdrant.return_value = (False, {"status": "error", "url": "http://localhost:6333", "details": "Connection error"})
    mock_neo4j.return_value = (True, {"status": "ok", "url": "http://localhost:7474", "details": "Online"})

    response = client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["components"]["qdrant"]["status"] == "error"
    assert data["components"]["neo4j"]["status"] == "ok"


@patch("company_graphrag.api.health.check_qdrant_health")
@patch("company_graphrag.api.health.check_neo4j_health")
def test_readiness_probe_neo4j_unhealthy(mock_neo4j: AsyncMock, mock_qdrant: AsyncMock, client: TestClient) -> None:
    """Verify /health/ready returns HTTP 503 when Neo4j service is down."""
    mock_qdrant.return_value = (True, {"status": "ok", "url": "http://localhost:6333", "details": "Online"})
    mock_neo4j.return_value = (False, {"status": "error", "url": "http://localhost:7474", "details": "Connection error"})

    response = client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["components"]["qdrant"]["status"] == "ok"
    assert data["components"]["neo4j"]["status"] == "error"


def test_settings_environment_modes() -> None:
    """Verify environment setting normalization and properties."""
    dev_settings = Settings(environment="DEVELOPMENT")
    assert dev_settings.is_development
    assert not dev_settings.is_production

    prod_settings = Settings(environment="production")
    assert prod_settings.is_production

    staging_settings = Settings(environment="staging")
    assert staging_settings.is_staging

    test_settings = Settings(environment="test")
    assert test_settings.is_test

    testing_settings = Settings(environment="testing")
    assert testing_settings.is_test

    with pytest.raises(ValueError, match="Invalid environment"):
        Settings(environment="invalid_env")


def test_company_catalog_uses_repository_configuration(client: TestClient) -> None:
    response = client.get("/research/companies")
    assert response.status_code == 200
    companies = response.json()
    assert any(company["id"] == "aselsan" for company in companies)
    assert all("market_cap" not in company for company in companies)


def test_stream_research_emits_grounded_contract(client: TestClient) -> None:
    citation = CitationItem(
        citation_index=1,
        chunk_id="chunk-1",
        company="Aselsan",
        ticker="ASELS",
        year=2024,
        source_file="ASELS__2024__annual_report__tr.pdf",
        page_number=12,
        retrieval_method="vector_search",
        snippet="Annual-report evidence.",
    )
    state = ResearchState(user_query="ASELSAN strategy")
    state.status = AgentWorkflowStatus.COMPLETED
    state.current_stage = "COMPLETED"
    state.final_answer = "Grounded answer [Source 1]"
    state.evidence = [
        EvidenceItem(
            company="Aselsan",
            ticker="ASELS",
            year=2024,
            chunk_id="chunk-1",
            page_number=12,
            source_file="ASELS__2024__annual_report__tr.pdf",
            retrieval_method="vector_search",
            content="Annual-report evidence.",
            relevance_score=0.91,
            citation_status="verified",
        )
    ]
    state.structured_report = ReportOutput(answer=state.final_answer, citations=[citation])

    with patch(
        "company_graphrag.api.research._run_workflow",
        side_effect=_streaming_workflow(state),
    ):
        response = client.post("/research/stream", json={"query": "ASELSAN strategy"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [line for line in response.text.splitlines() if line]
    event_types = [__import__("json").loads(line)["type"] for line in events]
    assert event_types[0] == "accepted"
    assert "answer_delta" in event_types
    assert event_types[-1] == "complete"
    complete = __import__("json").loads(events[-1])
    assert complete["citations"][0]["chunk_id"] == "chunk-1"
    assert complete["evidence"][0]["relevance_score"] == 0.91
    assert complete["answer"] == "Grounded answer [Source 1]"


# ---------------------------------------------------------------------------
# Helpers shared by new contract tests
# ---------------------------------------------------------------------------


def _make_grounded_state(run_id: str = "run_test_abc123") -> ResearchState:
    """Return a fully-populated ResearchState for route testing."""
    citation = CitationItem(
        citation_index=1,
        chunk_id="chunk-grounded-1",
        company="Aselsan",
        ticker="ASELS",
        year=2024,
        source_file="ASELS__2024__annual_report__tr.pdf",
        page_number=14,
        retrieval_method="hybrid_search",
        snippet="ASELSAN 2024 stratejik programlarında büyüme kaydetti.",
    )
    state = ResearchState(user_query="ASELSAN 2024 strategy?", run_id=run_id)
    state.status = AgentWorkflowStatus.COMPLETED
    state.current_stage = "COMPLETED"
    state.final_answer = "Grounded answer referencing [Source 1]."
    state.evidence = [
        EvidenceItem(
            company="Aselsan",
            ticker="ASELS",
            year=2024,
            chunk_id="chunk-grounded-1",
            page_number=14,
            source_file="ASELS__2024__annual_report__tr.pdf",
            retrieval_method="hybrid_search",
            content="ASELSAN 2024 stratejik programlarında büyüme kaydetti.",
            relevance_score=0.92,
            citation_status="verified",
            graph_path={"from": "Aselsan", "relation": "OPERATES_IN", "to": "Defense"},
        )
    ]
    state.structured_report = ReportOutput(
        answer=state.final_answer,
        citations=[citation],
    )
    return state


def _streaming_workflow(state: ResearchState):
    """Return a workflow double that emits genuine domain-style events in order."""

    def run(*_args, **kwargs):
        event_handler = kwargs.get("event_handler")
        transform_delta = kwargs.get("answer_delta_transformer")
        if event_handler is not None:
            state.citations = state.structured_report.citations if state.structured_report else state.citations
            event_handler("stage", state, {"stage": "PLANNING", "status": "planning"})
            event_handler("evidence", state, {"items": [item.model_dump() for item in state.evidence]})
            event_handler("citations", state, {})
            answer = state.final_answer or ""
            if transform_delta is not None:
                answer = transform_delta(answer, state)
            state.final_answer = answer
            if state.structured_report is not None:
                state.structured_report.answer = answer
            event_handler("answer_delta", state, {"delta": answer})
            event_handler("stage", state, {"stage": "COMPLETED", "status": "completed"})
        return state, "0" * 32, 10.0

    return run


# ---------------------------------------------------------------------------
# Contract: GET /research/companies
# ---------------------------------------------------------------------------


def test_companies_returns_catalog_array(client: TestClient) -> None:
    """GET /research/companies must return a JSON array of CompanyCatalogItem objects."""
    response = client.get("/research/companies")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    companies = response.json()
    assert isinstance(companies, list)
    assert len(companies) >= 1
    # Every item must have the required keys matching the frontend Company type
    for company in companies:
        assert "id" in company
        assert "name" in company
        assert isinstance(company["aliases"], list)
        assert isinstance(company["official_domains"], list)
        assert isinstance(company["years"], list)
    # aselsan must be present (used by E2E fixtures)
    assert any(c["id"] == "aselsan" for c in companies)


def test_companies_contains_no_market_data(client: TestClient) -> None:
    """Company catalog must not expose live market data fields."""
    response = client.get("/research/companies")
    assert response.status_code == 200
    for company in response.json():
        assert "market_cap" not in company
        assert "price" not in company
        assert "pe_ratio" not in company


# ---------------------------------------------------------------------------
# Contract: POST /research/stream — event-type ordering
# ---------------------------------------------------------------------------


def test_stream_accepted_event_is_first(client: TestClient) -> None:
    """The first NDJSON event must be 'accepted' with run_id and request_id."""
    state = _make_grounded_state()
    with patch("company_graphrag.api.research._run_workflow", side_effect=_streaming_workflow(state)):
        response = client.post("/research/stream", json={"query": "ASELSAN strategy?"})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events[0]["type"] == "accepted"
    assert "run_id" in events[0]
    assert "request_id" in events[0]
    assert "safety_action" in events[0]


def test_stream_complete_event_is_last(client: TestClient) -> None:
    """The last NDJSON event must be 'complete' with answer, citations, and metrics."""
    state = _make_grounded_state()
    with patch("company_graphrag.api.research._run_workflow", side_effect=_streaming_workflow(state)):
        response = client.post("/research/stream", json={"query": "ASELSAN strategy?"})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events[-1]["type"] == "complete"
    complete = events[-1]
    assert "answer" in complete
    assert "citations" in complete
    assert "evidence" in complete
    assert "metrics" in complete
    assert "run_id" in complete
    assert "request_id" in complete


def test_stream_event_sequence_satisfies_frontend_contract(client: TestClient) -> None:
    """Stream must emit: accepted, safety(input), stage*, evidence, citations, metrics, answer_delta*, complete."""
    state = _make_grounded_state()
    with patch("company_graphrag.api.research._run_workflow", side_effect=_streaming_workflow(state)):
        response = client.post("/research/stream", json={"query": "ASELSAN strategy?"})
    assert response.status_code == 200
    event_types = [json.loads(line)["type"] for line in response.text.splitlines() if line.strip()]

    assert event_types[0] == "accepted"
    assert event_types[-1] == "complete"
    assert "answer_delta" in event_types
    assert "evidence" in event_types
    assert "citations" in event_types
    assert "metrics" in event_types

    # answer_delta events must all precede complete
    last_delta = max(i for i, t in enumerate(event_types) if t == "answer_delta")
    complete_idx = event_types.index("complete")
    assert last_delta < complete_idx


def test_stream_complete_carries_graph_path_in_citations(client: TestClient) -> None:
    """Citations inside 'complete' must carry graph_path when evidence provides it."""
    state = _make_grounded_state()
    with patch("company_graphrag.api.research._run_workflow", side_effect=_streaming_workflow(state)):
        response = client.post("/research/stream", json={"query": "ASELSAN strategy?"})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    complete = next(e for e in events if e["type"] == "complete")
    citation = complete["citations"][0]
    assert citation["graph_path"] is not None
    assert isinstance(citation["graph_path"], (dict, list, str))


def test_stream_safety_input_event_present(client: TestClient) -> None:
    """Input safety phase must be emitted early in the stream."""
    state = _make_grounded_state()
    with patch("company_graphrag.api.research._run_workflow", side_effect=_streaming_workflow(state)):
        response = client.post("/research/stream", json={"query": "ASELSAN strategy?"})
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    safety_input = next((e for e in events if e["type"] == "safety" and e.get("phase") == "input"), None)
    assert safety_input is not None
    assert "action" in safety_input
    assert "decision_codes" in safety_input


def test_stream_emits_answer_delta_chunks(client: TestClient) -> None:
    """Answer must be split into answer_delta chunks covering the full answer text."""
    state = _make_grounded_state()
    with patch("company_graphrag.api.research._run_workflow", side_effect=_streaming_workflow(state)):
        response = client.post("/research/stream", json={"query": "ASELSAN strategy?"})
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    deltas = [e["delta"] for e in events if e["type"] == "answer_delta"]
    assert deltas  # must have at least one delta
    reconstructed = "".join(deltas)
    complete_answer = next(e["answer"] for e in events if e["type"] == "complete")
    assert reconstructed == complete_answer


def test_stream_metrics_has_required_fields(client: TestClient) -> None:
    """Metrics event must contain all fields expected by ResearchMetrics type."""
    state = _make_grounded_state()
    with patch("company_graphrag.api.research._run_workflow", side_effect=_streaming_workflow(state)):
        response = client.post("/research/stream", json={"query": "ASELSAN strategy?"})
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    metrics_event = next(e for e in events if e["type"] == "metrics")
    m = metrics_event["metrics"]
    for field in (
        "duration_ms",
        "evidence_count",
        "citation_count",
        "search_calls",
        "model_calls",
        "input_tokens",
        "output_tokens",
        "estimated_cost_usd",
        "retry_count",
    ):
        assert field in m, f"metrics missing field: {field}"


def test_stream_backend_error_emits_error_event(client: TestClient) -> None:
    """When the workflow raises an unexpected exception, an 'error' event is emitted."""
    with patch("company_graphrag.api.research._run_workflow", side_effect=RuntimeError("infra failure")):
        response = client.post("/research/stream", json={"query": "ASELSAN strategy?"})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    error_event = next((e for e in events if e["type"] == "error"), None)
    assert error_event is not None
    assert error_event["code"] == "backend_unavailable"
    assert error_event["recoverable"] is True


def test_stream_conflict_emits_error_event(client: TestClient) -> None:
    """When the workflow raises ValueError (conflict), a 'conflict' error event is emitted."""
    with patch("company_graphrag.api.research._run_workflow", side_effect=ValueError("conflict")):
        response = client.post("/research/stream", json={"query": "ASELSAN strategy?"})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    error_event = next((e for e in events if e["type"] == "error"), None)
    assert error_event is not None
    assert error_event["code"] == "conflict"
    assert error_event["recoverable"] is False


def test_stream_content_type_is_ndjson(client: TestClient) -> None:
    """Streaming endpoint must declare application/x-ndjson content-type."""
    state = _make_grounded_state()
    with patch("company_graphrag.api.research._run_workflow", side_effect=_streaming_workflow(state)):
        response = client.post("/research/stream", json={"query": "test"})
    assert response.headers["content-type"].startswith("application/x-ndjson")


def test_stream_cache_control_header_disables_caching(client: TestClient) -> None:
    """Streaming response must send Cache-Control: no-cache to prevent buffering."""
    state = _make_grounded_state()
    with patch("company_graphrag.api.research._run_workflow", side_effect=_streaming_workflow(state)):
        response = client.post("/research/stream", json={"query": "test"})
    cache_control = response.headers.get("cache-control", "")
    assert "no-cache" in cache_control


# ---------------------------------------------------------------------------
# Contract: GET /research/{run_id}/sources/{citation_index}
# ---------------------------------------------------------------------------


def test_get_source_returns_citation_detail(client: TestClient) -> None:
    """GET /research/{run_id}/sources/{idx} returns SourceDetail from checkpoint."""
    state = _make_grounded_state(run_id="run_source_detail_test")
    with (
        tempfile.TemporaryDirectory() as tmp_dir,
        patch("company_graphrag.api.research.settings.checkpoint_dir", tmp_dir),
    ):
        JSONCheckpointSaver(tmp_dir).save_checkpoint(state)
        response = client.get("/research/run_source_detail_test/sources/1")

    assert response.status_code == 200
    data = response.json()
    assert data["citation_index"] == 1
    assert data["chunk_id"] == "chunk-grounded-1"
    assert data["company"] == "Aselsan"
    assert data["ticker"] == "ASELS"
    assert data["year"] == 2024
    assert data["source_file"] == "ASELS__2024__annual_report__tr.pdf"
    assert data["page_number"] == 14
    assert data["retrieval_method"] == "hybrid_search"
    assert "snippet" in data
    assert "document_available" in data


def test_get_source_returns_relevance_score_from_evidence(client: TestClient) -> None:
    """SourceDetail must include relevance_score when matching evidence exists."""
    state = _make_grounded_state(run_id="run_evidence_score_test")
    with (
        tempfile.TemporaryDirectory() as tmp_dir,
        patch("company_graphrag.api.research.settings.checkpoint_dir", tmp_dir),
    ):
        JSONCheckpointSaver(tmp_dir).save_checkpoint(state)
        response = client.get("/research/run_evidence_score_test/sources/1")

    assert response.status_code == 200
    data = response.json()
    assert data["relevance_score"] == pytest.approx(0.92, rel=1e-3)
    assert data["citation_status"] == "verified"


def test_get_source_unknown_run_id_returns_404(client: TestClient) -> None:
    """Missing checkpoint must return HTTP 404."""
    with (
        tempfile.TemporaryDirectory() as tmp_dir,
        patch("company_graphrag.api.research.settings.checkpoint_dir", tmp_dir),
    ):
        response = client.get("/research/run_does_not_exist_xyz/sources/1")
    assert response.status_code == 404


def test_get_source_unknown_citation_index_returns_404(client: TestClient) -> None:
    """Citation index not in checkpoint must return HTTP 404."""
    state = _make_grounded_state(run_id="run_bad_citation_test")
    with (
        tempfile.TemporaryDirectory() as tmp_dir,
        patch("company_graphrag.api.research.settings.checkpoint_dir", tmp_dir),
    ):
        JSONCheckpointSaver(tmp_dir).save_checkpoint(state)
        response = client.get("/research/run_bad_citation_test/sources/999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Contract: GET /research/{run_id}/sources/{citation_index}/document
# ---------------------------------------------------------------------------


def test_get_source_document_returns_404_when_no_pdf(client: TestClient) -> None:
    """When source PDF is not on disk, document endpoint must return HTTP 404."""
    state = _make_grounded_state(run_id="run_no_pdf_test")
    with (
        tempfile.TemporaryDirectory() as tmp_dir,
        patch("company_graphrag.api.research.settings.checkpoint_dir", tmp_dir),
        patch("company_graphrag.api.research._resolve_source_document", return_value=None),
    ):
        JSONCheckpointSaver(tmp_dir).save_checkpoint(state)
        response = client.get("/research/run_no_pdf_test/sources/1/document")
    assert response.status_code == 404


def test_get_source_document_returns_pdf_when_available(client: TestClient) -> None:
    """When source PDF exists, document endpoint must stream it as application/pdf."""
    state = _make_grounded_state(run_id="run_pdf_available_test")
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_pdf = Path(tmp_dir) / "ASELS__2024__annual_report__tr.pdf"
        # Minimal valid PDF bytes
        fake_pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        with (
            patch("company_graphrag.api.research.settings.checkpoint_dir", tmp_dir),
            patch("company_graphrag.api.research._resolve_source_document", return_value=fake_pdf),
        ):
            JSONCheckpointSaver(tmp_dir).save_checkpoint(state)
            response = client.get("/research/run_pdf_available_test/sources/1/document")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")


def test_get_source_document_honors_http_range_requests(client: TestClient) -> None:
    """The BFF can forward browser PDF range requests without buffering the file."""
    state = _make_grounded_state(run_id="run_pdf_range_test")
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_pdf = Path(tmp_dir) / "ASELS__2024__annual_report__tr.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4\nrange-check\n%%EOF\n")
        with (
            patch("company_graphrag.api.research.settings.checkpoint_dir", tmp_dir),
            patch("company_graphrag.api.research._resolve_source_document", return_value=fake_pdf),
        ):
            JSONCheckpointSaver(tmp_dir).save_checkpoint(state)
            response = client.get(
                "/research/run_pdf_range_test/sources/1/document",
                headers={"Range": "bytes=0-7"},
            )
    assert response.status_code == 206
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-range"] == "bytes 0-7/27"
    assert response.content == b"%PDF-1.4"


def test_get_source_document_run_not_found_returns_404(client: TestClient) -> None:
    """Missing run checkpoint for document endpoint must return HTTP 404."""
    with (
        tempfile.TemporaryDirectory() as tmp_dir,
        patch("company_graphrag.api.research.settings.checkpoint_dir", tmp_dir),
    ):
        response = client.get("/research/run_ghost_xyz/sources/1/document")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Contract: POST /research (non-streaming)
# ---------------------------------------------------------------------------


def test_non_streaming_research_returns_run_id_and_answer(client: TestClient) -> None:
    """Non-streaming /research must return JSON with run_id, status, and answer."""
    state = _make_grounded_state()
    with patch("company_graphrag.api.research._run_workflow", return_value=(state, "0" * 32, 20.0)):
        response = client.post("/research", json={"query": "ASELSAN strategy?"})
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert "status" in data
    assert "answer" in data
    assert "request_id" in data
    assert "metadata" in data


def test_non_streaming_research_metadata_has_trace_id(client: TestClient) -> None:
    """Non-streaming /research metadata must include otel_trace_id for observability."""
    state = _make_grounded_state()
    with patch("company_graphrag.api.research._run_workflow", return_value=(state, "a" * 32, 18.0)):
        response = client.post("/research", json={"query": "ASELSAN strategy?"})
    assert response.status_code == 200
    meta = response.json()["metadata"]
    assert "otel_trace_id" in meta
    assert "input_safety_action" in meta
    assert "output_safety_action" in meta


def test_non_streaming_backend_error_returns_503(client: TestClient) -> None:
    """Unexpected workflow exception on /research must return HTTP 503."""
    with patch("company_graphrag.api.research._run_workflow", side_effect=RuntimeError("infra")):
        response = client.post("/research", json={"query": "ASELSAN strategy?"})
    assert response.status_code == 503


def test_non_streaming_conflict_returns_409(client: TestClient) -> None:
    """ValueError from workflow must map to HTTP 409 Conflict on /research."""
    with patch("company_graphrag.api.research._run_workflow", side_effect=ValueError("conflict")):
        response = client.post("/research", json={"query": "ASELSAN strategy?"})
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Contract: API key middleware
# ---------------------------------------------------------------------------


def test_research_endpoints_reject_wrong_api_key(client: TestClient) -> None:
    """When API_KEY is configured, /research/* must return 401 for wrong key."""
    with patch("company_graphrag.api.app.settings.api_key", "secret-key"):
        response = client.post(
            "/research",
            json={"query": "ASELSAN strategy?"},
            headers={"x-api-key": "wrong-key"},
        )
    assert response.status_code == 401


def test_research_endpoints_reject_missing_api_key(client: TestClient) -> None:
    """When API_KEY is configured, /research/* must return 401 when key is absent."""
    with patch("company_graphrag.api.app.settings.api_key", "secret-key"):
        response = client.post("/research", json={"query": "ASELSAN strategy?"})
    assert response.status_code == 401


def test_research_endpoints_accept_correct_api_key(client: TestClient) -> None:
    """When API_KEY is configured, /research/* must proceed with correct key."""
    state = _make_grounded_state()
    with (
        patch("company_graphrag.api.app.settings.api_key", "correct-key"),
        patch("company_graphrag.api.research._run_workflow", return_value=(state, "0" * 32, 10.0)),
    ):
        response = client.post(
            "/research",
            json={"query": "ASELSAN strategy?"},
            headers={"x-api-key": "correct-key"},
        )
    assert response.status_code == 200


def test_health_endpoints_do_not_require_api_key(client: TestClient) -> None:
    """Health routes must be accessible without an API key even when one is configured."""
    with patch("company_graphrag.api.app.settings.api_key", "secret-key"):
        response = client.get("/health/live")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Contract: Request size limit
# ---------------------------------------------------------------------------


def test_oversized_request_returns_413(client: TestClient) -> None:
    """A body exceeding request_max_bytes must return HTTP 413."""
    giant_query = "x" * 2_000_000
    with patch("company_graphrag.api.app.settings.request_max_bytes", 1024):
        response = client.post(
            "/research",
            content=json.dumps({"query": giant_query}).encode(),
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 413


# ---------------------------------------------------------------------------
# Contract: OpenAPI schema contains all required routes
# ---------------------------------------------------------------------------


def test_openapi_schema_exposes_stream_route(client: TestClient) -> None:
    """The published OpenAPI schema must include POST /research/stream."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/research/stream" in paths
    assert "post" in paths["/research/stream"]


def test_openapi_schema_exposes_companies_route(client: TestClient) -> None:
    """The published OpenAPI schema must include GET /research/companies."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/research/companies" in paths
    assert "get" in paths["/research/companies"]


def test_openapi_schema_exposes_source_detail_route(client: TestClient) -> None:
    """The published OpenAPI schema must include GET /research/{run_id}/sources/{citation_index}."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/research/{run_id}/sources/{citation_index}" in paths


def test_openapi_schema_exposes_source_document_route(client: TestClient) -> None:
    """The published OpenAPI schema must include GET .../sources/{citation_index}/document."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/research/{run_id}/sources/{citation_index}/document" in paths


def test_openapi_schema_exposes_health_routes(client: TestClient) -> None:
    """The published OpenAPI schema must include /health/live and /health/ready."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health/live" in paths
    assert "/health/ready" in paths
