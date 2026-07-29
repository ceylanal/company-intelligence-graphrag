#!/usr/bin/env python3
"""Run bounded staging smoke checks and emit a machine-readable report."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


def _record(
    results: list[dict[str, Any]],
    *,
    name: str,
    method: str,
    url: str,
    expected: set[int],
    client: httpx.Client,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> None:
    started = time.monotonic()
    try:
        response = client.request(method, url, headers=headers, json=json_body)
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        body: Any
        try:
            body = response.json()
        except ValueError:
            body = {"text_length": len(response.text)}
        results.append(
            {
                "name": name,
                "status": "PASS" if response.status_code in expected else "FAIL",
                "http_status": response.status_code,
                "expected_statuses": sorted(expected),
                "duration_ms": duration_ms,
                "response": body,
                "correlation": {
                    "request_id": response.headers.get("x-request-id"),
                    "run_id": response.headers.get("x-run-id"),
                    "trace_id": response.headers.get("x-trace-id"),
                },
            }
        )
    except Exception as exc:
        results.append(
            {
                "name": name,
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/production_activation/staging/smoke.json"))
    parser.add_argument("--research-query", default="")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    bearer_token = os.environ.get("BEARER_TOKEN", "") or os.environ.get("GOOGLE_IDENTITY_TOKEN", "")
    api_key = os.environ.get("API_KEY", "")
    auth_headers: dict[str, str] = {}
    if bearer_token:
        auth_headers["Authorization"] = f"Bearer {bearer_token}"
    if api_key:
        auth_headers["x-api-key"] = api_key
    results: list[dict[str, Any]] = []

    with httpx.Client(timeout=args.timeout, follow_redirects=False) as client:
        _record(results, name="liveness", method="GET", url=f"{base_url}/health/live", expected={200}, client=client, headers=auth_headers)
        _record(results, name="readiness", method="GET", url=f"{base_url}/health/ready", expected={200}, client=client, headers=auth_headers)
        _record(results, name="version", method="GET", url=f"{base_url}/version", expected={200}, client=client, headers=auth_headers)
        _record(
            results,
            name="invalid_request",
            method="POST",
            url=f"{base_url}/research",
            expected={422},
            client=client,
            headers=auth_headers,
            json_body={"query": "x"},
        )
        if api_key:
            platform_headers = {
                key: value for key, value in auth_headers.items() if key.lower() != "x-api-key"
            }
            _record(
                results,
                name="authentication_rejects_missing_key",
                method="POST",
                url=f"{base_url}/research",
                expected={401},
                client=client,
                headers=platform_headers,
                json_body={"query": "bounded staging authentication check"},
            )
        if args.research_query:
            _record(
                results,
                name="bounded_research",
                method="POST",
                url=f"{base_url}/research",
                expected={200},
                client=client,
                headers={**auth_headers, "idempotency-key": "staging-smoke-v1"},
                json_body={"query": args.research_query},
            )

    report = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": base_url,
        "summary": {
            "total": len(results),
            "passed": sum(item["status"] == "PASS" for item in results),
            "failed": sum(item["status"] == "FAIL" for item in results),
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    raise SystemExit(1 if report["summary"]["failed"] else 0)


if __name__ == "__main__":
    main()
