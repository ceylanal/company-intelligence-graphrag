"""Regression test suite for Vector RAG pipeline features and edge cases (Day 17)."""

import json

from typer.testing import CliRunner

from company_graphrag.cli import app
from company_graphrag.embeddings import TextEmbeddingEncoder
from company_graphrag.rag.pipeline import VectorRAGPipeline
from company_graphrag.retrieval.vector_retriever import VectorRetriever

runner = CliRunner()


def test_regression_company_filter() -> None:
    """Test company filter retention."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("gelir ve kârlılık", company="Aselsan Elektronik Sanayi ve Ticaret A.Ş.")
    assert not res.insufficient_context
    pipeline.close()


def test_regression_ticker_filter() -> None:
    """Test ticker filter retention."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("havacılık gelirleri", ticker="THYAO")
    assert not res.insufficient_context
    pipeline.close()


def test_regression_year_filter() -> None:
    """Test year filter retention."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("finansal sonuçlar", year=2024)
    assert not res.insufficient_context
    pipeline.close()


def test_regression_report_type_filter() -> None:
    """Test report_type filter retention."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("faaliyet dönemi", report_type="annual_report")
    assert not res.insufficient_context
    pipeline.close()


def test_regression_query_rewrite_off() -> None:
    """Test pipeline execution when query rewrite is disabled."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("ASELSAN 2024 cirosu", use_query_rewrite=False)
    assert not res.insufficient_context
    assert "rewrite_ms" not in res.stage_timings_ms
    pipeline.close()


def test_regression_multi_query_off() -> None:
    """Test pipeline execution when multi-query is disabled."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("Turkcell 5G yatırımları", use_multi_query=False)
    assert not res.insufficient_context
    pipeline.close()


def test_regression_rerank_off() -> None:
    """Test pipeline execution when reranking is disabled."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("Şişecam cam üretimi", use_reranking=False)
    assert not res.insufficient_context
    assert "reranking_ms" not in res.stage_timings_ms
    pipeline.close()


def test_regression_json_output() -> None:
    """Test CLI ask command with --output json option."""
    result = runner.invoke(
        app,
        ["ask", "AKBNK 2024 sermaye oranı", "--ticker", "AKBNK", "--output", "json"],
    )
    assert result.exit_code == 0
    start_idx = result.output.find("{")
    assert start_idx != -1
    data = json.loads(result.output[start_idx:])
    assert "query" in data
    assert "answer" in data


def test_regression_empty_query() -> None:
    """Test empty query input handling."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    res = pipeline.run("")
    assert res.insufficient_context
    assert "provided" in res.warnings[0].lower()
    pipeline.close()


def test_regression_qdrant_fallback() -> None:
    """Test fallback when Qdrant REST connection is unavailable."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    res = retriever.retrieve("Tüpraş kapasite", top_k=2)

    assert res.total_hits > 0
    retriever.close()


def test_regression_llm_fallback() -> None:
    """Test fallback when external LLM API encounters error."""
    from company_graphrag.rag.generator import RAGGenerator

    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    generator = RAGGenerator(retriever=retriever, mock_mode=True)

    ans = generator.generate("ASELSAN 2024 kârı", ticker="ASELS")
    assert ans.answer != ""
    assert len(ans.citations) > 0
    generator.close()


def test_regression_insufficient_context() -> None:
    """Test unanswerable question context detection."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    pipeline = VectorRAGPipeline(retriever=retriever)

    # Filtering by invalid ticker guarantees 0 hits!
    res = pipeline.run("SpaceX 2024 Mars bütçesi", ticker="SPACEX")
    assert res.insufficient_context
    assert "yeterli bilgi bulunamadı" in res.answer.lower()
    pipeline.close()
