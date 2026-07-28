"""Unit tests for Judge Calibration, Agreement metrics, and Regression verification (Day 32)."""

import json
from pathlib import Path

from company_graphrag.evals import (
    CalibrationEngine,
    ErrorCategory,
    HumanAnnotationLabel,
    HumanAnnotationStore,
    RegressionCheckEngine,
    check_human_labels_exist,
)
from company_graphrag.evals.calibration import (
    compute_pearson_correlation,
    compute_spearman_correlation,
    compute_weighted_kappa,
)


def test_check_human_labels_exist_missing(tmp_path: Path) -> None:
    """Test check_human_labels_exist returns False when labels file is missing."""
    valid, msg, labels = check_human_labels_exist(data_dir=tmp_path)
    assert not valid
    assert "missing or empty" in msg
    assert len(labels) == 0


def test_correlation_and_kappa_metrics() -> None:
    """Test correlation and kappa metric calculation helper functions."""
    h_scores = [5, 4, 3, 2, 1]
    j_scores = [5, 4, 3, 2, 1]

    rho = compute_spearman_correlation([float(x) for x in h_scores], [float(y) for y in j_scores])
    r_val = compute_pearson_correlation([float(x) for x in h_scores], [float(y) for y in j_scores])
    kappa = compute_weighted_kappa(h_scores, j_scores)

    assert rho == 1.0
    assert r_val == 1.0
    assert kappa == 1.0


def test_calibration_engine_with_labels(tmp_path: Path) -> None:
    """Test CalibrationEngine execution with mock human labels."""
    store = HumanAnnotationStore(data_dir=tmp_path)

    for i in range(1, 6):
        label = HumanAnnotationLabel(
            annotation_id=f"ann_{i:03d}",
            sample_id=f"sh_{i:03d}",
            blind_candidate_label="Candidate A",
            actual_retrieval_mode="hybrid",
            correctness=5,
            completeness=5,
            faithfulness=5,
            relevance=5,
            citation_support=5,
            overall_pass=True,
            error_category=ErrorCategory.NONE,
        )
        store.save_label(label)

    engine = CalibrationEngine(data_dir=tmp_path)
    out_dir = tmp_path / "artifacts_calibration"
    summary, out_p = engine.run_calibration(output_dir=out_dir)

    assert summary.total_samples == 5
    assert summary.acceptance_criteria.pass_fail_agreement_passed
    assert (out_p / "calibration_summary.json").exists()
    assert (out_p / "calibration_report.md").exists()
    assert (out_p / "error_analysis.md").exists()
    assert (out_p / "failure_catalog.jsonl").exists()


def test_regression_check_engine(tmp_path: Path) -> None:
    """Test RegressionCheckEngine running against baseline config."""
    baseline_file = Path("config/eval_baseline.yaml")
    answer_summary = tmp_path / "answer_summary.json"
    retrieval_summary = tmp_path / "retrieval_summary.json"
    answer_summary.write_text(
        json.dumps(
            {
                "test_summaries": {
                    "hybrid": {
                        "mean_exact_match": 0.0,
                        "mean_token_f1": 0.0660,
                        "mean_numeric_accuracy": 0.5392,
                        "mean_abstention_f1": 0.3333,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    retrieval_summary.write_text(
        json.dumps(
            {
                "summaries": {
                    "hybrid": {
                        "recall_at_5": 0.9500,
                        "precision_at_5": 0.7800,
                        "mrr": 0.9100,
                        "ndcg_at_5": 0.9200,
                        "source_recall": 1.0000,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    engine = RegressionCheckEngine(baseline_config_path=baseline_file)
    report = engine.run_regression_check(
        answer_summary_path=answer_summary,
        retrieval_summary_path=retrieval_summary,
        allowed_drop_override=0.05,
    )

    assert report.total_checks > 0
    assert report.all_passed
