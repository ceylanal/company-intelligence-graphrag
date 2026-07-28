"""Pydantic data models for evaluation samples, metrics results, and run reports."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class QuestionType(StrEnum):
    """Categorized question types for GraphRAG evaluation."""

    SINGLE_HOP_FACT = "single_hop_fact"
    MULTI_HOP_GRAPH = "multi_hop_graph"
    COMPARISON = "comparison"
    TEMPORAL = "temporal"
    AGGREGATION = "aggregation"
    UNANSWERABLE = "unanswerable"
    CITATION_VERIFICATION = "citation_verification"


class DifficultyLevel(StrEnum):
    """Evaluation sample difficulty level."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class DatasetSplit(StrEnum):
    """Dataset partition split."""

    TRAIN = "train"
    VAL = "val"
    TEST = "test"


class EvaluationSample(BaseModel):
    """Standard evaluation sample record for GraphRAG benchmark suite."""

    id: str = Field(description="Unique evaluation sample identifier e.g. eval_001")
    question: str = Field(description="Natural language question string")
    question_type: QuestionType = Field(description="Question taxonomy category")
    company: str | list[str] | None = Field(default=None, description="Target company or companies")
    expected_answer: str = Field(description="Canonical reference ground truth answer")
    acceptable_answers: list[str] = Field(default_factory=list, description="Alternative acceptable answers")
    source_file: str | list[str] = Field(description="Ground truth source PDF filename(s)")
    source_pages: list[int] = Field(default_factory=list, description="Ground truth source page numbers")
    source_chunk_ids: list[str] = Field(default_factory=list, description="Ground truth source chunk IDs")
    expected_entities: list[str] = Field(default_factory=list, description="Ground truth entity names")
    expected_relations: list[str] = Field(default_factory=list, description="Ground truth relationship types")
    expected_graph_path: list[str] = Field(default_factory=list, description="Ground truth graph path sequence")
    answerable: bool = Field(default=True, description="False if question is out-of-domain or unanswerable")
    difficulty: DifficultyLevel = Field(default=DifficultyLevel.MEDIUM, description="Difficulty rating")
    split: DatasetSplit = Field(default=DatasetSplit.TEST, description="Dataset partition split")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional custom metadata fields")


class RetrievalMetricsResult(BaseModel):
    """Evaluated retrieval performance metrics."""

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


class AnswerMetricsResult(BaseModel):
    """Evaluated answer quality performance metrics."""

    exact_match: float = 0.0
    token_f1: float = 0.0
    normalized_match: float = 0.0
    numeric_accuracy: float = 0.0
    answer_completeness: float = 0.0
    abstention_accuracy: float = 0.0


class CitationMetricsResult(BaseModel):
    """Evaluated citation quality metrics."""

    citation_precision: float = 0.0
    citation_recall: float = 0.0
    citation_coverage: float = 0.0
    cited_page_accuracy: float = 0.0


class GraphMetricsResult(BaseModel):
    """Evaluated graph reasoning metrics."""

    entity_recall: float = 0.0
    relation_recall: float = 0.0
    graph_path_recall: float = 0.0


class SampleEvalResult(BaseModel):
    """Complete evaluation result for a single sample and method."""

    sample_id: str
    question_type: QuestionType
    method: str = Field(description="'vector', 'graph', or 'hybrid'")
    retrieval: RetrievalMetricsResult
    answer: AnswerMetricsResult
    citation: CitationMetricsResult
    graph: GraphMetricsResult
    latency_ms: float = 0.0
    overall_sample_score: float = 0.0


class MethodAggregatedMetrics(BaseModel):
    """Aggregated metrics summary for a specific retrieval/generation method."""

    method: str
    sample_count: int
    mean_retrieval_mrr: float
    mean_retrieval_recall_at_5: float
    mean_answer_token_f1: float
    mean_numeric_accuracy: float
    mean_abstention_accuracy: float
    mean_citation_precision: float
    mean_graph_path_recall: float
    mean_latency_ms: float
    overall_method_score: float


class EvaluationRunReport(BaseModel):
    """Comprehensive evaluation run report comparing multiple methods across a dataset."""

    run_timestamp: str
    total_samples: int
    splits_evaluated: list[str]
    question_type_distribution: dict[str, int]
    method_summaries: dict[str, MethodAggregatedMetrics]
    sample_results: list[SampleEvalResult] = Field(default_factory=list)
