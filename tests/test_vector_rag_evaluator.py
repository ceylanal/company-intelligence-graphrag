"""Unit tests for VectorRAGEvaluator benchmark execution and summary calculation (Day 17)."""

from pathlib import Path

from company_graphrag.embeddings import TextEmbeddingEncoder
from company_graphrag.evaluation.vector_rag_evaluator import VectorRAGEvaluator
from company_graphrag.rag.pipeline import VectorRAGPipeline
from company_graphrag.retrieval.vector_retriever import VectorRetriever


def test_evaluator_load_questions() -> None:
    """Test loading benchmark questions from JSONL dataset."""
    evaluator = VectorRAGEvaluator()
    questions = evaluator.load_questions(limit=5)

    assert len(questions) == 5
    assert questions[0].question_id == "Q01"
    assert questions[0].expected_ticker == "ASELS"
    evaluator.close()


def test_evaluator_run_small_suite(tmp_path: Path) -> None:
    """Test running evaluation suite across 3 sample questions."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)
    evaluator = VectorRAGEvaluator(pipeline=pipeline)

    summary, results = evaluator.evaluate_all(
        output_dir=tmp_path,
        limit=3,
    )

    assert summary.total_questions == 3
    assert summary.hit_rate_at_3 >= 0.0
    assert summary.mrr >= 0.0
    assert len(results) == 3
    assert (tmp_path / "vector_rag_results.jsonl").exists()

    evaluator.close()
