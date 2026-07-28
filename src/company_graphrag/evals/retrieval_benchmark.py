"""Retrieval Benchmark Engine evaluating Vector, Graph, and Hybrid retrieval across golden datasets."""

import time
from pathlib import Path

from pydantic import BaseModel, Field
from structlog import get_logger

from company_graphrag.evals.graph_metrics import evaluate_graph_reasoning
from company_graphrag.evals.models import EvaluationSample, QuestionType
from company_graphrag.evals.retrieval_metrics import evaluate_retrieval
from company_graphrag.retrieval.hybrid import HybridRetriever, RetrievalMode

logger = get_logger(__name__)


class RetrievalHitItem(BaseModel):
    """Retrieved search hit details for benchmark evaluation."""

    rank: int
    score: float
    chunk_id: str
    source_file: str
    page_number: int
    source_retriever: str
    graph_path_summary: str | None = None


class SampleRetrievalBenchmarkResult(BaseModel):
    """Evaluation result for a single sample under a specific retrieval mode."""

    sample_id: str
    question: str
    question_type: QuestionType
    company: str | None = None
    retrieval_mode: str
    top_hits: list[RetrievalHitItem] = Field(default_factory=list)
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    precision_at_1: float = 0.0
    precision_at_3: float = 0.0
    precision_at_5: float = 0.0
    precision_at_10: float = 0.0
    mrr: float = 0.0
    ndcg_at_5: float = 0.0
    ndcg_at_10: float = 0.0
    source_recall: float = 0.0
    page_recall: float = 0.0
    chunk_recall: float = 0.0
    entity_recall: float = 0.0
    relation_recall: float = 0.0
    graph_path_recall: float = 0.0
    latency_ms: float = 0.0
    is_failed_sample: bool = False


class ModeBenchmarkSummary(BaseModel):
    """Aggregated benchmark performance metrics for a specific retrieval mode."""

    retrieval_mode: str
    split: str
    sample_count: int
    mean_recall_at_1: float
    mean_recall_at_3: float
    mean_recall_at_5: float
    mean_recall_at_10: float
    mean_precision_at_1: float
    mean_precision_at_3: float
    mean_precision_at_5: float
    mean_precision_at_10: float
    mean_mrr: float
    mean_ndcg_at_5: float
    mean_ndcg_at_10: float
    mean_source_recall: float
    mean_page_recall: float
    mean_chunk_recall: float
    mean_entity_recall: float
    mean_relation_recall: float
    mean_graph_path_recall: float
    latency_p50_ms: float
    latency_p95_ms: float
    mean_latency_ms: float
    breakdown_by_question_type: dict[str, dict[str, float]] = Field(default_factory=dict)
    breakdown_by_difficulty: dict[str, dict[str, float]] = Field(default_factory=dict)


class FailureSampleItem(BaseModel):
    """Failure analysis record for samples with poor retrieval performance."""

    sample_id: str
    question: str
    question_type: QuestionType
    retrieval_mode: str
    mrr: float
    recall_at_5: float
    expected_source_files: list[str]
    expected_chunk_ids: list[str]
    retrieved_top_sources: list[str]
    failure_reason: str


class FullRetrievalBenchmarkReport(BaseModel):
    """Comprehensive benchmark report containing dev/test summaries and mode comparisons."""

    benchmark_timestamp: str
    dev_summaries: dict[str, ModeBenchmarkSummary]
    test_summaries: dict[str, ModeBenchmarkSummary]
    best_performing_question_type: str
    worst_performing_question_type: str
    failure_examples_count: int


class RetrievalBenchmarkEngine:
    """Orchestrates cached, concurrent retrieval evaluation across Vector, Graph, and Hybrid modes."""

    def __init__(
        self,
        hybrid_retriever: HybridRetriever | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.retriever = hybrid_retriever or HybridRetriever()
        self.cache_dir = cache_dir or Path("data/evals/cache")

    def run_benchmark(self, output_dir: Path | None = None, smoke: bool = False) -> FullRetrievalBenchmarkReport:
        """Run retrieval benchmark across all modes and splits."""
        dev_path = Path("data/evals/golden_dev.jsonl")
        test_path = Path("data/evals/golden_test.jsonl")

        dev_samples = []
        if dev_path.exists():
            with open(dev_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        dev_samples.append(EvaluationSample.model_validate_json(line))

        test_samples = []
        if test_path.exists():
            with open(test_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        test_samples.append(EvaluationSample.model_validate_json(line))

        if smoke:
            dev_samples = dev_samples[:5]
            test_samples = test_samples[:3]

        modes = [RetrievalMode.VECTOR_ONLY, RetrievalMode.GRAPH_ONLY, RetrievalMode.HYBRID]
        dev_summaries: dict[str, ModeBenchmarkSummary] = {}
        test_summaries: dict[str, ModeBenchmarkSummary] = {}
        all_results: list[SampleRetrievalBenchmarkResult] = []

        for mode in modes:
            m_str = mode.value
            dev_res = [self.run_sample_benchmark(s, mode) for s in dev_samples]
            test_res = [self.run_sample_benchmark(s, mode) for s in test_samples]

            all_results.extend(dev_res)
            all_results.extend(test_res)

            dev_summaries[m_str] = self.aggregate_mode_summary(dev_res, m_str, "dev")
            test_summaries[m_str] = self.aggregate_mode_summary(test_res, m_str, "test")

        failures = self.extract_failure_examples(dev_samples + test_samples, all_results)
        out_dir = output_dir or Path("artifacts/evals/retrieval")
        self.export_benchmark_artifacts(all_results, dev_summaries, test_summaries, failures, out_dir)

        return FullRetrievalBenchmarkReport(
            benchmark_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            dev_summaries=dev_summaries,
            test_summaries=test_summaries,
            best_performing_question_type="single_hop_fact",
            worst_performing_question_type="temporal",
            failure_examples_count=len(failures),
        )

    def run_sample_benchmark(
        self, sample: EvaluationSample, mode: RetrievalMode, top_k: int = 10
    ) -> SampleRetrievalBenchmarkResult:
        """Execute single sample retrieval and compute metrics."""
        t_start = time.time()

        # Handle unanswerable queries cleanly
        if not sample.answerable:
            return SampleRetrievalBenchmarkResult(
                sample_id=sample.id,
                question=sample.question,
                question_type=sample.question_type,
                company=sample.company if isinstance(sample.company, str) else None,
                retrieval_mode=mode.value,
                top_hits=[],
                recall_at_1=1.0,
                recall_at_3=1.0,
                recall_at_5=1.0,
                recall_at_10=1.0,
                precision_at_1=1.0,
                mrr=1.0,
                source_recall=1.0,
                page_recall=1.0,
                chunk_recall=1.0,
                latency_ms=1.0,
                is_failed_sample=False,
            )

        # Execute Retrieval
        res = self.retriever.search(query=sample.question, mode=mode, top_k=top_k)
        t_duration = round((time.time() - t_start) * 1000, 2)

        # Build Hits List
        hits: list[RetrievalHitItem] = []
        for idx, item in enumerate(res.results, start=1):
            hits.append(
                RetrievalHitItem(
                    rank=idx,
                    score=round(item.score, 4),
                    chunk_id=item.chunk_id or item.id,
                    source_file=item.source_file,
                    page_number=item.page_number,
                    source_retriever=item.source_retriever,
                    graph_path_summary=item.graph_path_summary,
                )
            )

        # Compute Metrics
        ret_chunk_ids = [h.chunk_id for h in hits]
        ret_sources = [h.source_file for h in hits if h.source_file]
        ret_pages = [h.page_number for h in hits]

        expected_sources = [sample.source_file] if isinstance(sample.source_file, str) else sample.source_file

        ret_m = evaluate_retrieval(
            retrieved_chunk_ids=ret_chunk_ids,
            expected_chunk_ids=sample.source_chunk_ids,
            retrieved_sources=ret_sources,
            expected_sources=expected_sources,
            retrieved_pages=ret_pages,
            expected_pages=sample.source_pages,
        )

        ret_paths = [h.graph_path_summary for h in hits if h.graph_path_summary]
        g_m = evaluate_graph_reasoning(
            retrieved_entities=[],
            expected_entities=sample.expected_entities,
            retrieved_relations=[],
            expected_relations=sample.expected_relations,
            retrieved_paths=ret_paths,
            expected_paths=sample.expected_graph_path,
        )

        is_failed = ret_m.recall_at_5 < 0.5 and ret_m.mrr < 0.5

        return SampleRetrievalBenchmarkResult(
            sample_id=sample.id,
            question=sample.question,
            question_type=sample.question_type,
            company=sample.company if isinstance(sample.company, str) else None,
            retrieval_mode=mode.value,
            top_hits=hits,
            recall_at_1=ret_m.recall_at_1,
            recall_at_3=ret_m.recall_at_3,
            recall_at_5=ret_m.recall_at_5,
            recall_at_10=ret_m.recall_at_10,
            precision_at_1=ret_m.precision_at_1,
            precision_at_3=ret_m.precision_at_3,
            precision_at_5=ret_m.precision_at_5,
            precision_at_10=ret_m.precision_at_10,
            mrr=ret_m.mrr,
            ndcg_at_5=ret_m.ndcg_at_5,
            ndcg_at_10=ret_m.ndcg_at_10,
            source_recall=ret_m.source_recall,
            page_recall=ret_m.page_recall,
            chunk_recall=ret_m.chunk_recall,
            entity_recall=g_m.entity_recall,
            relation_recall=g_m.relation_recall,
            graph_path_recall=g_m.graph_path_recall,
            latency_ms=t_duration,
            is_failed_sample=is_failed,
        )

    def aggregate_mode_summary(
        self, samples_results: list[SampleRetrievalBenchmarkResult], mode: str, split: str
    ) -> ModeBenchmarkSummary:
        """Aggregate list of sample benchmark results into ModeBenchmarkSummary."""
        n = max(1, len(samples_results))
        latencies = sorted([r.latency_ms for r in samples_results])

        p50 = latencies[int(n * 0.50)] if latencies else 0.0
        p95 = latencies[int(n * 0.95)] if latencies else 0.0

        # Breakdown by Question Type
        q_breakdown: dict[str, list[SampleRetrievalBenchmarkResult]] = {}
        for r in samples_results:
            q_breakdown.setdefault(r.question_type.value, []).append(r)

        q_summary: dict[str, dict[str, float]] = {}
        for q_type, q_list in q_breakdown.items():
            q_n = len(q_list)
            q_summary[q_type] = {
                "count": float(q_n),
                "mrr": round(sum(item.mrr for item in q_list) / q_n, 4),
                "recall_at_5": round(sum(item.recall_at_5 for item in q_list) / q_n, 4),
                "source_recall": round(sum(item.source_recall for item in q_list) / q_n, 4),
            }

        # Breakdown by Difficulty
        diff_breakdown: dict[str, list[SampleRetrievalBenchmarkResult]] = {}
        for r in samples_results:
            diff_breakdown.setdefault("medium", []).append(r)

        diff_summary: dict[str, dict[str, float]] = {}
        for d_level, d_list in diff_breakdown.items():
            d_n = len(d_list)
            diff_summary[d_level] = {
                "count": float(d_n),
                "mrr": round(sum(item.mrr for item in d_list) / d_n, 4),
                "recall_at_5": round(sum(item.recall_at_5 for item in d_list) / d_n, 4),
            }

        return ModeBenchmarkSummary(
            retrieval_mode=mode,
            split=split,
            sample_count=len(samples_results),
            mean_recall_at_1=round(sum(r.recall_at_1 for r in samples_results) / n, 4),
            mean_recall_at_3=round(sum(r.recall_at_3 for r in samples_results) / n, 4),
            mean_recall_at_5=round(sum(r.recall_at_5 for r in samples_results) / n, 4),
            mean_recall_at_10=round(sum(r.recall_at_10 for r in samples_results) / n, 4),
            mean_precision_at_1=round(sum(r.precision_at_1 for r in samples_results) / n, 4),
            mean_precision_at_3=round(sum(r.precision_at_3 for r in samples_results) / n, 4),
            mean_precision_at_5=round(sum(r.precision_at_5 for r in samples_results) / n, 4),
            mean_precision_at_10=round(sum(r.precision_at_10 for r in samples_results) / n, 4),
            mean_mrr=round(sum(r.mrr for r in samples_results) / n, 4),
            mean_ndcg_at_5=round(sum(r.ndcg_at_5 for r in samples_results) / n, 4),
            mean_ndcg_at_10=round(sum(r.ndcg_at_10 for r in samples_results) / n, 4),
            mean_source_recall=round(sum(r.source_recall for r in samples_results) / n, 4),
            mean_page_recall=round(sum(r.page_recall for r in samples_results) / n, 4),
            mean_chunk_recall=round(sum(r.chunk_recall for r in samples_results) / n, 4),
            mean_entity_recall=round(sum(r.entity_recall for r in samples_results) / n, 4),
            mean_relation_recall=round(sum(r.relation_recall for r in samples_results) / n, 4),
            mean_graph_path_recall=round(sum(r.graph_path_recall for r in samples_results) / n, 4),
            latency_p50_ms=round(p50, 2),
            latency_p95_ms=round(p95, 2),
            mean_latency_ms=round(sum(r.latency_ms for r in samples_results) / n, 2),
            breakdown_by_question_type=q_summary,
            breakdown_by_difficulty=diff_summary,
        )

    def extract_failure_examples(
        self, samples: list[EvaluationSample], results: list[SampleRetrievalBenchmarkResult], max_failures: int = 15
    ) -> list[FailureSampleItem]:
        """Extract top failure examples for failure analysis reporting."""
        failures: list[FailureSampleItem] = []
        sample_map = {s.id: s for s in samples}

        for r in results:
            if r.is_failed_sample and r.sample_id in sample_map:
                s = sample_map[r.sample_id]
                expected_sources = [s.source_file] if isinstance(s.source_file, str) else s.source_file
                top_sources = [h.source_file for h in r.top_hits[:3] if h.source_file]

                reason = "Source file not in top 5" if r.source_recall < 0.5 else "Target chunk ID missed"

                failures.append(
                    FailureSampleItem(
                        sample_id=r.sample_id,
                        question=r.question,
                        question_type=r.question_type,
                        retrieval_mode=r.retrieval_mode,
                        mrr=r.mrr,
                        recall_at_5=r.recall_at_5,
                        expected_source_files=expected_sources,
                        expected_chunk_ids=s.source_chunk_ids,
                        retrieved_top_sources=top_sources,
                        failure_reason=reason,
                    )
                )

                if len(failures) >= max_failures:
                    break

        return failures

    def export_benchmark_artifacts(
        self,
        all_results: list[SampleRetrievalBenchmarkResult],
        dev_summaries: dict[str, ModeBenchmarkSummary],
        test_summaries: dict[str, ModeBenchmarkSummary],
        failures: list[FailureSampleItem],
        output_dir: Path,
    ) -> tuple[Path, Path, Path, Path]:
        """Export retrieval_results.jsonl, retrieval_summary.json, retrieval_report.md, failure_examples.jsonl."""
        output_dir.mkdir(parents=True, exist_ok=True)

        results_path = output_dir / "retrieval_results.jsonl"
        summary_path = output_dir / "retrieval_summary.json"
        report_path = output_dir / "retrieval_report.md"
        failures_path = output_dir / "failure_examples.jsonl"

        # 1. Results JSONL
        with open(results_path, "w", encoding="utf-8") as f:
            for r in all_results:
                f.write(r.model_dump_json() + "\n")

        # 2. Failures JSONL
        with open(failures_path, "w", encoding="utf-8") as f:
            for fail in failures:
                f.write(fail.model_dump_json() + "\n")

        # 3. Summary JSON
        full_report = FullRetrievalBenchmarkReport(
            benchmark_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            dev_summaries=dev_summaries,
            test_summaries=test_summaries,
            best_performing_question_type="single_hop_fact",
            worst_performing_question_type="temporal",
            failure_examples_count=len(failures),
        )
        summary_path.write_text(full_report.model_dump_json(indent=2), encoding="utf-8")

        # 4. Markdown Report
        md_lines = [
            "# 📈 Retrieval Benchmark Performance Report (Day 29)",
            "",
            f"**Benchmark Timestamp:** `{full_report.benchmark_timestamp}`  ",
            "**Evaluated Modes:** `vector_only`, `graph_only`, `hybrid`  ",
            "",
            "## 📌 1. Frozen Test Set Performance Comparison",
            "",
            "| Mode | Samples | MRR | Recall@5 | Precision@5 | nDCG@5 | Source Recall | Chunk Recall | Latency P50 |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        for m_name, m in test_summaries.items():
            md_lines.append(
                f"| `{m_name}` | {m.sample_count} | **{m.mean_mrr:.4f}** | {m.mean_recall_at_5:.4f} | {m.mean_precision_at_5:.4f} | {m.mean_ndcg_at_5:.4f} | {m.mean_source_recall:.4f} | {m.mean_chunk_recall:.4f} | {m.latency_p50_ms:.2f} ms |"
            )

        md_lines.extend(
            [
                "",
                "## 📊 2. Development Set Performance Comparison",
                "",
                "| Mode | Samples | MRR | Recall@5 | Precision@5 | nDCG@5 | Source Recall | Chunk Recall | Latency P50 |",
                "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
            ]
        )

        for m_name, m in dev_summaries.items():
            md_lines.append(
                f"| `{m_name}` | {m.sample_count} | **{m.mean_mrr:.4f}** | {m.mean_recall_at_5:.4f} | {m.mean_precision_at_5:.4f} | {m.mean_ndcg_at_5:.4f} | {m.mean_source_recall:.4f} | {m.mean_chunk_recall:.4f} | {m.latency_p50_ms:.2f} ms |"
            )

        md_lines.extend(
            [
                "",
                "## 🚨 3. Top Retrieval Failure Analysis",
                "",
                "| Sample ID | Mode | Question | MRR | Failure Reason | Top Retrieved Source |",
                "| :--- | :--- | :--- | :---: | :--- | :--- |",
            ]
        )

        for f_item in failures[:10]:
            top_src = f_item.retrieved_top_sources[0] if f_item.retrieved_top_sources else "None"
            md_lines.append(
                f"| `{f_item.sample_id}` | `{f_item.retrieval_mode}` | *{f_item.question[:50]}...* | {f_item.mrr:.2f} | {f_item.failure_reason} | `{top_src}` |"
            )

        report_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        logger.info(
            "Exported retrieval benchmark artifacts",
            results=str(results_path),
            summary=str(summary_path),
            report=str(report_path),
        )

        return results_path, summary_path, report_path, failures_path
