"""FastAPI application entrypoint for Company Intelligence GraphRAG."""

import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from company_graphrag import __version__
from company_graphrag.api.health import router as health_router
from company_graphrag.api.research import router as research_router
from company_graphrag.config import settings
from company_graphrag.observability.context import bind_context, reset_context
from company_graphrag.observability.logging import configure_logging
from company_graphrag.observability.metrics import HTTP_LATENCY, HTTP_REQUESTS
from company_graphrag.observability.tracing import configure_telemetry

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and graceful shutdown lifecycle events."""
    configure_logging()
    configure_telemetry()
    logger.info(
        "application_started",
        environment=settings.environment,
        log_level=settings.log_level,
        version=settings.app_version or __version__,
    )
    yield
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()
    logger.info("application_stopped")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application instance."""
    app = FastAPI(
        title="Company Intelligence GraphRAG API",
        description="Production API for Hybrid GraphRAG system combining vector search and knowledge graph.",
        version=settings.app_version or __version__,
        lifespan=lifespan,
    )

    app.include_router(health_router)
    app.include_router(research_router)
    cors_origins = [origin.strip().rstrip("/") for origin in settings.cors_allowed_origins.split(",") if origin.strip()]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "Idempotency-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID", "X-Run-ID", "X-Trace-ID"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex}"
        run_id = request.headers.get("x-run-id") or f"run_{uuid.uuid4().hex[:16]}"
        incoming_trace_id = request.headers.get("x-trace-id")
        trace_id = incoming_trace_id or uuid.uuid4().hex
        tokens = bind_context(request_id=request_id, run_id=run_id, trace_id=trace_id)
        started = time.monotonic()
        route = request.url.path
        status_code = 500
        try:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > settings.request_max_bytes:
                response: Response = JSONResponse(
                    status_code=413,
                    content={"detail": "Request body exceeds configured limit", "request_id": request_id},
                )
            elif route.startswith("/research") and settings.api_key:
                supplied = request.headers.get("x-api-key", "")
                if supplied != settings.api_key:
                    response = JSONResponse(
                        status_code=401,
                        content={"detail": "Authentication required", "request_id": request_id},
                    )
                else:
                    response = await call_next(request)
            else:
                response = await call_next(request)
            status_code = response.status_code
            response.headers["x-request-id"] = request_id
            response.headers["x-run-id"] = run_id
            response.headers["x-trace-id"] = trace_id
            return response
        finally:
            duration = time.monotonic() - started
            HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
            HTTP_LATENCY.labels(request.method, route).observe(duration)
            logger.info(
                "http_request_completed",
                method=request.method,
                route=route,
                status=status_code,
                duration_ms=round(duration * 1000, 2),
            )
            reset_context(tokens)

    @app.get("/", tags=["General"])
    async def root() -> dict[str, str]:
        return {
            "message": "Company Intelligence GraphRAG API",
            "version": settings.app_version or __version__,
            "docs": "/docs",
            "health": "/health/live",
        }

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    if settings.telemetry_enabled:
        FastAPIInstrumentor.instrument_app(app)

    return app


app = create_app()
