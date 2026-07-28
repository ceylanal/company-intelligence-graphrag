"""Answer & Citation Evaluation Engine evaluating RAG answer generation, citations, and abstention across golden datasets."""

import json
import time
from pathlib import Path

from structlog import get_logger

from company_graphrag.evals.answer_metrics import (
    calculate_abstention_accuracy,
    calculate_answer_completeness,
    calculate_exact_match,
    calculate_numeric_accuracy,
    calculate_token_f1,
)
from company_graphrag.evals.answer_models import (
    AnswerFailureSampleItem,
    AnswerModeSummary,
    FullAnswerEvaluationReport,
    SampleAnswerEvalResult,
)
from company_graphrag.evals.citation_verifier import verify_sentence_to_source_support
from company_graphrag.evals.llm_judge import LLMJudgeEvaluator
from company_graphrag.evals.models import EvaluationSample
from company_graphrag.graph.generation.generator import GraphRAGGenerator
from company_graphrag.retrieval.hybrid import HybridRetriever, RetrievalMode

logger = get_logger(__name__)


class AnswerEvaluationEngine:
    """Orchestrates RAG answer and citation evaluation across Vector, Graph, and Hybrid modes."""

    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        generator: GraphRAGGenerator | None = None,
        judge_enabled: bool = False,
        cache_dir: Path | None = None,
    ) -> None:
        self.retriever = retriever or HybridRetriever()
        self.generator = generator or GraphRAGGenerator()
        self.judge_evaluator = LLMJudgeEvaluator(cache_dir=cache_dir, enabled=judge_enabled)

    def evaluate_mode(
        self, mode: RetrievalMode, split: str = "test", smoke: bool = False
    ) -> tuple[list[SampleAnswerEvalResult], AnswerModeSummary]:
        """Evaluate all samples in split for a single mode."""
        dataset_path = Path("data/evals/golden_dev.jsonl" if split == "dev" else "data/evals/golden_test.jsonl")
        samples = []
        if dataset_path.exists():
            with open(dataset_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        samples.append(EvaluationSample.model_validate_json(line))

        if smoke:
            samples = samples[:5] if split == "dev" else samples[:3]

        results = [self.evaluate_sample_answer(s, mode) for s in samples]
        summary = self.aggregate_mode_summary(results, mode.value, split)
        return results, summary

    def evaluate_sample_answer(
        self, sample: EvaluationSample, mode: RetrievalMode, top_k: int = 5
    ) -> SampleAnswerEvalResult:
        """Execute single sample RAG answer generation and compute all deterministic & citation metrics."""
        t_start = time.time()

        # 1. Execute Retrieval & Generation under deterministic settings
        comp_filter = sample.company if isinstance(sample.company, str) else None
        ret_res = self.retriever.search(query=sample.question, mode=mode, top_k=top_k)
        answer_res = self.generator.generate_answer(query=sample.question, hybrid_response=ret_res)
        t_duration = round((time.time() - t_start) * 1000, 2)

        gen_answer = answer_res.detailed_explanation or answer_res.short_answer
        is_refusal = answer_res.insufficient_context or ("yeterli kanıt bulunamadı" in gen_answer.lower())

        # Build Context Summary
        context_texts = [item.text for item in ret_res.results]
        context_summary = " ".join(context_texts[:3])

        # Extract Citations
        cited_sources: list[str] = []
        for c in answer_res.citations:
            if isinstance(c.source_file, str) and c.source_file:
                cited_sources.append(c.source_file)
            elif isinstance(c.source_file, list):
                cited_sources.extend([str(sf) for sf in c.source_file if sf])

        # 2. Compute Deterministic Answer Metrics
        em = calculate_exact_match(gen_answer, sample.expected_answer)
        f1 = calculate_token_f1(gen_answer, sample.expected_answer)
        num_acc = calculate_numeric_accuracy(gen_answer, sample.expected_answer)
        acc_match = calculate_answer_completeness(gen_answer, sample.acceptable_answers)

        abstention_acc = calculate_abstention_accuracy(
            is_abstained=is_refusal,
            answerable=sample.answerable,
        )

        # 3. Compute Sentence-to-Source Citation Verification Metrics
        expected_sources = [sample.source_file] if isinstance(sample.source_file, str) else sample.source_file

        support_info, c_prec, c_rec, c_cov, src_acc, page_acc = verify_sentence_to_source_support(
            generated_answer=gen_answer,
            retrieved_contexts=context_texts,
            cited_sources=cited_sources,
            expected_sources=expected_sources,
            expected_pages=sample.source_pages,
        )

        # 4. LLM Judge Evaluation
        judge_res = self.judge_evaluator.evaluate_sample(
            question=sample.question,
            expected_answer=sample.expected_answer,
            retrieved_context=context_summary,
            generated_answer=gen_answer,
        )

        is_failed = (f1 < 0.3 and not sample.answerable and not is_refusal) or (f1 < 0.2 and sample.answerable)

        return SampleAnswerEvalResult(
            sample_id=sample.id,
            question=sample.question,
            question_type=sample.question_type,
            company=comp_filter,
            retrieval_mode=mode.value,
            generated_answer=gen_answer,
            retrieved_context_summary=context_summary[:300],
            citations_count=len(answer_res.citations),
            citation_sources=cited_sources,
            latency_ms=t_duration,
            is_abstention=is_refusal,
            answerable=sample.answerable,
            exact_match=round(em, 4),
            token_f1=round(f1, 4),
            numeric_accuracy=round(num_acc, 4),
            acceptable_match=round(acc_match, 4),
            abstention_correct=bool(abstention_acc == 1.0),
            citation_precision=c_prec,
            citation_recall=c_rec,
            citation_coverage=c_cov,
            source_file_accuracy=src_acc,
            page_accuracy=page_acc,
            chunk_support_accuracy=support_info.sentence_support_score,
            judge_result=judge_res,
            is_failed_sample=is_failed,
        )

    def aggregate_mode_summary(
        self, sample_results: list[SampleAnswerEvalResult], mode: str, split: str
    ) -> AnswerModeSummary:
        """Aggregate sample answer results into Mode summary."""
        n = max(1, len(sample_results))

        # Abstention Metrics
        correct_abstentions = sum(1 for r in sample_results if not r.answerable and r.is_abstention)
        total_unanswerable = max(1, sum(1 for r in sample_results if not r.answerable))
        total_abstentions = max(1, sum(1 for r in sample_results if r.is_abstention))

        abs_prec = round(correct_abstentions / total_abstentions, 4)
        abs_rec = round(correct_abstentions / total_unanswerable, 4)
        abs_f1 = round((2 * abs_prec * abs_rec) / max(0.001, (abs_prec + abs_rec)), 4)
        ans_acc = round(sum(1 for r in sample_results if r.abstention_correct) / n, 4)

        # Judge Aggregates
        judge_enabled = self.judge_evaluator.enabled
        mean_corr = round(sum(r.judge_result.correctness for r in sample_results if r.judge_result) / n, 2)
        mean_comp = round(sum(r.judge_result.completeness for r in sample_results if r.judge_result) / n, 2)
        mean_faith = round(sum(r.judge_result.faithfulness for r in sample_results if r.judge_result) / n, 2)
        mean_rel = round(sum(r.judge_result.relevance for r in sample_results if r.judge_result) / n, 2)
        mean_cit_supp = round(sum(r.judge_result.citation_support for r in sample_results if r.judge_result) / n, 2)

        return AnswerModeSummary(
            retrieval_mode=mode,
            split=split,
            sample_count=len(sample_results),
            mean_exact_match=round(sum(r.exact_match for r in sample_results) / n, 4),
            mean_token_f1=round(sum(r.token_f1 for r in sample_results) / n, 4),
            mean_numeric_accuracy=round(sum(r.numeric_accuracy for r in sample_results) / n, 4),
            mean_acceptable_match=round(sum(r.acceptable_match for r in sample_results) / n, 4),
            answerable_accuracy=ans_acc,
            abstention_precision=abs_prec,
            abstention_recall=abs_rec,
            abstention_f1=abs_f1,
            mean_citation_precision=round(sum(r.citation_precision for r in sample_results) / n, 4),
            mean_citation_recall=round(sum(r.citation_recall for r in sample_results) / n, 4),
            mean_citation_coverage=round(sum(r.citation_coverage for r in sample_results) / n, 4),
            source_file_accuracy=round(sum(r.source_file_accuracy for r in sample_results) / n, 4),
            page_accuracy=round(sum(r.page_accuracy for r in sample_results) / n, 4),
            chunk_support_accuracy=round(sum(r.chunk_support_accuracy for r in sample_results) / n, 4),
            judge_enabled=judge_enabled,
            mean_correctness=mean_corr,
            mean_completeness=mean_comp,
            mean_faithfulness=mean_faith,
            mean_relevance=mean_rel,
            mean_citation_support=mean_cit_supp,
            mean_latency_ms=round(sum(r.latency_ms for r in sample_results) / n, 2),
        )

    def extract_failure_examples(
        self, samples: list[EvaluationSample], results: list[SampleAnswerEvalResult], max_failures: int = 15
    ) -> list[AnswerFailureSampleItem]:
        """Extract top 15 failure examples for qualitative failure analysis."""
        failures: list[AnswerFailureSampleItem] = []
        sample_map = {s.id: s for s in samples}

        for r in results:
            if r.is_failed_sample and r.sample_id in sample_map:
                s = sample_map[r.sample_id]
                reason = "Hallucination / Missed refusal" if not s.answerable else "Low token overlap"
                failures.append(
                    AnswerFailureSampleItem(
                        sample_id=r.sample_id,
                        question=r.question,
                        question_type=r.question_type,
                        retrieval_mode=r.retrieval_mode,
                        token_f1=r.token_f1,
                        citation_coverage=r.citation_coverage,
                        generated_answer=r.generated_answer[:100],
                        expected_answer=s.expected_answer[:100],
                        failure_reason=reason,
                    )
                )

                if len(failures) >= max_failures:
                    break

        return failures

    def export_evaluation_artifacts(
        self,
        all_results: list[SampleAnswerEvalResult],
        dev_summaries: dict[str, AnswerModeSummary],
        test_summaries: dict[str, AnswerModeSummary],
        failures: list[AnswerFailureSampleItem],
        output_dir: Path,
    ) -> tuple[Path, Path, Path, Path, Path]:
        """Export answer_results.jsonl, answer_summary.json, citation_summary.json, answer_report.md, and judge_prompt.md."""
        output_dir.mkdir(parents=True, exist_ok=True)

        results_path = output_dir / "answer_results.jsonl"
        summary_path = output_dir / "answer_summary.json"
        cit_summary_path = output_dir / "citation_summary.json"
        report_path = output_dir / "answer_report.md"

        # 1. Export Results JSONL
        with open(results_path, "w", encoding="utf-8") as f:
            for r in all_results:
                f.write(r.model_dump_json() + "\n")

        # 2. Export Failures JSONL
        fail_path = output_dir / "failure_examples.jsonl"
        with open(fail_path, "w", encoding="utf-8") as f:
            for fail in failures:
                f.write(fail.model_dump_json() + "\n")

        # 3. Export Answer Summary JSON
        full_report = FullAnswerEvaluationReport(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            dev_summaries=dev_summaries,
            test_summaries=test_summaries,
            llm_calls_count=self.judge_evaluator.llm_calls_count,
            cache_hits_count=self.judge_evaluator.cache_hits_count,
            judge_enabled=self.judge_evaluator.enabled,
            failure_examples_count=len(failures),
        )
        summary_path.write_text(full_report.model_dump_json(indent=2), encoding="utf-8")

        # 4. Export Citation Summary JSON
        cit_data = {
            "timestamp": full_report.timestamp,
            "test_citation_summaries": {
                mode: {
                    "citation_precision": s.mean_citation_precision,
                    "citation_recall": s.mean_citation_recall,
                    "citation_coverage": s.mean_citation_coverage,
                    "source_file_accuracy": s.source_file_accuracy,
                    "chunk_support_accuracy": s.chunk_support_accuracy,
                }
                for mode, s in test_summaries.items()
            },
        }
        cit_summary_path.write_text(json.dumps(cit_data, indent=2), encoding="utf-8")

        # 5. Export Judge Prompt MD
        judge_prompt_path = self.judge_evaluator.export_judge_prompt(output_dir)

        # 6. Generate Markdown Report
        md_lines = [
            "# 📝 RAG Answer & Citation Evaluation Report (Day 30)",
            "",
            f"**Evaluation Timestamp:** `{full_report.timestamp}`  ",
            f"**LLM Judge Enabled:** `{self.judge_evaluator.enabled}` (LLM Calls: `{self.judge_evaluator.llm_calls_count}`, Cache Hits: `{self.judge_evaluator.cache_hits_count}`)  ",
            "",
            "## 📌 1. Deterministic Answer Quality Comparison (Frozen Test Set)",
            "",
            "| Mode | Samples | Exact Match | Token F1 | Numeric Acc | Abstention F1 | Latency |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        for m_name, m in test_summaries.items():
            md_lines.append(
                f"| `{m_name}` | {m.sample_count} | **{m.mean_exact_match:.4f}** | **{m.mean_token_f1:.4f}** | {m.mean_numeric_accuracy:.4f} | {m.abstention_f1:.4f} | {m.mean_latency_ms:.2f} ms |"
            )

        md_lines.extend(
            [
                "",
                "## 📌 2. Citation & Sentence Grounded Support Comparison (Frozen Test Set)",
                "",
                "| Mode | Citation Precision | Citation Recall | Coverage | Source Acc | Chunk Support Acc |",
                "| :--- | :---: | :---: | :---: | :---: | :---: |",
            ]
        )

        for m_name, m in test_summaries.items():
            md_lines.append(
                f"| `{m_name}` | **{m.mean_citation_precision:.4f}** | {m.mean_citation_recall:.4f} | {m.mean_citation_coverage:.4f} | {m.source_file_accuracy:.4f} | {m.chunk_support_accuracy:.4f} |"
            )

        md_lines.extend(
            [
                "",
                "## 🧑‍⚖️ 3. LLM-as-a-Judge Evaluation Ratings (1-5 Scale)",
                "",
                "| Mode | Correctness | Completeness | Faithfulness | Relevance | Citation Support |",
                "| :--- | :---: | :---: | :---: | :---: | :---: |",
            ]
        )

        for m_name, m in test_summaries.items():
            md_lines.append(
                f"| `{m_name}` | **{m.mean_correctness:.2f}** | {m.mean_completeness:.2f} | **{m.mean_faithfulness:.2f}** | {m.mean_relevance:.2f} | {m.mean_citation_support:.2f} |"
            )

        md_lines.extend(
            [
                "",
                "## 🚨 4. Top Failure Analysis",
                "",
                "| Sample ID | Mode | Question | Token F1 | Failure Reason |",
                "| :--- | :--- | :--- | :---: | :--- |",
            ]
        )

        for f_item in failures[:10]:
            md_lines.append(
                f"| `{f_item.sample_id}` | `{f_item.retrieval_mode}` | *{f_item.question[:50]}...* | {f_item.token_f1:.2f} | {f_item.failure_reason} |"
            )

        report_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        logger.info(
            "Exported answer evaluation artifacts",
            results=str(results_path),
            summary=str(summary_path),
            report=str(report_path),
        )

        return results_path, summary_path, cit_summary_path, report_path, judge_prompt_path
