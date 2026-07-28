"""Unit tests for Human Evaluation & Annotation builder, blinding, persistence, and CLI commands (Day 31)."""

from pathlib import Path

from company_graphrag.evals import (
    ErrorCategory,
    HumanAnnotationBuilder,
    HumanAnnotationLabel,
    HumanAnnotationStore,
)


def test_human_annotation_builder(tmp_path: Path) -> None:
    """Test building blinded human annotation items and pilot package."""
    builder = HumanAnnotationBuilder(output_dir=tmp_path)
    ans_path = Path("artifacts/evals/answers/answer_results.jsonl")
    dev_path = Path("data/evals/golden_dev.jsonl")

    items = builder.build_blind_package(
        answer_results_path=ans_path,
        dev_samples_path=dev_path,
        sample_count=10,
        seed=42,
    )

    assert len(items) == 10
    assert items[0].blind_candidate_label in ["Candidate A", "Candidate B", "Candidate C"]

    items_file = tmp_path / "annotation_items.jsonl"
    pilot_file = tmp_path / "pilot_annotation_items.jsonl"
    assert items_file.exists()
    assert pilot_file.exists()


def test_human_annotation_store_persistence(tmp_path: Path) -> None:
    """Test saving, updating, and exporting human annotation labels to JSONL and CSV."""
    store = HumanAnnotationStore(data_dir=tmp_path)

    label1 = HumanAnnotationLabel(
        annotation_id="ann_001",
        sample_id="sh_001",
        blind_candidate_label="Candidate A",
        actual_retrieval_mode="hybrid",
        correctness=5,
        completeness=5,
        faithfulness=5,
        relevance=5,
        citation_support=5,
        overall_pass=True,
        error_category=ErrorCategory.NONE,
        notes="Flawless answer",
    )

    store.save_label(label1)
    loaded = store.load_labels()
    assert len(loaded) == 1
    assert loaded[0].annotation_id == "ann_001"
    assert loaded[0].correctness == 5

    # Update existing label
    label1_updated = label1.model_copy(update={"correctness": 4})
    store.save_label(label1_updated)
    reloaded = store.load_labels()
    assert len(reloaded) == 1
    assert reloaded[0].correctness == 4

    csv_path = tmp_path / "human_labels.csv"
    assert csv_path.exists()
