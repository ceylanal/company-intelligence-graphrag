"""Pydantic data models for Answer & Citation Evaluation suite (Day 30)."""

from pydantic import BaseModel, Field

from company_graphrag.evals.models import QuestionType


class LLMJudgeResult(BaseModel):
    """LLM-as-a-judge scores and qualitative feedback."""

    correctness: float = Field(ge=1.0, le=5.0, description="Factual correctness rating (1-5)")
    completeness: float = Field(ge=1.0, le=5.0, description="Completeness of answer (1-5)")
    faithfulness: float = Field(ge=1.0, le=5.0, description="Faithfulness to grounded context (1-5)")
    relevance: float = Field(ge=1.0, le=5.0, description="Relevance to question (1-5)")
    citation_support: float = Field(ge=1.0, le=5.0, description="Citation accuracy and support (1-5)")
    reasoning: str = ""
    judge_cached: bool = False


class SentenceSupportResult(BaseModel):
    """Sentence-to-source grounded support evaluation result."""

    total_sentences: int = 0
    cited_sentences: int = 0
    supported_sentences: int = 0
    unsupported_sentences: int = 0
    sentence_support_score: float = 0.0


class SampleAnswerEvalResult(BaseModel):
    """Detailed evaluation result for a single sample answer."""

    sample_id: str
    question: str
    question_type: QuestionType
    company: str | None = None
    retrieval_mode: str
    generated_answer: str
    retrieved_context_summary: str = ""
    citations_count: int = 0
    citation_sources: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    is_abstention: bool = False
    answerable: bool = True

    # Deterministic Answer Metrics
    exact_match: float = 0.0
    token_f1: float = 0.0
    numeric_accuracy: float = 0.0
    acceptable_match: float = 0.0
    abstention_correct: bool = False

    # Citation Metrics
    citation_precision: float = 0.0
    citation_recall: float = 0.0
    citation_coverage: float = 0.0
    source_file_accuracy: float = 0.0
    page_accuracy: float = 0.0
    chunk_support_accuracy: float = 0.0

    # LLM Judge Ratings (Optional)
    judge_result: LLMJudgeResult | None = None
    is_failed_sample: bool = False


class AnswerModeSummary(BaseModel):
    """Aggregated evaluation summary for a specific retrieval/generation mode."""

    retrieval_mode: str
    split: str
    sample_count: int

    # Answer Quality Metrics
    mean_exact_match: float
    mean_token_f1: float
    mean_numeric_accuracy: float
    mean_acceptable_match: float
    answerable_accuracy: float
    abstention_precision: float
    abstention_recall: float
    abstention_f1: float

    # Citation Metrics
    mean_citation_precision: float
    mean_citation_recall: float
    mean_citation_coverage: float
    source_file_accuracy: float
    page_accuracy: float
    chunk_support_accuracy: float

    # LLM Judge Aggregates (Optional)
    judge_enabled: bool = False
    mean_correctness: float = 0.0
    mean_completeness: float = 0.0
    mean_faithfulness: float = 0.0
    mean_relevance: float = 0.0
    mean_citation_support: float = 0.0

    mean_latency_ms: float = 0.0


class AnswerFailureSampleItem(BaseModel):
    """Failure analysis record for poorly performing answer generations."""

    sample_id: str
    question: str
    question_type: QuestionType
    retrieval_mode: str
    token_f1: float
    citation_coverage: float
    generated_answer: str
    expected_answer: str
    failure_reason: str


class FullAnswerEvaluationReport(BaseModel):
    """Comprehensive answer & citation evaluation report."""

    timestamp: str
    dev_summaries: dict[str, AnswerModeSummary]
    test_summaries: dict[str, AnswerModeSummary]
    llm_calls_count: int
    cache_hits_count: int
    judge_enabled: bool
    failure_examples_count: int
