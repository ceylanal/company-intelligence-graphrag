#!/usr/bin/env python3
"""Run a bounded, deterministic baseline against the private staging API."""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from company_graphrag.evals.answer_metrics import calculate_token_f1

ABSTENTION_MARKERS = (
    "yetersiz kanıt",
    "yeterli kanıt bulunamadı",
    "doğrulanmış herhangi bir kaynak",
    "insufficient evidence",
    "insufficient context",
)
CITATION_PATTERN = re.compile(r"\[(?:source|kaynak)\s+\d+\]", re.IGNORECASE)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 2)


def evaluate_sample(sample: dict[str, Any], answer: str, latency_ms: float) -> dict[str, Any]:
    """Compute transparent deterministic proxies from the public API response."""
    normalized_answer = _normalized(answer)
    acceptable = [str(item) for item in sample.get("acceptable_answers", []) if str(item).strip()]
    acceptable_match = any(_normalized(item) in normalized_answer for item in acceptable)
    abstained = any(marker in normalized_answer for marker in ABSTENTION_MARKERS)
    answerable = bool(sample.get("answerable", True))
    correct = acceptable_match if answerable else abstained
    citation_count = len(CITATION_PATTERN.findall(answer))
    expected_source = str(sample.get("source_file") or "")
    source_mentioned = bool(expected_source and expected_source.casefold() in answer.casefold())
    hallucinated = bool(answerable and not acceptable_match and not abstained)

    return {
        "sample_id": sample["id"],
        "question_type": sample.get("question_type"),
        "answerable": answerable,
        "http_status": 200,
        "latency_ms": round(latency_ms, 2),
        "correct": correct,
        "acceptable_match": acceptable_match,
        "token_f1": round(calculate_token_f1(answer, str(sample.get("expected_answer") or "")), 4),
        "abstained": abstained,
        "citation_count": citation_count,
        "citation_source_match": source_mentioned,
        "faithfulness_proxy": bool(abstained or citation_count > 0),
        "retrieval_recall_proxy": bool(acceptable_match or source_mentioned),
        "hallucinated": hallucinated,
        "answer": answer,
    }


def build_summary(results: list[dict[str, Any]], image_digest: str) -> dict[str, Any]:
    """Aggregate deterministic staging metrics without presenting proxies as judge scores."""
    completed = [item for item in results if item.get("http_status") == 200]
    count = len(completed)
    denominator = max(1, count)
    multihop = [item for item in completed if item.get("question_type") == "multi_hop_graph"]
    cited = [item for item in completed if item.get("citation_count", 0) > 0]
    latencies = [float(item["latency_ms"]) for item in completed]
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "image_digest": image_digest,
        "sample_count": len(results),
        "completed_count": count,
        "request_success_rate": round(count / max(1, len(results)), 4),
        "correctness_rate": round(sum(bool(item["correct"]) for item in completed) / denominator, 4),
        "mean_token_f1": round(statistics.fmean(float(item["token_f1"]) for item in completed), 4)
        if completed
        else 0.0,
        "faithfulness_proxy_rate": round(
            sum(bool(item["faithfulness_proxy"]) for item in completed) / denominator, 4
        ),
        "citation_correctness_proxy_rate": round(
            sum(bool(item["citation_source_match"]) for item in cited) / max(1, len(cited)), 4
        ),
        "retrieval_recall_proxy": round(
            sum(bool(item["retrieval_recall_proxy"]) for item in completed) / denominator, 4
        ),
        "multi_hop_success_rate": round(
            sum(bool(item["correct"]) for item in multihop) / max(1, len(multihop)), 4
        ),
        "hallucination_rate": round(
            sum(bool(item["hallucinated"]) for item in completed) / denominator, 4
        ),
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "methodology": {
            "correctness": "acceptable-answer substring match; correct abstention for unanswerable samples",
            "faithfulness": "proxy: explicit citation marker or safe abstention; no LLM judge",
            "citation_correctness": "proxy: cited expected source filename in public answer",
            "retrieval_recall": "proxy: acceptable answer or expected source visible in public answer",
            "hallucination": "answerable sample with neither acceptable answer nor safe abstention",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--dataset", type=Path, default=Path("data/evals/golden_test.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/production_activation/evals"))
    parser.add_argument("--max-samples", type=int, default=34)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    args = parser.parse_args()

    api_key = os.environ.get("API_KEY", "")
    identity_token = os.environ.get("GOOGLE_IDENTITY_TOKEN", "")
    if not api_key or not identity_token:
        raise SystemExit("API_KEY and GOOGLE_IDENTITY_TOKEN are required")

    samples = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][: args.max_samples]
    headers = {"x-api-key": api_key, "Authorization": f"Bearer {identity_token}"}
    results: list[dict[str, Any]] = []
    with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers, timeout=args.timeout_seconds) as client:
        for sample in samples:
            started = time.perf_counter()
            try:
                response = client.post(
                    "/research",
                    headers={"idempotency-key": f"staging-baseline-v1-{sample['id']}"},
                    json={"query": sample["question"]},
                )
                latency_ms = (time.perf_counter() - started) * 1000
                if response.status_code != 200:
                    results.append(
                        {
                            "sample_id": sample["id"],
                            "question_type": sample.get("question_type"),
                            "http_status": response.status_code,
                            "latency_ms": round(latency_ms, 2),
                            "error_type": "http_error",
                        }
                    )
                    continue
                payload = response.json()
                item = evaluate_sample(sample, str(payload.get("answer") or ""), latency_ms)
                item["request_id"] = payload.get("request_id")
                item["run_id"] = payload.get("run_id")
                results.append(item)
            except (httpx.HTTPError, ValueError) as exc:
                results.append(
                    {
                        "sample_id": sample["id"],
                        "question_type": sample.get("question_type"),
                        "http_status": None,
                        "error_type": type(exc).__name__,
                    }
                )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results_path = args.output_dir / "staging-results.jsonl"
    results_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in results),
        encoding="utf-8",
    )
    summary = build_summary(results, args.image_digest)
    (args.output_dir / "staging-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output_dir / "staging-summary.json")
    return 0 if summary["request_success_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
