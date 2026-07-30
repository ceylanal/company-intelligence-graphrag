"""Run the deterministic Day 54 safety red-team evaluation and enforce release gates."""

from __future__ import annotations

import argparse
from pathlib import Path

from company_graphrag.evals.safety_eval import DEFAULT_GATES_PATH, SafetyEvaluator, write_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gates", type=Path, default=DEFAULT_GATES_PATH)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/safety/day54"))
    args = parser.parse_args()

    evaluation = SafetyEvaluator(args.gates).evaluate()
    write_artifacts(evaluation, args.output_dir)
    print(f"Safety release gate: {'PASS' if evaluation.passed else 'FAIL'}")
    for gate in evaluation.gates:
        if not gate.passed:
            print(f"GATE FAILED {gate.name}: cases={','.join(gate.failing_case_ids)}")
    if not evaluation.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
