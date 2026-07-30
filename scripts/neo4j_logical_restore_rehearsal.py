#!/usr/bin/env python3
"""Export Aura logically and verify a restore into an isolated Neo4j database."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

TOKEN_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TEMP_SOURCE_ID = "__dr_source_id"


def _safe_token(value: str, kind: str) -> str:
    if not TOKEN_PATTERN.fullmatch(value):
        raise ValueError(f"Unsafe Neo4j {kind}: {value!r}")
    return value


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "iso_format"):
        return value.iso_format()
    return str(value)


def graph_checksum(nodes: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> str:
    """Return a stable checksum independent of Neo4j element IDs."""
    canonical_nodes = [
        {
            "source_id": item["source_id"],
            "labels": sorted(item["labels"]),
            "properties": _jsonable(
                {key: value for key, value in item["properties"].items() if key != TEMP_SOURCE_ID}
            ),
        }
        for item in nodes
    ]
    canonical_relationships = [
        {
            "start_id": item["start_id"],
            "end_id": item["end_id"],
            "type": item["type"],
            "properties": _jsonable(item["properties"]),
        }
        for item in relationships
    ]
    payload = {
        "nodes": sorted(canonical_nodes, key=lambda item: item["source_id"]),
        "relationships": sorted(
            canonical_relationships,
            key=lambda item: (
                item["start_id"],
                item["end_id"],
                item["type"],
                json.dumps(item["properties"], sort_keys=True, default=str),
            ),
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def export_graph(driver: Any, database: str, restored: bool = False) -> dict[str, Any]:
    """Read a complete logical graph representation."""
    node_id = f"n.{TEMP_SOURCE_ID}" if restored else "elementId(n)"
    start_id = f"a.{TEMP_SOURCE_ID}" if restored else "elementId(a)"
    end_id = f"b.{TEMP_SOURCE_ID}" if restored else "elementId(b)"
    with driver.session(database=database) as session:
        nodes = [
            {
                "source_id": str(record["source_id"]),
                "labels": list(record["labels"]),
                "properties": dict(record["properties"]),
            }
            for record in session.run(
                f"MATCH (n) RETURN {node_id} AS source_id, labels(n) AS labels, "
                "properties(n) AS properties"
            )
        ]
        relationships = [
            {
                "start_id": str(record["start_id"]),
                "end_id": str(record["end_id"]),
                "type": str(record["type"]),
                "properties": dict(record["properties"]),
            }
            for record in session.run(
                f"MATCH (a)-[r]->(b) RETURN {start_id} AS start_id, {end_id} AS end_id, "
                "type(r) AS type, properties(r) AS properties"
            )
        ]
    return {"nodes": nodes, "relationships": relationships}


def restore_graph(driver: Any, database: str, graph: dict[str, Any]) -> None:
    """Restore the export into a target that must be empty."""
    with driver.session(database=database) as session:
        count = session.run("MATCH (n) RETURN count(n) AS count").single()["count"]
        if count:
            raise RuntimeError("Restore target is not empty")

        node_groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for node in graph["nodes"]:
            labels = tuple(sorted(_safe_token(label, "label") for label in node["labels"]))
            node_groups.setdefault(labels, []).append(node)
        for labels, rows in node_groups.items():
            label_clause = "".join(f":`{label}`" for label in labels)
            session.run(
                f"UNWIND $rows AS row CREATE (n{label_clause}) "
                f"SET n = row.properties SET n.{TEMP_SOURCE_ID} = row.source_id",
                rows=rows,
            ).consume()

        relationship_groups: dict[str, list[dict[str, Any]]] = {}
        for relationship in graph["relationships"]:
            rel_type = _safe_token(relationship["type"], "relationship type")
            relationship_groups.setdefault(rel_type, []).append(relationship)
        for rel_type, rows in relationship_groups.items():
            session.run(
                f"UNWIND $rows AS row MATCH (a {{{TEMP_SOURCE_ID}: row.start_id}}), "
                f"(b {{{TEMP_SOURCE_ID}: row.end_id}}) CREATE (a)-[r:`{rel_type}`]->(b) "
                "SET r = row.properties",
                rows=rows,
            ).consume()


def _connect(uri: str, username: str, password: str, database: str, attempts: int = 30) -> Any:
    driver = GraphDatabase.driver(uri, auth=(username, password))
    for attempt in range(attempts):
        try:
            driver.verify_connectivity()
            with driver.session(database=database) as session:
                session.run("RETURN 1").consume()
            return driver
        except Exception:
            if attempt == attempts - 1:
                driver.close()
                raise
            time.sleep(2)
    raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-uri", required=True)
    parser.add_argument("--source-username", required=True)
    parser.add_argument("--source-database", default="neo4j")
    parser.add_argument("--source-password-env", default="NEO4J_PASSWORD")
    parser.add_argument("--target-uri", required=True)
    parser.add_argument("--target-username", required=True)
    parser.add_argument("--target-database", default="neo4j")
    parser.add_argument("--target-password-env", default="NEO4J_RESTORE_PASSWORD")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy": "logical_export_isolated_restore",
        "provider_native_snapshot_available": False,
        "status": "DRY_RUN",
    }
    if not args.execute:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0

    source_password = os.environ.get(args.source_password_env, "")
    target_password = os.environ.get(args.target_password_env, "")
    if not source_password or not target_password:
        raise SystemExit("Source and target password environment variables are required")

    started = time.perf_counter()
    source = _connect(
        args.source_uri, args.source_username, source_password, args.source_database
    )
    target = _connect(
        args.target_uri, args.target_username, target_password, args.target_database
    )
    try:
        exported = export_graph(source, args.source_database)
        restore_graph(target, args.target_database, exported)
        restored = export_graph(target, args.target_database, restored=True)
        source_checksum = graph_checksum(exported["nodes"], exported["relationships"])
        target_checksum = graph_checksum(restored["nodes"], restored["relationships"])
        checks = {
            "node_count": len(exported["nodes"]) == len(restored["nodes"]),
            "relationship_count": len(exported["relationships"])
            == len(restored["relationships"]),
            "canonical_checksum": source_checksum == target_checksum,
        }
        report.update(
            {
                "status": "PASS" if all(checks.values()) else "FAIL",
                "duration_seconds": round(time.perf_counter() - started, 2),
                "checks": checks,
                "source": {
                    "node_count": len(exported["nodes"]),
                    "relationship_count": len(exported["relationships"]),
                    "checksum_sha256": source_checksum,
                },
                "restored": {
                    "node_count": len(restored["nodes"]),
                    "relationship_count": len(restored["relationships"]),
                    "checksum_sha256": target_checksum,
                },
            }
        )
    finally:
        source.close()
        target.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
