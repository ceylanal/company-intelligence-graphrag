"""Unit tests for End-to-End Vector RAG Pipeline (Day 14)."""

import json

from typer.testing import CliRunner

from company_graphrag.cli import app
from company_graphrag.embeddings import TextEmbeddingEncoder
from company_graphrag.rag.generator import RAGGenerator
from company_graphrag.rag.pipeline import VectorRAGPipeline
from company_graphrag.retrieval.vector_retriever import VectorRetriever
from company_graphrag.storage import QdrantVectorStore

runner = CliRunner()


def test_pipeline_successful_end_to_end() -> None:
    """Scenario 1: Successful end-to-end RAG pipeline execution."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("ASELSAN 2024 cirosu ne kadar?", top_k=3, ticker="ASELS")

    assert res.query == "ASELSAN 2024 cirosu ne kadar?"
    assert not res.insufficient_context
    assert res.used_source_count >= 1
    assert res.execution_time_ms > 0.0
    assert "retrieval_ms" in res.stage_timings_ms
    assert "generation_ms" in res.stage_timings_ms
    pipeline.close()


def test_pipeline_filtered_query() -> None:
    """Scenario 2: Filtered query execution."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("Mobil bankacılık büyümesi", ticker="AKBNK", year=2024)

    assert not res.insufficient_context
    for src in res.sources:
        assert src.ticker == "AKBNK"
        assert src.year == 2024
    pipeline.close()


def test_pipeline_no_results() -> None:
    """Scenario 3: No retrieval results found."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("Bilinmeyen sorgu", ticker="NON_EXISTENT_COMPANY")

    assert res.insufficient_context
    assert res.retrieved_count == 0
    assert res.used_source_count == 0
    assert "No relevant sources found" in res.warnings[0]
    pipeline.close()


def test_pipeline_insufficient_context() -> None:
    """Scenario 4: Empty query / insufficient context."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("   \n  ")

    assert res.insufficient_context
    assert res.used_source_count == 0
    assert "Empty query" in res.warnings[0]
    pipeline.close()


def test_pipeline_invalid_citation_warning() -> None:
    """Scenario 5: Warning generated when LLM output contains ungrounded citation."""
    store = QdrantVectorStore(path="data/vector_store/qdrant_db")
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True), store=store)

    class MockHallucinatingGenerator(RAGGenerator):
        def generate(self, *args, **kwargs):
            from company_graphrag.rag.models import RAGAnswer, SourceReference

            src = SourceReference(
                source_number=1,
                chunk_id="c1",
                company="Aselsan",
                ticker="ASELS",
                year=2024,
                report_type="annual_report",
                page_number=1,
                source_file="ASELS.pdf",
                text="Aselsan ciro",
                retrieval_score=0.9,
                character_count=12,
            )
            return RAGAnswer(
                query="c",
                answer="ASELSAN cirosu 120 Milyar TL [Source 1]. Ayrıca [Source 99] uydurma.",
                citations=[1],
                sources=[src],
                used_source_count=1,
                insufficient_context=False,
                execution_time_ms=10.0,
            )

    pipeline = VectorRAGPipeline(retriever=retriever, generator=MockHallucinatingGenerator(retriever=retriever))
    res = pipeline.run("ASELSAN ciro", top_k=1)

    assert any("invalid citation" in w for w in res.warnings)
    pipeline.close()


def test_pipeline_retriever_error_handling() -> None:
    """Scenario 6: Retriever error gracefully captured into warnings."""

    class BrokenRetriever(VectorRetriever):
        def retrieve(self, *args, **kwargs):
            raise RuntimeError("Qdrant database connection timeout")

    pipeline = VectorRAGPipeline(retriever=BrokenRetriever())
    res = pipeline.run("ASELSAN ciro")

    assert res.insufficient_context
    assert any("Retrieval error" in w for w in res.warnings)
    pipeline.close()


def test_pipeline_llm_error_handling() -> None:
    """Scenario 7: LLM timeout error falls back gracefully."""
    store = QdrantVectorStore(path="data/vector_store/qdrant_db")
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True), store=store)
    generator = RAGGenerator(retriever=retriever, llm_provider="openai", api_key="invalid", mock_mode=False)

    pipeline = VectorRAGPipeline(retriever=retriever, generator=generator)
    res = pipeline.run("ASELSAN ciro", top_k=1, ticker="ASELS")

    assert not res.insufficient_context
    assert res.used_source_count >= 1
    pipeline.close()


def test_cli_ask_json_output() -> None:
    """Scenario 8: CLI ask command --output json verification."""
    result = runner.invoke(
        app,
        [
            "ask",
            "ASELSAN'ın 2024 gelir ve kârlılık performansı nasıldı?",
            "--ticker",
            "ASELS",
            "--year",
            "2024",
            "--top-k",
            "2",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    json_start = result.output.find("{")
    assert json_start != -1
    data = json.loads(result.output[json_start:])
    assert "query" in data
    assert "answer" in data
    assert "citations" in data
    assert "stage_timings_ms" in data


def test_pipeline_stage_timings() -> None:
    """Scenario 9: Stage timing metrics verification."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("THY yolcu kapasitesi", ticker="THYAO")

    assert "retrieval_ms" in res.stage_timings_ms
    assert "context_ms" in res.stage_timings_ms
    assert "generation_ms" in res.stage_timings_ms
    assert "total_ms" in res.stage_timings_ms
    assert res.stage_timings_ms["total_ms"] >= res.stage_timings_ms["retrieval_ms"]
    pipeline.close()


def test_pipeline_with_reranking() -> None:
    """Scenario 10: RAG pipeline execution with reranking enabled."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("ASELSAN 2024 gelir ve kârlılık", top_k=3, candidate_k=10, use_reranking=True, ticker="ASELS")

    assert not res.insufficient_context
    assert "reranking_ms" in res.stage_timings_ms
    assert res.used_source_count >= 1
    pipeline.close()


def test_pipeline_query_rewrite_and_multi_query() -> None:
    """Scenario 11: End-to-End RAG pipeline execution with Query Rewrite and Multi-Query RRF Fusion."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run(
        "THY geçen sene iyi miydi?",
        top_k=3,
        use_query_rewrite=True,
        use_multi_query=True,
        use_reranking=True,
    )

    assert not res.insufficient_context
    assert res.query_plan is not None
    assert res.query_plan.detected_ticker == "THYAO"
    assert res.query_plan.detected_year == 2024
    assert "rewrite_ms" in res.stage_timings_ms
    assert "reranking_ms" in res.stage_timings_ms
    pipeline.close()
