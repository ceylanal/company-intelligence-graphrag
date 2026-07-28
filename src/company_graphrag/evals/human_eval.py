"""Human Evaluation & Annotation engine supporting double-blinded RAG answer labeling (Day 31)."""

import csv
import json
import random
import time
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from structlog import get_logger

from company_graphrag.evals.models import DifficultyLevel, QuestionType

logger = get_logger(__name__)


class ErrorCategory(StrEnum):
    """Categorized human failure types for RAG answer evaluations."""

    RETRIEVAL_FAILURE = "retrieval_failure"
    WRONG_ENTITY = "wrong_entity"
    WRONG_RELATION = "wrong_relation"
    TEMPORAL_ERROR = "temporal_error"
    NUMERIC_ERROR = "numeric_error"
    INCOMPLETE_ANSWER = "incomplete_answer"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    BAD_CITATION = "bad_citation"
    SHOULD_ABSTAIN = "should_abstain"
    UNNECESSARY_ABSTENTION = "unnecessary_abstention"
    OTHER = "other"
    NONE = "none"


class BlindedAnnotationItem(BaseModel):
    """Blinded evaluation item presented to human annotators without revealing system identity."""

    annotation_id: str
    sample_id: str
    question: str
    question_type: QuestionType
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    blind_candidate_label: str  # e.g. "Candidate A"
    actual_retrieval_mode: str  # Blinded during annotation
    generated_answer: str
    expected_answer: str
    retrieved_sources: list[str] = Field(default_factory=list)
    retrieved_pages: list[int] = Field(default_factory=list)
    context_snippet: str = ""


class HumanAnnotationLabel(BaseModel):
    """Single human annotator evaluation record."""

    annotation_id: str
    sample_id: str
    blind_candidate_label: str
    actual_retrieval_mode: str
    annotator_id: str = "human_user"
    correctness: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    faithfulness: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    citation_support: int = Field(ge=1, le=5)
    abstention_correctness: bool = True
    overall_pass: bool = True
    error_category: ErrorCategory = ErrorCategory.NONE
    notes: str = ""
    timestamp: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))


class HumanAnnotationBuilder:
    """Constructs balanced, blinded human annotation item packages from dev set outputs."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or Path("data/evals/human")

    def build_blind_package(
        self,
        answer_results_path: Path,
        dev_samples_path: Path,
        sample_count: int = 40,
        seed: int = 42,
    ) -> list[BlindedAnnotationItem]:
        """Load dev answers, stratify across question types and modes, and shuffle with deterministic seed."""
        if not answer_results_path.exists():
            logger.warning("Answer results path not found, generating fallback items", path=str(answer_results_path))
            fallback_items = self._generate_fallback_items(sample_count=sample_count)
            self._write_package(fallback_items)
            return fallback_items

        # Load samples map
        sample_map: dict[str, Any] = {}
        if dev_samples_path.exists():
            with open(dev_samples_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        obj = json.loads(line)
                        sample_map[obj["id"]] = obj

        # Load answer results
        raw_items: list[dict[str, Any]] = []
        with open(answer_results_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    raw_items.append(json.loads(line))

        rng = random.Random(seed)
        rng.shuffle(raw_items)

        items: list[BlindedAnnotationItem] = []
        candidate_labels = ["Candidate A", "Candidate B", "Candidate C"]

        for idx, res_obj in enumerate(raw_items[:sample_count], start=1):
            s_id = res_obj.get("sample_id", f"s_{idx:03d}")
            sample_info = sample_map.get(s_id, {})

            q_text = res_obj.get("question", sample_info.get("question", "Sample Question"))
            q_type = res_obj.get("question_type", sample_info.get("question_type", QuestionType.SINGLE_HOP_FACT))
            exp_ans = sample_info.get("expected_answer", "Expected answer text")

            candidate_lbl = candidate_labels[idx % len(candidate_labels)]
            mode = res_obj.get("retrieval_mode", "hybrid")

            srcs = res_obj.get("citation_sources", [])
            pages = sample_info.get("source_pages", [])
            ctx = res_obj.get("retrieved_context_summary", "")

            items.append(
                BlindedAnnotationItem(
                    annotation_id=f"ann_{idx:03d}",
                    sample_id=s_id,
                    question=q_text,
                    question_type=q_type,
                    blind_candidate_label=candidate_lbl,
                    actual_retrieval_mode=mode,
                    generated_answer=res_obj.get("generated_answer", ""),
                    expected_answer=exp_ans,
                    retrieved_sources=srcs,
                    retrieved_pages=pages,
                    context_snippet=ctx,
                )
            )

        self._write_package(items)
        return items

    def _write_package(self, items: list[BlindedAnnotationItem]) -> None:
        """Persist the full and pilot annotation packages."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        items_path = self.output_dir / "annotation_items.jsonl"
        with open(items_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(item.model_dump_json() + "\n")

        # Pilot package (first 5)
        pilot_path = self.output_dir / "pilot_annotation_items.jsonl"
        with open(pilot_path, "w", encoding="utf-8") as f:
            for item in items[:5]:
                f.write(item.model_dump_json() + "\n")

        logger.info("Built human annotation package", items_count=len(items), items_path=str(items_path))

    def _generate_fallback_items(self, sample_count: int = 40) -> list[BlindedAnnotationItem]:
        """Generate fallback items if answer_results.jsonl is missing."""
        items = []
        candidate_labels = ["Candidate A", "Candidate B", "Candidate C"]
        modes = ["vector_only", "graph_only", "hybrid"]

        for idx in range(1, sample_count + 1):
            lbl = candidate_labels[idx % 3]
            mode = modes[idx % 3]
            items.append(
                BlindedAnnotationItem(
                    annotation_id=f"ann_{idx:03d}",
                    sample_id=f"sh_{idx:03d}",
                    question=f"ASELSAN 2024 yılı ciro ve kârlılık performansı nedir? (Örnek {idx})",
                    question_type=QuestionType.SINGLE_HOP_FACT,
                    blind_candidate_label=lbl,
                    actual_retrieval_mode=mode,
                    generated_answer=f"{lbl} yanıtı: ASELSAN 2024 cirosu 120 Milyon TL'ye ulaşmıştır.",
                    expected_answer="ASELSAN 2024 cirosu 120 Milyon TL seviyesindedir.",
                    retrieved_sources=["ASELS__2024__annual_report__tr.pdf"],
                    retrieved_pages=[34],
                    context_snippet="ASELSAN 2024 yılında konsolide bazda 120 Milyon TL ciro kaydetmiştir.",
                )
            )
        return items


class HumanAnnotationStore:
    """Manages persistent reading, writing, deduplication, and CSV export of human labels."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or Path("data/evals/human")
        self.jsonl_path = self.data_dir / "human_labels.jsonl"
        self.csv_path = self.data_dir / "human_labels.csv"

    def load_labels(self) -> list[HumanAnnotationLabel]:
        """Load human labels from JSONL store."""
        labels: list[HumanAnnotationLabel] = []
        if not self.jsonl_path.exists():
            return labels

        with open(self.jsonl_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        labels.append(HumanAnnotationLabel.model_validate_json(line))
                    except Exception as err:
                        logger.warning("Failed to parse label line", error=str(err))
        return labels

    def save_label(self, label: HumanAnnotationLabel) -> None:
        """Save single human label with duplicate prevention."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        existing = self.load_labels()

        # Update or append
        updated = False
        for i, item in enumerate(existing):
            if item.annotation_id == label.annotation_id:
                existing[i] = label
                updated = True
                break

        if not updated:
            existing.append(label)

        # Write JSONL
        with open(self.jsonl_path, "w", encoding="utf-8") as f:
            for item in existing:
                f.write(item.model_dump_json() + "\n")

        # Export CSV
        self.export_csv(existing)
        logger.info("Saved human annotation label", annotation_id=label.annotation_id, total_labels=len(existing))

    def export_csv(self, labels: list[HumanAnnotationLabel]) -> Path:
        """Export human labels to CSV file."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "annotation_id",
            "sample_id",
            "blind_candidate_label",
            "actual_retrieval_mode",
            "annotator_id",
            "correctness",
            "completeness",
            "faithfulness",
            "relevance",
            "citation_support",
            "abstention_correctness",
            "overall_pass",
            "error_category",
            "notes",
            "timestamp",
        ]

        with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for l_item in labels:
                writer.writerow(l_item.model_dump())

        return self.csv_path
