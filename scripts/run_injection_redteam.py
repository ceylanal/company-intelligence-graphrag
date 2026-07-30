"""Execute the deterministic prompt-injection and retrieval-poisoning red-team corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from company_graphrag.safety.prompt_injection import PromptInjectionDetector

DEFAULT_CASES = (
    Path("data/safety/prompt_injection_cases.jsonl"),
    Path("data/safety/retrieval_poisoning_cases.jsonl"),
)
DEFAULT_OUTPUT = Path("artifacts/safety/day52/redteam-results.json")


def load_cases(paths: tuple[Path, ...] = DEFAULT_CASES) -> list[dict[str, Any]]:
    """Load JSONL test cases without writing raw payloads to the result artifact."""
    cases: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cases.append(json.loads(line))
    return cases


def run_redteam(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure simulated weak-baseline and detector containment outcomes."""
    detector = PromptInjectionDetector()
    results: list[dict[str, str]] = []
    attack_count = 0
    baseline_successes = 0
    after_successes = 0
    benign_count = 0
    false_positives = 0

    for case in cases:
        expected = str(case["expected_action"])
        observed = detector.detect(str(case["text"]), source=str(case["surface"])).action.value
        is_attack = expected != "allow"
        if is_attack:
            attack_count += 1
            baseline_successes += 1  # Baseline model accepted all untrusted content.
            if observed != expected:
                after_successes += 1
        else:
            benign_count += 1
            if observed != "allow":
                false_positives += 1
        results.append({"id": str(case["id"]), "expected_action": expected, "observed_action": observed})

    return {
        "schema_version": "1.0",
        "total_cases": len(cases),
        "attack_cases": attack_count,
        "benign_cases": benign_count,
        "before": {
            "model": "simulated_unprotected_context_acceptance",
            "attack_successes": baseline_successes,
            "attack_success_rate": round(baseline_successes / attack_count, 4) if attack_count else 0.0,
        },
        "after": {
            "model": "prompt_injection_detector_and_context_isolation",
            "attack_successes": after_successes,
            "attack_success_rate": round(after_successes / attack_count, 4) if attack_count else 0.0,
            "containment_rate": round(1 - (after_successes / attack_count), 4) if attack_count else 1.0,
        },
        "false_positive_rate": round(false_positives / benign_count, 4) if benign_count else 0.0,
        "case_results": results,
    }


def main() -> None:
    """Run the corpus and emit a compact machine-readable result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run_redteam(load_cases())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("total_cases", "before", "after", "false_positive_rate")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
