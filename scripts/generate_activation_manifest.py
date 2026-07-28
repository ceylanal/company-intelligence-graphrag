#!/usr/bin/env python3
"""Generate a secret-free production activation manifest."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from company_graphrag.versioning.manifest import build_run_manifest

DEFAULT_CONFIG = Path("config/production_activation.yaml")
DEFAULT_OUTPUT = Path("artifacts/production_activation/activation_manifest.json")


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _presence(names: list[str]) -> dict[str, bool]:
    return {name: bool(os.environ.get(name)) for name in names}


def build_activation_manifest(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Build the activation manifest without copying credential values."""
    contract = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    run_manifest = build_run_manifest("production-activation")
    staging = contract["environments"]["staging"]
    production = contract["environments"]["production"]
    commit_sha = os.getenv("GITHUB_SHA") or _git("rev-parse", "HEAD")
    short_sha = commit_sha[:12]
    image = contract["container"]["image"]
    github_actions_status = os.getenv("ACTIVATION_GITHUB_ACTIONS_STATUS")
    if not github_actions_status:
        github_actions_status = "EXECUTING_IN_GITHUB_ACTIONS" if os.getenv("GITHUB_ACTIONS") == "true" else "NOT_VERIFIED"

    return {
        "schema_version": contract["schema_version"],
        "generated_at": datetime.now(UTC).isoformat(),
        "repository": contract["repository"],
        "git": {
            "commit_sha": commit_sha,
            "short_sha": short_sha,
            "branch": os.getenv("GITHUB_REF_NAME") or _git("branch", "--show-current"),
            "worktree_clean": not bool(_git("status", "--porcelain")),
        },
        "versioning": {
            "application_version": run_manifest.application_version,
            "prompt_bundle_version": run_manifest.prompt_bundle_version,
            "workflow_version": run_manifest.workflow_version,
            "config_hash": run_manifest.config_hash,
            "manifest_schema_version": run_manifest.schema_version,
        },
        "container": {
            "image": image,
            "candidate_tags": [
                f"{image}:sha-{short_sha}",
                f"{image}:{run_manifest.application_version}",
                f"{image}:staging",
            ],
            "digest": None,
            "signature_verified": False,
        },
        "staging": {
            "environment": staging["github_environment"],
            "cloud_run_service": staging["cloud_run_service"],
            "qdrant_collection": staging["qdrant_collection"],
            "neo4j_database": staging["neo4j_database"],
            "opik_project": staging["opik_project"],
            "grafana_environment": staging["grafana_environment"],
            "revision": None,
            "url": None,
        },
        "production": {
            "environment": production["github_environment"],
            "cloud_run_service": production["cloud_run_service"],
            "qdrant_collection": production["qdrant_collection"],
            "neo4j_database": production["neo4j_database"],
            "opik_project": production["opik_project"],
            "grafana_environment": production["grafana_environment"],
            "revision": None,
            "url": None,
        },
        "expected_smoke_tests": contract["expected_smoke_tests"],
        "expected_eval_suites": contract["expected_eval_suites"],
        "rollback_target": None,
        "credential_presence": {
            "github_secrets": _presence(contract["github"]["secrets"]),
            "application_secrets": _presence(contract["application_secrets"]),
        },
        "activation_status": {
            "github_actions": github_actions_status,
            "ghcr": "GHCR_PUBLISH_PENDING",
            "cosign": "SIGNATURE_PENDING",
            "qdrant_cloud": "BLOCKED_BY_CREDENTIALS",
            "neo4j_aura": "BLOCKED_BY_CREDENTIALS_AND_EMPTY_SOURCE_GRAPH",
            "opik": "BLOCKED_BY_CREDENTIALS",
            "grafana_cloud": "BLOCKED_BY_CREDENTIALS",
            "cloud_run_staging": "BLOCKED_BY_PREREQUISITES",
            "production": "PRODUCTION_APPROVAL_PENDING",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    manifest = build_activation_manifest(args.config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
