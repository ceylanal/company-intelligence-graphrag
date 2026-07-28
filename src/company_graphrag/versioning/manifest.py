"""Public, deterministic run manifest generation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from company_graphrag import __version__
from company_graphrag.config import Settings, settings
from company_graphrag.versioning.prompts import PromptRegistry, get_prompt_registry


class RunManifest(BaseModel):
    """Machine-readable provenance for one research run."""

    schema_version: str = "1.0.0"
    run_id: str
    created_at: str
    application_version: str
    git_commit_sha: str
    environment: str
    prompt_bundle_version: str
    prompt_versions: dict[str, str]
    llm: dict[str, Any]
    embedding: dict[str, Any]
    chunking: dict[str, Any]
    qdrant: dict[str, Any]
    graph: dict[str, Any]
    retrieval: dict[str, Any]
    workflow_version: str
    citation_validation_version: str
    eval: dict[str, Any]
    config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def _git_sha(configured_sha: str) -> str:
    if configured_sha and configured_sha != "unknown":
        return configured_sha
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def public_config(settings_obj: Settings, registry: PromptRegistry) -> dict[str, Any]:
    """Return the allowlisted reproducibility configuration.

    Connection URLs, credentials, headers, user input, and prompt bodies are
    intentionally excluded.
    """
    return {
        "application_version": settings_obj.app_version or __version__,
        "environment": settings_obj.environment,
        "prompt_bundle_version": registry.bundle_version,
        "prompt_bundle_fingerprint": registry.bundle_fingerprint(),
        "prompt_versions": {
            prompt_id: prompt.version for prompt_id, prompt in sorted(registry.prompts.items())
        },
        "llm": {
            "provider": settings_obj.llm_provider,
            "model": settings_obj.llm_model,
            "fallback_model": settings_obj.llm_fallback_model or None,
            "temperature": settings_obj.llm_temperature,
        },
        "embedding": {"model": settings_obj.embedding_model},
        "chunking": {
            "target_tokens": settings_obj.chunk_target_tokens,
            "overlap_tokens": settings_obj.chunk_overlap_tokens,
        },
        "qdrant": {
            "collection": settings_obj.qdrant_collection_name,
            "collection_version": settings_obj.qdrant_collection_version,
        },
        "graph": {"schema_version": settings_obj.graph_schema_version},
        "retrieval": {"version": settings_obj.retrieval_version},
        "workflow_version": settings_obj.workflow_version,
        "citation_validation_version": settings_obj.citation_validation_version,
        "eval": {
            "dataset_version": settings_obj.eval_dataset_version,
            "rubric_version": settings_obj.eval_rubric_version,
        },
    }


def config_hash(settings_obj: Settings = settings, registry: PromptRegistry | None = None) -> str:
    """Hash canonical JSON for critical, non-secret settings."""
    prompt_registry = registry or get_prompt_registry()
    canonical = json.dumps(
        public_config(settings_obj, prompt_registry),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_run_manifest(
    run_id: str,
    *,
    settings_obj: Settings = settings,
    registry: PromptRegistry | None = None,
    created_at: str | None = None,
) -> RunManifest:
    """Build a complete public manifest for one run."""
    prompt_registry = registry or get_prompt_registry()
    public = public_config(settings_obj, prompt_registry)
    return RunManifest(
        run_id=run_id,
        created_at=created_at or datetime.now(UTC).isoformat(),
        git_commit_sha=_git_sha(settings_obj.git_commit_sha),
        config_hash=config_hash(settings_obj, prompt_registry),
        **public,
    )


def save_run_manifest(manifest: RunManifest, directory: str | Path | None = None) -> Path:
    """Atomically persist one manifest without overwriting another run."""
    output_dir = Path(directory or settings.run_manifest_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{manifest.run_id}.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target
