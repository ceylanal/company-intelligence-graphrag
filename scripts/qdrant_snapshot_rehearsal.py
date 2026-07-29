#!/usr/bin/env python3
"""Create and restore a Qdrant staging snapshot into an isolated collection."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from qdrant_client import QdrantClient
from qdrant_client.models import SnapshotPriority
from scripts.qdrant_activation import inventory


def snapshot_location(source_collection: str, snapshot_name: str) -> str:
    """Return Qdrant's in-node collection snapshot location."""
    return f"file:///qdrant/snapshots/{source_collection}/{snapshot_name}"


def _snapshot_payload(snapshot: Any) -> dict[str, Any]:
    if snapshot is None:
        return {}
    if hasattr(snapshot, "model_dump"):
        return cast(dict[str, Any], snapshot.model_dump(mode="json"))
    return {"name": str(getattr(snapshot, "name", ""))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--source-collection", required=True)
    parser.add_argument("--restore-collection", required=True)
    parser.add_argument("--api-key-env", default="QDRANT_API_KEY")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if args.source_collection == args.restore_collection:
        raise SystemExit("Restore collection must be isolated from the source collection")
    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        raise SystemExit(f"{args.api_key_env} is required")

    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_collection": args.source_collection,
        "restore_collection": args.restore_collection,
        "status": "DRY_RUN",
    }
    if not args.execute:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0

    client = QdrantClient(url=args.url, api_key=api_key, timeout=120)
    started = time.perf_counter()
    try:
        source_inventory = inventory(client, args.source_collection)
        snapshot_details: dict[str, Any]
        if client.collection_exists(args.restore_collection):
            snapshot_details = {"reused_existing_restore_target": True}
        else:
            snapshot = client.create_snapshot(args.source_collection, wait=True)
            snapshot_details = _snapshot_payload(snapshot)
            snapshot_name = str(snapshot_details.get("name") or "")
            if not snapshot_name:
                raise RuntimeError("Qdrant did not return a snapshot name")
            recovered = client.recover_snapshot(
                args.restore_collection,
                snapshot_location(args.source_collection, snapshot_name),
                priority=SnapshotPriority.SNAPSHOT,
                wait=True,
            )
            if recovered is False:
                raise RuntimeError("Qdrant snapshot recovery returned false")

        restore_inventory = inventory(client, args.restore_collection)
        checks = {
            "points_count": source_inventory["points_count"] == restore_inventory["points_count"],
            "scanned_points_count": source_inventory["scanned_points_count"]
            == restore_inventory["scanned_points_count"],
            "vectors": source_inventory["vectors"] == restore_inventory["vectors"],
            "payload_schema": source_inventory["payload_schema"] == restore_inventory["payload_schema"],
            "id_payload_checksum": source_inventory["id_payload_checksum_sha256"]
            == restore_inventory["id_payload_checksum_sha256"],
        }
        report.update(
            {
                "status": "PASS" if all(checks.values()) else "FAIL",
                "duration_seconds": round(time.perf_counter() - started, 2),
                "snapshot": snapshot_details,
                "checks": checks,
                "source_inventory": source_inventory,
                "restore_inventory": restore_inventory,
            }
        )
    finally:
        client.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
