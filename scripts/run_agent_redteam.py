"""Run deterministic agent/tool-abuse scenarios without contacting any backend."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from company_graphrag.agents.schema import ExecutionBudget, ResearchState, ToolCallRecord
from company_graphrag.safety.agent_limits import AgentLimitError, AgentLimits
from company_graphrag.safety.tool_policy import ToolExecutionContext, ToolPolicy, ToolPolicyError

CASES_PATH = Path("data/safety/tool_abuse_cases.jsonl")
OUTPUT_PATH = Path("artifacts/safety/day53/agent-redteam-results.json")


def run_case(case: dict[str, Any]) -> str:
    """Return allow/block for a corpus case, without executing external tools."""
    operation = case["operation"]
    if operation == "output":
        return "allow" if ToolPolicy().validate_tool_output(case["payload"]["text"]) else "block"
    if operation == "limits":
        payload = case["payload"]
        state = ResearchState(
            user_query="safety test",
            execution_budget=ExecutionBudget(max_tokens=payload.get("max_tokens", 32000), tokens_used=payload.get("tokens_used", 0)),
        )
        state.tool_calls.extend(
            ToolCallRecord(agent_role="Vector Researcher", tool_name="vector_search", input_params={"query": "ASELS"})
            for _ in range(payload.get("repeat_count", 0))
        )
        try:
            AgentLimits(max_repeated_operation=2).check(state)
        except AgentLimitError:
            return "block"
        return "allow"

    context = ToolExecutionContext(
        agent_role=case["agent_role"],
        allowed_tickers=frozenset(case.get("allowed_tickers", [])),
    )
    try:
        ToolPolicy().validate_call(case["tool_name"], case["payload"], context=context)
    except ToolPolicyError:
        return "block"
    return "allow"


def main() -> None:
    """Execute red-team cases and write compact, non-sensitive evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    cases = [json.loads(line) for line in CASES_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    case_results = [{"id": case["id"], "expected_action": case["expected_action"], "observed_action": run_case(case)} for case in cases]
    attacks = [item for item in case_results if item["expected_action"] == "block"]
    benign = [item for item in case_results if item["expected_action"] == "allow"]
    result = {
        "schema_version": "1.0",
        "total_cases": len(case_results),
        "attack_cases": len(attacks),
        "blocked_attacks": sum(item["observed_action"] == "block" for item in attacks),
        "attack_bypass_rate": round(sum(item["observed_action"] != "block" for item in attacks) / len(attacks), 4),
        "false_positive_rate": round(sum(item["observed_action"] != "allow" for item in benign) / len(benign), 4),
        "case_results": case_results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("total_cases", "blocked_attacks", "attack_bypass_rate", "false_positive_rate")}))


if __name__ == "__main__":
    main()
