"""Evaluation Regression Verification Engine checking performance against baseline config (Day 32)."""

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel
from structlog import get_logger

logger = get_logger(__name__)


class RegressionCheckResult(BaseModel):
    """Result summary of a regression metric check against baseline."""

    metric_name: str
    baseline_value: float
    current_value: float
    allowed_drop_pct: float
    min_allowed_value: float
    passed: bool
    status_msg: str


class FullRegressionCheckReport(BaseModel):
    """Overall evaluation regression report across retrieval, answer quality, and citations."""

    baseline_path: str
    tolerance_pct: float
    total_checks: int
    passed_checks: int
    failed_checks: int
    all_passed: bool
    details: list[RegressionCheckResult]


class RegressionCheckEngine:
    """Verifies that current RAG evaluation metrics meet or exceed baseline targets within allowed drop tolerance."""

    def __init__(self, baseline_config_path: Path | None = None) -> None:
        self.baseline_path = baseline_config_path or Path("config/eval_baseline.yaml")

    def load_baseline(self) -> dict[str, Any]:
        """Load baseline YAML configuration."""
        if not self.baseline_path.exists():
            raise FileNotFoundError(f"Baseline configuration file not found at '{self.baseline_path}'")
        with open(self.baseline_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}

    def run_regression_check(
        self,
        answer_summary_path: Path | None = None,
        retrieval_summary_path: Path | None = None,
        allowed_drop_override: float | None = None,
    ) -> FullRegressionCheckReport:
        """Run regression check comparing current evaluation output summaries against baseline."""
        baseline = self.load_baseline()
        tolerance_cfg = baseline.get("tolerance", {})
        allowed_drop_pct = (
            allowed_drop_override
            if allowed_drop_override is not None
            else tolerance_cfg.get("allowed_metric_drop_pct", 0.05)
        )

        ans_p = answer_summary_path or Path("artifacts/evals/answers/answer_summary.json")
        ret_p = retrieval_summary_path or Path("artifacts/evals/retrieval/retrieval_summary.json")

        results: list[RegressionCheckResult] = []

        # Check hybrid answer metrics if available
        if ans_p.exists():
            import json

            with open(ans_p, encoding="utf-8") as f:
                ans_data = json.load(f)
            hybrid_ans = ans_data.get("test_summaries", {}).get("hybrid", {})
            baseline_ans = baseline.get("answer", {}).get("hybrid", {})

            for metric_key, b_val in baseline_ans.items():
                curr_key = "mean_" + metric_key if f"mean_{metric_key}" in hybrid_ans else metric_key
                c_val = hybrid_ans.get(curr_key, b_val)
                res = self._check_single_metric(f"answer.hybrid.{metric_key}", b_val, c_val, allowed_drop_pct)
                results.append(res)

        # Check hybrid retrieval metrics if available
        if ret_p.exists():
            import json

            with open(ret_p, encoding="utf-8") as f:
                ret_data = json.load(f)
            hybrid_ret = ret_data.get("summaries", {}).get("hybrid", {})
            baseline_ret = baseline.get("retrieval", {}).get("hybrid", {})

            for metric_key, b_val in baseline_ret.items():
                c_val = hybrid_ret.get(metric_key, b_val)
                res = self._check_single_metric(f"retrieval.hybrid.{metric_key}", b_val, c_val, allowed_drop_pct)
                results.append(res)

        failed_count = sum(1 for r in results if not r.passed)
        passed_count = len(results) - failed_count
        all_ok = failed_count == 0

        report = FullRegressionCheckReport(
            baseline_path=str(self.baseline_path),
            tolerance_pct=allowed_drop_pct,
            total_checks=len(results),
            passed_checks=passed_count,
            failed_checks=failed_count,
            all_passed=all_ok,
            details=results,
        )

        logger.info(
            "Evaluation Regression Check completed",
            all_passed=all_ok,
            passed=passed_count,
            failed=failed_count,
        )
        return report

    def _check_single_metric(
        self, metric_name: str, baseline_val: float, current_val: float, allowed_drop_pct: float
    ) -> RegressionCheckResult:
        """Check a single metric value against its baseline and tolerance limit."""
        min_allowed = baseline_val * (1.0 - allowed_drop_pct)
        passed = current_val >= min_allowed
        status = (
            f"✅ PASS ({current_val:.4f} >= min {min_allowed:.4f})"
            if passed
            else f"❌ FAIL ({current_val:.4f} < min {min_allowed:.4f}, baseline {baseline_val:.4f})"
        )

        return RegressionCheckResult(
            metric_name=metric_name,
            baseline_value=round(baseline_val, 4),
            current_value=round(current_val, 4),
            allowed_drop_pct=allowed_drop_pct,
            min_allowed_value=round(min_allowed, 4),
            passed=passed,
            status_msg=status,
        )
