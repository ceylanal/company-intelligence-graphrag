"""Unit tests for Golden Evaluation Dataset builder, deduplication, export, and validator (Day 28)."""

from pathlib import Path

from company_graphrag.evals import (
    EvaluationDatasetValidator,
    GoldenDatasetBuilder,
    QuestionType,
    deduplicate_samples,
)


def test_golden_dataset_builder_generation() -> None:
    """Test building, ground verification, and deduplicating Golden Evaluation samples."""
    builder = GoldenDatasetBuilder()
    dev_samples, test_samples, report_meta = builder.build_golden_dataset()

    total_samples = len(dev_samples) + len(test_samples)
    assert total_samples >= 100

    q_types = {s.question_type for s in dev_samples + test_samples}
    assert QuestionType.SINGLE_HOP_FACT in q_types
    assert QuestionType.MULTI_HOP_GRAPH in q_types
    assert QuestionType.COMPARISON in q_types
    assert QuestionType.UNANSWERABLE in q_types

    assert report_meta["total_validated"] == total_samples


def test_deduplicate_samples_similarity() -> None:
    """Test filtering near-duplicate question strings."""
    builder = GoldenDatasetBuilder()
    samples = builder._create_single_hop_fact_samples()

    # Add duplicate question
    dup = samples[0].model_copy(deep=True)
    dup.id = "dup_001"
    samples.append(dup)

    deduped, dropped = deduplicate_samples(samples, threshold=0.85)
    assert dropped >= 1
    assert len(deduped) == len(samples) - dropped


def test_golden_dataset_export_and_validation(tmp_path: Path) -> None:
    """Test exporting dataset files and verifying checksum manifest integrity."""
    builder = GoldenDatasetBuilder()
    dev_samples, test_samples, _ = builder.build_golden_dataset()

    dev_p, test_p, manifest_p, report_p = builder.export_golden_dataset(dev_samples, test_samples, output_dir=tmp_path)

    assert dev_p.exists()
    assert test_p.exists()
    assert manifest_p.exists()
    assert report_p.exists()

    validator = EvaluationDatasetValidator(dataset_dir=tmp_path)
    val_report = validator.validate_dataset()

    assert val_report.status == "PASS"
    assert val_report.checksums_valid is True
    assert val_report.manifest_exists is True
    assert val_report.invalid_schema_count == 0
    assert val_report.duplicate_questions_count == 0
