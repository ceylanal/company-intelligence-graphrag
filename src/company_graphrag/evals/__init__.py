"""Modular Evaluation Framework package for GraphRAG benchmark suite (Day 27 - Day 33)."""

from company_graphrag.evals.answer_evaluator import AnswerEvaluationEngine
from company_graphrag.evals.answer_metrics import (
    calculate_abstention_accuracy,
    calculate_answer_completeness,
    calculate_exact_match,
    calculate_normalized_match,
    calculate_numeric_accuracy,
    calculate_token_f1,
    evaluate_answer,
)
from company_graphrag.evals.answer_models import (
    AnswerFailureSampleItem,
    AnswerModeSummary,
    FullAnswerEvaluationReport,
    LLMJudgeResult,
    SampleAnswerEvalResult,
    SentenceSupportResult,
)
from company_graphrag.evals.calibration import (
    CalibrationEngine,
    CalibrationReportSummary,
    check_human_labels_exist,
)
from company_graphrag.evals.citation_metrics import (
    calculate_citation_coverage,
    calculate_citation_precision,
    calculate_citation_recall,
    calculate_cited_page_accuracy,
    evaluate_citations,
)
from company_graphrag.evals.citation_verifier import verify_sentence_to_source_support
from company_graphrag.evals.dataset_builder import GoldenDatasetBuilder, deduplicate_samples
from company_graphrag.evals.evaluator import EvaluationEngine
from company_graphrag.evals.final_eval import (
    FinalBenchmarkRunner,
    FinalEvaluationSummary,
    SystemFinalScorecard,
)
from company_graphrag.evals.graph_metrics import (
    calculate_entity_recall,
    calculate_graph_path_recall,
    calculate_relation_recall,
    evaluate_graph_reasoning,
)
from company_graphrag.evals.human_eval import (
    BlindedAnnotationItem,
    ErrorCategory,
    HumanAnnotationBuilder,
    HumanAnnotationLabel,
    HumanAnnotationStore,
)
from company_graphrag.evals.llm_judge import LLMJudgeEvaluator
from company_graphrag.evals.models import (
    AnswerMetricsResult,
    CitationMetricsResult,
    DatasetSplit,
    DifficultyLevel,
    EvaluationRunReport,
    EvaluationSample,
    GraphMetricsResult,
    MethodAggregatedMetrics,
    QuestionType,
    RetrievalMetricsResult,
    SampleEvalResult,
)
from company_graphrag.evals.regression_check import (
    FullRegressionCheckReport,
    RegressionCheckEngine,
)
from company_graphrag.evals.retrieval_benchmark import (
    FailureSampleItem,
    FullRetrievalBenchmarkReport,
    ModeBenchmarkSummary,
    RetrievalBenchmarkEngine,
    SampleRetrievalBenchmarkResult,
)
from company_graphrag.evals.retrieval_metrics import (
    calculate_lineage_recall,
    calculate_mrr,
    calculate_ndcg_at_k,
    calculate_precision_at_k,
    calculate_recall_at_k,
    evaluate_retrieval,
)
from company_graphrag.evals.validator import DatasetValidationReport, EvaluationDatasetValidator

__all__ = [
    "EvaluationSample",
    "QuestionType",
    "DifficultyLevel",
    "DatasetSplit",
    "RetrievalMetricsResult",
    "AnswerMetricsResult",
    "CitationMetricsResult",
    "GraphMetricsResult",
    "SampleEvalResult",
    "MethodAggregatedMetrics",
    "EvaluationRunReport",
    "EvaluationEngine",
    "GoldenDatasetBuilder",
    "deduplicate_samples",
    "EvaluationDatasetValidator",
    "DatasetValidationReport",
    "RetrievalBenchmarkEngine",
    "SampleRetrievalBenchmarkResult",
    "ModeBenchmarkSummary",
    "FailureSampleItem",
    "FullRetrievalBenchmarkReport",
    # Day 30 Answer & Citation Eval Symbols
    "AnswerEvaluationEngine",
    "SentenceSupportResult",
    "verify_sentence_to_source_support",
    "LLMJudgeEvaluator",
    "LLMJudgeResult",
    "SampleAnswerEvalResult",
    "AnswerModeSummary",
    "AnswerFailureSampleItem",
    "FullAnswerEvaluationReport",
    # Day 31 Human Annotation Symbols
    "BlindedAnnotationItem",
    "HumanAnnotationLabel",
    "ErrorCategory",
    "HumanAnnotationBuilder",
    "HumanAnnotationStore",
    # Day 32 Calibration & Regression Symbols
    "CalibrationEngine",
    "CalibrationReportSummary",
    "check_human_labels_exist",
    "RegressionCheckEngine",
    "FullRegressionCheckReport",
    # Day 33 Final Evaluation Symbols
    "FinalBenchmarkRunner",
    "FinalEvaluationSummary",
    "SystemFinalScorecard",
    # Metrics
    "calculate_recall_at_k",
    "calculate_precision_at_k",
    "calculate_mrr",
    "calculate_ndcg_at_k",
    "calculate_lineage_recall",
    "evaluate_retrieval",
    "calculate_exact_match",
    "calculate_token_f1",
    "calculate_normalized_match",
    "calculate_numeric_accuracy",
    "calculate_answer_completeness",
    "calculate_abstention_accuracy",
    "evaluate_answer",
    "calculate_citation_precision",
    "calculate_citation_recall",
    "calculate_citation_coverage",
    "calculate_cited_page_accuracy",
    "evaluate_citations",
    "calculate_entity_recall",
    "calculate_relation_recall",
    "calculate_graph_path_recall",
    "evaluate_graph_reasoning",
]
