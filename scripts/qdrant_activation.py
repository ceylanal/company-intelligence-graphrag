#!/usr/bin/env python3
"""Inventory, migrate, and verify Qdrant collections without exposing credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams


def _client(*, path: str | None, url: str | None, api_key_env: str) -> QdrantClient:
    if bool(path) == bool(url):
        raise ValueError("Exactly one of --path or --url is required")
    if path:
        return QdrantClient(path=path)
    api_key = os.environ.get(api_key_env, "")
    return QdrantClient(url=url, api_key=api_key or None, timeout=30)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _checksum_points(client: QdrantClient, collection: str, batch_size: int = 256) -> tuple[str, int, list[str]]:
    digest = hashlib.sha256()
    offset: Any = None
    count = 0
    samples: list[str] = []
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in sorted(points, key=lambda item: str(item.id)):
            point_id = str(point.id)
            if len(samples) < 10:
                samples.append(point_id)
            digest.update(point_id.encode())
            digest.update(b"\0")
            digest.update(json.dumps(point.payload or {}, sort_keys=True, default=str).encode())
            digest.update(b"\n")
            count += 1
        if offset is None:
            break
    return digest.hexdigest(), count, samples


def inventory(client: QdrantClient, collection: str, storage_path: str | None = None) -> dict[str, Any]:
    if not client.collection_exists(collection):
        return {
            "schema_version": "1.0.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "collection": collection,
            "exists": False,
            "points_count": 0,
            "scanned_points_count": 0,
            "vectors": None,
            "payload_schema": {},
            "status": "NOT_FOUND",
            "optimizer_status": "none",
            "sample_point_ids": [],
            "id_payload_checksum_sha256": None,
            "storage_bytes": None,
        }
    info = client.get_collection(collection)
    checksum, scanned_count, samples = _checksum_points(client, collection)
    vectors = _jsonable(info.config.params.vectors)
    payload_schema = _jsonable(info.payload_schema)
    storage_bytes = None
    if storage_path:
        storage_bytes = sum(path.stat().st_size for path in Path(storage_path).rglob("*") if path.is_file())
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "collection": collection,
        "exists": True,
        "points_count": info.points_count,
        "scanned_points_count": scanned_count,
        "vectors": vectors,
        "payload_schema": payload_schema,
        "status": str(info.status),
        "optimizer_status": str(info.optimizer_status),
        "sample_point_ids": samples,
        "id_payload_checksum_sha256": checksum,
        "storage_bytes": storage_bytes,
    }


def migrate(
    source: QdrantClient,
    target: QdrantClient,
    *,
    source_collection: str,
    target_collection: str,
    batch_size: int,
    execute: bool,
) -> dict[str, Any]:
    source_info = source.get_collection(source_collection)
    if not execute:
        return {
            "status": "DRY_RUN",
            "source_collection": source_collection,
            "target_collection": target_collection,
            "source_points": source_info.points_count,
            "batch_size": batch_size,
        }

    if not target.collection_exists(target_collection):
        vectors = source_info.config.params.vectors
        if not isinstance(vectors, VectorParams) and not isinstance(vectors, dict):
            raise ValueError("Unsupported multi-vector collection configuration")
        target.create_collection(collection_name=target_collection, vectors_config=vectors)

    offset: Any = None
    migrated = 0
    batches = 0
    while True:
        points, offset = source.scroll(
            collection_name=source_collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        batch = [
            PointStruct(id=point.id, vector=cast(Any, point.vector), payload=point.payload or {})
            for point in points
            if point.vector is not None
        ]
        if batch:
            target.upsert(collection_name=target_collection, points=batch, wait=True)
            migrated += len(batch)
            batches += 1
        if offset is None:
            break
    return {
        "status": "COMPLETED",
        "source_collection": source_collection,
        "target_collection": target_collection,
        "migrated_points": migrated,
        "batches": batches,
        "batch_size": batch_size,
    }


def _write(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    inv = subparsers.add_parser("inventory")
    inv.add_argument("--path")
    inv.add_argument("--url")
    inv.add_argument("--api-key-env", default="QDRANT_API_KEY")
    inv.add_argument("--collection", required=True)
    inv.add_argument("--output", type=Path, required=True)

    mig = subparsers.add_parser("migrate")
    mig.add_argument("--source-path")
    mig.add_argument("--source-url")
    mig.add_argument("--source-api-key-env", default="SOURCE_QDRANT_API_KEY")
    mig.add_argument("--source-collection", required=True)
    mig.add_argument("--target-url", required=True)
    mig.add_argument("--target-api-key-env", default="TARGET_QDRANT_API_KEY")
    mig.add_argument("--target-collection", required=True)
    mig.add_argument("--batch-size", type=int, default=128)
    mig.add_argument("--execute", action="store_true")
    mig.add_argument("--output", type=Path, required=True)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--source", type=Path, required=True)
    compare.add_argument("--target", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "inventory":
        client = _client(path=args.path, url=args.url, api_key_env=args.api_key_env)
        try:
            _write(args.output, inventory(client, args.collection, args.path))
        finally:
            client.close()
    elif args.command == "migrate":
        source = _client(
            path=args.source_path,
            url=args.source_url,
            api_key_env=args.source_api_key_env,
        )
        target = _client(path=None, url=args.target_url, api_key_env=args.target_api_key_env)
        try:
            report = migrate(
                source,
                target,
                source_collection=args.source_collection,
                target_collection=args.target_collection,
                batch_size=args.batch_size,
                execute=args.execute,
            )
            _write(args.output, report)
        finally:
            source.close()
            target.close()
    else:
        source_report = json.loads(args.source.read_text(encoding="utf-8"))
        target_report = json.loads(args.target.read_text(encoding="utf-8"))
        checks = {
            "points_count": source_report["points_count"] == target_report["points_count"],
            "vectors": source_report["vectors"] == target_report["vectors"],
            "payload_schema": source_report["payload_schema"] == target_report["payload_schema"],
            "id_payload_checksum": source_report["id_payload_checksum_sha256"]
            == target_report["id_payload_checksum_sha256"],
        }
        _write(
            args.output,
            {
                "schema_version": "1.0.0",
                "status": "PASS" if all(checks.values()) else "FAIL",
                "checks": checks,
                "source_collection": source_report["collection"],
                "target_collection": target_report["collection"],
            },
        )
        raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
