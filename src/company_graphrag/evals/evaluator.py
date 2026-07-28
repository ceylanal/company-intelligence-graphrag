"""Evaluation Engine orchestrating deterministic evaluation across samples, methods, and metrics."""

import json
from datetime import UTC, datetime
from pathlib import Path

from structlog import get_logger

from company_graphrag.evals.answer_metrics import evaluate_answer
from company_graphrag.evals.citation_metrics import evaluate_citations
from company_graphrag.evals.graph_metrics import evaluate_graph_reasoning
from company_graphrag.evals.models import (
    EvaluationRunReport,
    EvaluationSample,
    MethodAggregatedMetrics,
    QuestionType,
    SampleEvalResult,
)
from company_graphrag.evals.retrieval_metrics import evaluate_retrieval

logger = get_logger(__name__)


class EvaluationEngine:
    """Orchestrates evaluation across evaluation samples and methods."""

    def __init__(self, sample_path: Path | None = None) -> None:
        self.sample_path = sample_path or Path("data/evaluation/eval_samples.jsonl")

    def load_samples(self) -> list[EvaluationSample]:
        """Load EvaluationSample records from JSONL file."""
        if not self.sample_path.exists():
            logger.warning("Evaluation samples file not found, creating sample dataset", path=str(self.sample_path))
            return self._create_sample_dataset()

        samples = []
        with open(self.sample_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    samples.append(EvaluationSample.model_validate(data))
        return samples

    def evaluate_sample_method(
        self,
        sample: EvaluationSample,
        method: str,
        retrieved_chunk_ids: list[str],
        retrieved_sources: list[str],
        retrieved_pages: list[int],
        predicted_answer: str,
        cited_sources: list[str],
        cited_pages: list[int],
        retrieved_entities: list[str],
        retrieved_relations: list[str],
        retrieved_paths: list[str],
        latency_ms: float = 0.0,
        is_abstained: bool = False,
    ) -> SampleEvalResult:
        """Evaluate a single sample for a specific method across all metric dimensions."""
        expected_sources = [sample.source_file] if isinstance(sample.source_file, str) else sample.source_file

        ret_metrics = evaluate_retrieval(
            retrieved_chunk_ids=retrieved_chunk_ids,
            expected_chunk_ids=sample.source_chunk_ids,
            retrieved_sources=retrieved_sources,
            expected_sources=expected_sources,
            retrieved_pages=retrieved_pages,
            expected_pages=sample.source_pages,
        )

        ans_metrics = evaluate_answer(
            prediction=predicted_answer,
            ground_truth=sample.expected_answer,
            acceptable_answers=sample.acceptable_answers,
            is_abstained=is_abstained,
            answerable=sample.answerable,
        )

        cit_metrics = evaluate_citations(
            cited_sources=cited_sources,
            relevant_sources=expected_sources,
            cited_pages=cited_pages,
            expected_pages=sample.source_pages,
            claim_count=max(1, len(sample.expected_answer.split("."))),
        )

        g_metrics = evaluate_graph_reasoning(
            retrieved_entities=retrieved_entities,
            expected_entities=sample.expected_entities,
            retrieved_relations=retrieved_relations,
            expected_relations=sample.expected_relations,
            retrieved_paths=retrieved_paths,
            expected_paths=sample.expected_graph_path,
        )

        overall_score = round(
            (0.30 * ret_metrics.mrr)
            + (0.30 * ans_metrics.token_f1)
            + (0.20 * cit_metrics.citation_precision)
            + (0.20 * g_metrics.graph_path_recall),
            4,
        )

        return SampleEvalResult(
            sample_id=sample.id,
            question_type=sample.question_type,
            method=method,
            retrieval=ret_metrics,
            answer=ans_metrics,
            citation=cit_metrics,
            graph=g_metrics,
            latency_ms=latency_ms,
            overall_sample_score=overall_score,
        )

    def aggregate_run_report(
        self, samples: list[EvaluationSample], sample_results: list[SampleEvalResult]
    ) -> EvaluationRunReport:
        """Aggregate sample results into MethodAggregatedMetrics and EvaluationRunReport."""
        q_dist: dict[str, int] = {}
        for s in samples:
            q_type = s.question_type.value
            q_dist[q_type] = q_dist.get(q_type, 0) + 1

        method_groups: dict[str, list[SampleEvalResult]] = {}
        for r in sample_results:
            method_groups.setdefault(r.method, []).append(r)

        method_summaries: dict[str, MethodAggregatedMetrics] = {}
        for m, results in method_groups.items():
            n = max(1, len(results))
            method_summaries[m] = MethodAggregatedMetrics(
                method=m,
                sample_count=len(results),
                mean_retrieval_mrr=round(sum(r.retrieval.mrr for r in results) / n, 4),
                mean_retrieval_recall_at_5=round(sum(r.retrieval.recall_at_5 for r in results) / n, 4),
                mean_answer_token_f1=round(sum(r.answer.token_f1 for r in results) / n, 4),
                mean_numeric_accuracy=round(sum(r.answer.numeric_accuracy for r in results) / n, 4),
                mean_abstention_accuracy=round(sum(r.answer.abstention_accuracy for r in results) / n, 4),
                mean_citation_precision=round(sum(r.citation.citation_precision for r in results) / n, 4),
                mean_graph_path_recall=round(sum(r.graph.graph_path_recall for r in results) / n, 4),
                mean_latency_ms=round(sum(r.latency_ms for r in results) / n, 2),
                overall_method_score=round(sum(r.overall_sample_score for r in results) / n, 4),
            )

        return EvaluationRunReport(
            run_timestamp=datetime.now(UTC).isoformat(),
            total_samples=len(samples),
            splits_evaluated=list({s.split.value for s in samples}),
            question_type_distribution=q_dist,
            method_summaries=method_summaries,
            sample_results=sample_results,
        )

    def _create_sample_dataset(self) -> list[EvaluationSample]:
        """Create sample dataset JSONL file with representational question types."""
        samples = [
            EvaluationSample(
                id="eval_001",
                question="ASELSAN'ın ürettiği elektro-optik ürün hangisidir?",
                question_type=QuestionType.SINGLE_HOP_FACT,
                company="Aselsan",
                expected_answer="Aselsan ASELFLIR-500 elektro-optik sistem üretmektedir.",
                acceptable_answers=["ASELFLIR-500"],
                source_file="ASELS__2024.pdf",
                source_pages=[14],
                source_chunk_ids=["chk_asels_14"],
                expected_entities=["Aselsan", "ASELFLIR-500"],
                expected_relations=["PRODUCES"],
                expected_graph_path=["(ASELSAN) ➔ PRODUCES ➔ (ASELFLIR-500)"],
                answerable=True,
            ),
            EvaluationSample(
                id="eval_002",
                question="Akbank ile aynı sektördeki şirketler hangileridir?",
                question_type=QuestionType.MULTI_HOP_GRAPH,
                company="Akbank",
                expected_answer="Akbank bankacılık sektöründe Garanti ve İş Bankası ile rekabet etmektedir.",
                acceptable_answers=["Garanti, İş Bankası"],
                source_file="AKBNK__2024.pdf",
                source_pages=[10],
                source_chunk_ids=["chk_akbnk_10"],
                expected_entities=["Akbank", "Bankacılık"],
                expected_relations=["OPERATES_IN"],
                expected_graph_path=["(Akbank) ➔ OPERATES_IN ➔ (Bankacılık)"],
                answerable=True,
            ),
            EvaluationSample(
                id="eval_003",
                question="Aselsan mars uzay mekiği projesi bütçesi nedir?",
                question_type=QuestionType.UNANSWERABLE,
                company="Aselsan",
                expected_answer="Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli kanıt bulunamadı.",
                acceptable_answers=["Yetersiz kanıt"],
                source_file="ASELS__2024.pdf",
                source_pages=[1],
                source_chunk_ids=["chk_asels_1"],
                expected_entities=[],
                expected_relations=[],
                expected_graph_path=[],
                answerable=False,
            ),
        ]

        self.sample_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.sample_path, "w", encoding="utf-8") as f:
            for s in samples:
                f.write(s.model_dump_json() + "\n")
        logger.info("Created evaluation samples dataset", count=len(samples), path=str(self.sample_path))
        return samples

    def export_reports(self, report: EvaluationRunReport, output_dir: Path) -> tuple[Path, Path]:
        """Export JSON report and Markdown audit report."""
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "evaluation_run_report.json"
        md_path = output_dir / "evaluation_run_report.md"

        json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        md_lines = [
            "# 📊 GraphRAG Evaluation Framework Run Report",
            "",
            f"**Run Timestamp:** `{report.run_timestamp}`  ",
            f"**Total Evaluation Samples:** `{report.total_samples}`  ",
            f"**Splits Evaluated:** `{', '.join(report.splits_evaluated)}`  ",
            "",
            "## 📌 1. Method Benchmark Performance Comparison",
            "",
            "| Method | Samples | Overall Score | MRR | Recall@5 | Answer Token F1 | Numeric Acc | Abstention Acc | Citation Prec | Graph Path Recall | Latency |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        for m_name, m in report.method_summaries.items():
            md_lines.append(
                f"| `{m_name}` | {m.sample_count} | **{m.overall_method_score:.4f}** | {m.mean_retrieval_mrr:.4f} | {m.mean_retrieval_recall_at_5:.4f} | {m.mean_answer_token_f1:.4f} | {m.mean_numeric_accuracy:.4f} | {m.mean_abstention_accuracy:.4f} | {m.mean_citation_precision:.4f} | {m.mean_graph_path_recall:.4f} | {m.mean_latency_ms:.2f} ms |"
            )

        md_lines.extend(
            [
                "",
                "## 📋 2. Question Taxonomy Distribution",
                "",
                "| Question Type | Sample Count | Percentage |",
                "| :--- | :---: | :---: |",
            ]
        )

        for q_type, cnt in report.question_type_distribution.items():
            pct = (cnt / max(1, report.total_samples)) * 100.0
            md_lines.append(f"| `{q_type}` | {cnt} | {pct:.1f}% |")

        md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        logger.info("Exported evaluation framework reports", json=str(json_path), md=str(md_path))
        return json_path, md_path
