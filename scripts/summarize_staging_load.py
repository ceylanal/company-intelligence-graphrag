#!/usr/bin/env python3
"""Aggregate bounded Locust staging stages into a machine-readable baseline."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _number(row: dict[str, str], key: str) -> float:
    raw = row.get(key, "0").strip()
    return float(raw) if raw else 0.0


def summarize_stage(path: Path, users: int) -> dict[str, Any]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    aggregate = next((row for row in rows if row.get("Name") == "Aggregated"), None)
    if aggregate is None:
        raise ValueError(f"Aggregated Locust row is missing from {path}")
    requests = int(_number(aggregate, "Request Count"))
    failures = int(_number(aggregate, "Failure Count"))
    return {
        "users": users,
        "requests": requests,
        "failures": failures,
        "success_rate": round((requests - failures) / max(1, requests), 4),
        "failure_rate": round(failures / max(1, requests), 4),
        "p50_latency_ms": _number(aggregate, "50%"),
        "p95_latency_ms": _number(aggregate, "95%"),
        "p99_latency_ms": _number(aggregate, "99%"),
        "max_latency_ms": _number(aggregate, "Max Response Time"),
        "requests_per_second": _number(aggregate, "Requests/s"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-digest", required=True)
    args = parser.parse_args()

    stages = [
        summarize_stage(args.input_dir / f"users-{users}_stats.csv", users)
        for users in (1, 5, 10)
    ]
    payload = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "image_digest": args.image_digest,
        "scope": "private staging health/readiness/version endpoints; no repeated paid-model traffic",
        "stages": stages,
        "total_requests": sum(stage["requests"] for stage in stages),
        "total_failures": sum(stage["failures"] for stage in stages),
        "provider_fallback_rate": None,
        "provider_fallback_note": "Not exercised by the bounded health-only load profile.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if payload["total_failures"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
