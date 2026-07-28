"""Health and status check routes for FastAPI application."""

import sys
import time
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Response, status
from neo4j import AsyncGraphDatabase

from company_graphrag import __version__
from company_graphrag.config import settings
from company_graphrag.observability.metrics import DEPENDENCY_LATENCY
from company_graphrag.versioning.manifest import build_run_manifest

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Health & Status"])


async def check_qdrant_health() -> tuple[bool, dict[str, Any]]:
    """Verify connection health to Qdrant REST service."""
    url = f"{settings.effective_qdrant_url}/healthz"
    try:
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=settings.health_timeout_seconds) as client:
            res = await client.get(url)
            DEPENDENCY_LATENCY.labels("qdrant", "health").observe(time.monotonic() - started)
            if res.status_code == 200:
                return True, {"status": "ok", "latency_ms": round((time.monotonic() - started) * 1000, 2)}
            return False, {
                "status": "error",
                "details": f"HTTP status {res.status_code}",
            }
    except Exception as err:
        return False, {
            "status": "error",
            "details": "Connection failed",
            "error_type": type(err).__name__,
        }


async def check_neo4j_health() -> tuple[bool, dict[str, Any]]:
    """Verify connection health to Neo4j HTTP service."""
    started = time.monotonic()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
        connection_timeout=settings.health_timeout_seconds,
    )
    try:
        await driver.verify_connectivity()
        DEPENDENCY_LATENCY.labels("neo4j", "health").observe(time.monotonic() - started)
        return True, {"status": "ok", "latency_ms": round((time.monotonic() - started) * 1000, 2)}
    except Exception as err:
        return False, {
            "status": "error",
            "details": "Connection failed",
            "error_type": type(err).__name__,
        }
    finally:
        await driver.close()


@router.get("/health/live", summary="Liveness probe", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict[str, Any]:
    """Check if the API container is running and healthy."""
    return {
        "status": "live",
        "environment": settings.environment,
    }


@router.get("/health/ready", summary="Readiness probe")
async def readiness_probe(response: Response) -> dict[str, Any]:
    """Verify independent connectivity to required storage backends (Qdrant & Neo4j)."""
    qdrant_ok, qdrant_info = await check_qdrant_health()
    neo4j_ok, neo4j_info = await check_neo4j_health()

    is_ready = qdrant_ok and neo4j_ok
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "healthy" if is_ready else "unhealthy",
        "environment": settings.environment,
        "components": {
            "qdrant": qdrant_info,
            "neo4j": neo4j_info,
        },
    }


@router.get("/version", summary="Application version details", status_code=status.HTTP_200_OK)
async def version_info() -> dict[str, Any]:
    """Return version and environment metadata."""
    manifest = build_run_manifest("version")
    return {
        "name": "company-graphrag",
        "version": settings.app_version or __version__,
        "git_commit_sha": manifest.git_commit_sha,
        "environment": settings.environment,
        "python_version": sys.version.split()[0],
        "workflow_version": manifest.workflow_version,
        "prompt_bundle_version": manifest.prompt_bundle_version,
        "config_hash": manifest.config_hash,
        "manifest_schema_version": manifest.schema_version,
    }
