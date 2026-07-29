#!/usr/bin/env python3
"""Create secret-free Neo4j inventories and compare migration integrity."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase


def _driver(uri: str, username: str, password_env: str) -> Any:
    password = os.environ.get(password_env, "")
    if not password:
        raise ValueError(f"{password_env} is not configured")
    return GraphDatabase.driver(uri, auth=(username, password), connection_timeout=10)


def inventory(uri: str, username: str, password_env: str, database: str) -> dict[str, Any]:
    driver = _driver(uri, username, password_env)
    try:
        driver.verify_connectivity()
        target_db = database
        try:
            with driver.session(database=target_db) as session:
                session.run("RETURN 1").single()
        except Exception:
            target_db = "neo4j"

        with driver.session(database=target_db) as session:
            total_nodes = session.run("MATCH (n) RETURN count(n) AS count").single()["count"]
            total_relationships = session.run("MATCH ()-[r]->() RETURN count(r) AS count").single()["count"]
            labels = {
                row["label"]: row["count"]
                for row in session.run(
                    "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS count ORDER BY label"
                )
            }
            relationship_types = {
                row["type"]: row["count"]
                for row in session.run(
                    "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY type"
                )
            }
            constraints = [dict(row) for row in session.run("SHOW CONSTRAINTS YIELD *")]
            indexes = [dict(row) for row in session.run("SHOW INDEXES YIELD *")]
            sample_nodes = [
                {
                    "element_id": row["element_id"],
                    "labels": row["labels"],
                    "property_keys": row["property_keys"],
                }
                for row in session.run(
                    "MATCH (n) RETURN elementId(n) AS element_id, labels(n) AS labels, "
                    "keys(n) AS property_keys ORDER BY element_id LIMIT 10"
                )
            ]
            orphan_nodes = session.run(
                "MATCH (n) WHERE NOT (n)--() RETURN count(n) AS count"
            ).single()["count"]
            provenance_sample_count = session.run(
                "MATCH (n) WHERE n.source_id IS NOT NULL OR n.document_id IS NOT NULL "
                "OR n.chunk_id IS NOT NULL RETURN count(n) AS count"
            ).single()["count"]
    finally:
        driver.close()

    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "database": database,
        "total_nodes": total_nodes,
        "total_relationships": total_relationships,
        "labels": labels,
        "relationship_types": relationship_types,
        "constraints": constraints,
        "indexes": indexes,
        "orphan_nodes": orphan_nodes,
        "nodes_with_provenance": provenance_sample_count,
        "sample_nodes": sample_nodes,
    }


def _write(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    inv = subparsers.add_parser("inventory")
    inv.add_argument("--uri", required=True)
    inv.add_argument("--username", default="neo4j")
    inv.add_argument("--password-env", default="NEO4J_PASSWORD")
    inv.add_argument("--database", default="neo4j")
    inv.add_argument("--output", type=Path, required=True)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--source", type=Path, required=True)
    compare.add_argument("--target", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "inventory":
        _write(args.output, inventory(args.uri, args.username, args.password_env, args.database))
        return

    source = json.loads(args.source.read_text(encoding="utf-8"))
    target = json.loads(args.target.read_text(encoding="utf-8"))
    checks = {
        "total_nodes": source["total_nodes"] == target["total_nodes"],
        "total_relationships": source["total_relationships"] == target["total_relationships"],
        "labels": source["labels"] == target["labels"],
        "relationship_types": source["relationship_types"] == target["relationship_types"],
        "constraints_count": len(source["constraints"]) == len(target["constraints"]),
    }
    report = {
        "schema_version": "1.0.0",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "source_database": source["database"],
        "target_database": target["database"],
    }
    _write(args.output, report)
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
