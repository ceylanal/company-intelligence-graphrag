"""Unit tests for Final Evaluation Audit, Scorecards, and Artifact Exports (Day 33)."""

from pathlib import Path

from company_graphrag.evals import FinalBenchmarkRunner


def test_final_benchmark_runner_smoke(tmp_path: Path) -> None:
    """Test FinalBenchmarkRunner running smoke test and generating scorecards."""
    runner = FinalBenchmarkRunner()
    out_dir = tmp_path / "artifacts_final"

    summary, out_p = runner.run_final_benchmark(output_dir=out_dir, smoke=True)

    assert summary.system_status == "CONDITIONAL PASS — KNOWN LIMITATIONS"
    assert "hybrid" in summary.scorecards
    assert "vector_only" in summary.scorecards
    assert "graph_only" in summary.scorecards

    assert (out_p / "final_summary.json").exists()
    assert (out_p / "final_results.jsonl").exists()
    assert (out_p / "final_scorecard.csv").exists()
    assert Path("docs/evaluation/final_report.md").exists()
    assert Path("docs/evaluation/reproducibility.md").exists()
