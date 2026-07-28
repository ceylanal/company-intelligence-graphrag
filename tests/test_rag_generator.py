"""Unit tests for Grounded RAG Generator and citation validation (Day 13)."""

from company_graphrag.embeddings import TextEmbeddingEncoder
from company_graphrag.rag.generator import RAGGenerator, extract_citations
from company_graphrag.rag.models import SourceReference
from company_graphrag.retrieval.vector_retriever import VectorRetriever
from company_graphrag.storage import QdrantVectorStore


def create_mock_source(
    num: int, company: str = "Aselsan A.Ş.", ticker: str = "ASELS", year: int = 2024
) -> SourceReference:
    return SourceReference(
        source_number=num,
        chunk_id=f"chk_00{num}",
        company=company,
        ticker=ticker,
        year=year,
        report_type="annual_report",
        page_number=10 * num,
        source_file=f"{ticker}__{year}__annual_report__tr.pdf",
        text=f"{company} {year} yılı performans verileri sayfa {10 * num}.",
        retrieval_score=0.85 - (0.05 * num),
        character_count=50,
    )


def test_extract_citations() -> None:
    """Test citation extraction and filtering of invalid citation numbers."""
    valid_nums = {1, 2, 3}
    text = "Aselsan cirosunu artırmıştır [Source 1]. Akbank müşteri sayısı büyümüştür [Source 2] [Source 99]."

    citations = extract_citations(text, valid_nums)
    assert citations == [1, 2]  # [Source 99] is invalid and filtered out!


def test_single_source_answer() -> None:
    """Scenario 1: Single-source grounded answer generation."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    generator = RAGGenerator(retriever=retriever, mock_mode=True)

    result = generator.generate("ASELSAN cirosu", top_k=1, ticker="ASELS")

    assert not result.insufficient_context
    assert result.used_source_count >= 1
    assert result.answer != ""
    assert "[Source 1]" in result.answer
    generator.close()


def test_multi_source_answer() -> None:
    """Scenario 2: Multi-source grounded answer generation."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    generator = RAGGenerator(retriever=retriever, mock_mode=True)

    result = generator.generate("ASELSAN ve Akbank performansları", top_k=2)

    assert not result.insufficient_context
    assert result.used_source_count >= 1
    assert result.answer != ""
    generator.close()


def test_insufficient_context_answer() -> None:
    """Scenario 3: Insufficient context handling."""
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True))
    generator = RAGGenerator(retriever=retriever, mock_mode=True)

    # Search for something non-existent with strict filter returning zero hits
    result = generator.generate("Nonexistent random query", ticker="NONEXISTENT_TICKER")

    assert result.insufficient_context
    assert result.used_source_count == 0
    assert result.answer == "Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli bilgi bulunamadı."
    assert result.citations == []
    generator.close()


def test_hallucination_prevention() -> None:
    """Scenario 4: Verify prompt structure enforces grounding and prevents ungrounded claims."""
    from company_graphrag.rag.prompts import GROUNDED_RAG_SYSTEM_PROMPT

    assert "Kendi genel bilgin veya dışarıdan edindiğin hiçbir bilgiyi katma" in GROUNDED_RAG_SYSTEM_PROMPT
    assert "Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli bilgi bulunamadı" in GROUNDED_RAG_SYSTEM_PROMPT
    assert "[Source 1]" in GROUNDED_RAG_SYSTEM_PROMPT


def test_invalid_citation_filtering() -> None:
    """Scenario 5: Verify invalid citation numbers in LLM text are filtered out."""
    valid_nums = {1, 2}
    llm_output = "ASELSAN 2024 cirosu 120 Milyar TL'ye ulaştı [Source 1]. Şirket ayrıca 2030 hedefi koydu [Source 55]."

    citations = extract_citations(llm_output, valid_nums)
    assert citations == [1]  # 55 is excluded


def test_llm_connection_error_fallback() -> None:
    """Scenario 6: Verify LLM connection error falls back cleanly without crashing."""
    store = QdrantVectorStore(path="data/vector_store/qdrant_db")
    retriever = VectorRetriever(encoder=TextEmbeddingEncoder(mock=True), store=store)

    # Set external LLM mode with invalid key/url to trigger error fallback
    generator = RAGGenerator(retriever=retriever, llm_provider="openai", api_key="invalid_key", mock_mode=False)

    result = generator.generate("ASELSAN 2024", top_k=1, ticker="ASELS")

    assert result.answer != ""
    assert result.used_source_count >= 1
    generator.close()
