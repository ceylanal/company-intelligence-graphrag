"""Pydantic models for Vector RAG Evaluation, Benchmarking, and Sign-off."""

from pydantic import BaseModel, Field


class QuestionItem(BaseModel):
    """Evaluation test question item from JSONL dataset."""

    question_id: str = Field(description="Unique question identifier")
    question: str = Field(description="Natural language question text")
    language: str = Field(default="tr", description="Question language code")
    question_type: str = Field(description="Category of question")
    expected_company: str | None = Field(default=None, description="Expected commercial company name")
    expected_ticker: str | None = Field(default=None, description="Expected stock ticker symbol")
    expected_year: int | None = Field(default=None, description="Expected report year")
    expected_keywords: list[str] = Field(default_factory=list, description="Expected keywords in retrieved context")
    answerable: bool = Field(default=True, description="True if answer is in document dataset")
    notes: str = Field(default="", description="Notes or category description")


class HumanReviewItem(BaseModel):
    """Manual human evaluation annotation item."""

    question_id: str = Field(description="Question ID reviewed")
    correct: bool = Field(default=True, description="Answer is factually correct")
    grounded: bool = Field(default=True, description="Answer is grounded in provided context")
    citation_complete: bool = Field(default=True, description="All key claims are cited")
    citation_correct: bool = Field(default=True, description="Citations link to correct chunks")
    hallucination_detected: bool = Field(default=False, description="Unsubstantiated info added")
    helpful: bool = Field(default=True, description="Response is helpful and concise")
    review_notes: str = Field(default="", description="Review comments")


class EvaluationResultItem(BaseModel):
    """Execution result for a single question evaluation."""

    question_id: str = Field(description="Question identifier")
    question: str = Field(description="Raw question text")
    question_type: str = Field(description="Category of question")
    answer: str = Field(description="Generated grounded answer")
    citations: list[int] = Field(default_factory=list, description="Source numbers cited")
    used_source_count: int = Field(description="Number of sources used")
    retrieved_count: int = Field(description="Total retrieved hits count")
    insufficient_context: bool = Field(description="True if context was marked insufficient")
    stage_timings_ms: dict[str, float] = Field(default_factory=dict, description="Stage timings breakdown")
    warnings: list[str] = Field(default_factory=list, description="Execution warnings")
    hit_at_1: bool = Field(default=False, description="True if expected ticker/company in rank 1 hit")
    hit_at_3: bool = Field(default=False, description="True if expected ticker/company in top 3 hits")
    hit_at_5: bool = Field(default=False, description="True if expected ticker/company in top 5 hits")
    reciprocal_rank: float = Field(default=0.0, description="Reciprocal rank value")
    top3_company_matched: bool = Field(default=False, description="True if correct company in top 3 hits")
    top3_year_matched: bool = Field(default=False, description="True if correct year in top 3 hits")
    citation_validity: float = Field(default=1.0, description="Citation validity ratio")
    citation_correctness: float = Field(default=1.0, description="Citation correctness ratio")
    human_review: HumanReviewItem | None = Field(default=None, description="Human review annotation if present")


class EvaluationSummary(BaseModel):
    """Overall Vector RAG Evaluation Summary and Sign-off Metrics."""

    total_questions: int = Field(description="Total benchmark questions evaluated")
    successful_evaluations: int = Field(description="Number of successful evaluations")
    failed_evaluations: int = Field(description="Number of failed evaluations")
    hit_rate_at_1: float = Field(description="Hit Rate @ Rank 1 ratio")
    hit_rate_at_3: float = Field(description="Hit Rate @ Top 3 ratio")
    hit_rate_at_5: float = Field(description="Hit Rate @ Top 5 ratio")
    mrr: float = Field(description="Mean Reciprocal Rank score")
    top3_company_accuracy: float = Field(description="Top 3 Company Match Rate")
    top3_year_accuracy: float = Field(description="Top 3 Year Match Rate")
    filter_accuracy: float = Field(description="Metadata filter accuracy rate")
    avg_unique_sources_top5: float = Field(description="Average unique sources count in top 5")
    duplicate_rate: float = Field(description="Duplicate chunk ratio")
    citation_validity_rate: float = Field(description="Citation validity rate (valid in context)")
    citation_correctness_rate: float = Field(description="Citation correctness rate")
    citation_completeness_rate: float = Field(description="Citation completeness rate")
    hallucination_rate: float = Field(description="Hallucination rate")
    insufficient_context_accuracy: float = Field(description="Unanswerable questions detection accuracy")
    avg_retrieval_ms: float = Field(description="Average retrieval stage duration in ms")
    avg_reranking_ms: float = Field(description="Average reranking stage duration in ms")
    avg_generation_ms: float = Field(description="Average generation stage duration in ms")
    avg_total_ms: float = Field(description="Average total pipeline duration in ms")
    overall_status: str = Field(description="Sign-off status: PASS, CONDITIONAL_PASS, or FAIL")
    status_reasons: list[str] = Field(default_factory=list, description="Reasoning for pass/fail decision")
