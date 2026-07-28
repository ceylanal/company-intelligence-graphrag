"""Unit tests for Retrieval Benchmark Engine, caching, failure analysis, and CLI commands (Day 29)."""

from pathlib import Path

from company_graphrag.evals import (
    DifficultyLevel,
    EvaluationSample,
    QuestionType,
    RetrievalBenchmarkEngine,
)
from company_graphrag.retrieval import HybridRetriever, RetrievalMode


def test_retrieval_benchmark_sample_run() -> None:
    """Test running retrieval benchmark on a single evaluation sample."""
    sample = EvaluationSample(
        id="test_001",
        question="ASELSAN'ın Genel Müdürü kimdir?",
        question_type=QuestionType.SINGLE_HOP_FACT,
        company="Aselsan",
        expected_answer="Ahmet Akyol",
        source_file="ASELS__2024__annual_report__tr.pdf",
        source_pages=[34],
        source_chunk_ids=["chk_asels_34"],
        expected_entities=["ASELSAN", "Ahmet Akyol"],
        expected_relations=["MANAGED_BY"],
        answerable=True,
    )

    retriever = HybridRetriever()
    engine = RetrievalBenchmarkEngine(hybrid_retriever=retriever)
    res = engine.run_sample_benchmark(sample, mode=RetrievalMode.HYBRID)

    assert res.sample_id == "test_001"
    assert res.retrieval_mode == "hybrid"
    assert res.latency_ms > 0
    assert res.mrr >= 0.0


def test_retrieval_benchmark_unanswerable() -> None:
    """Test retrieval benchmark handling of unanswerable queries."""
    sample = EvaluationSample(
        id="test_unans",
        question="ASELSAN mars uzay mekiği projesi bütçesi ne kadardır?",
        question_type=QuestionType.UNANSWERABLE,
        company="Aselsan",
        expected_answer="Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli kanıt bulunamadı.",
        source_file="OUT_OF_DOMAIN.pdf",
        source_pages=[],
        source_chunk_ids=[],
        answerable=False,
        metadata={"unanswerable_reason": "Out of domain"},
    )

    retriever = HybridRetriever()
    engine = RetrievalBenchmarkEngine(hybrid_retriever=retriever)
    res = engine.run_sample_benchmark(sample, mode=RetrievalMode.AUTO)

    assert res.mrr == 1.0
    assert res.recall_at_1 == 1.0
    assert res.is_failed_sample is False


def test_retrieval_benchmark_export_artifacts(tmp_path: Path) -> None:
    """Test exporting benchmark artifact files."""
    sample = EvaluationSample(
        id="test_exp",
        question="Akbank 2024 cirosu nedir?",
        question_type=QuestionType.SINGLE_HOP_FACT,
        company="Akbank",
        expected_answer="Akbank 2024 cirosu artmıştır.",
        source_file="AKBNK__2024__annual_report__tr.pdf",
        source_pages=[10],
        source_chunk_ids=["chk_akbnk_10"],
        difficulty=DifficultyLevel.EASY,
    )

    retriever = HybridRetriever()
    engine = RetrievalBenchmarkEngine(hybrid_retriever=retriever)
    res = engine.run_sample_benchmark(sample, mode=RetrievalMode.HYBRID)

    dev_summary = engine.aggregate_mode_summary([res], mode="hybrid", split="dev")
    test_summary = engine.aggregate_mode_summary([res], mode="hybrid", split="test")
    failures = engine.extract_failure_examples([sample], [res])

    res_p, sum_p, rep_p, fail_p = engine.export_benchmark_artifacts(
        [res], {"hybrid": dev_summary}, {"hybrid": test_summary}, failures, output_dir=tmp_path
    )

    assert res_p.exists()
    assert sum_p.exists()
    assert rep_p.exists()
    assert fail_p.exists()
