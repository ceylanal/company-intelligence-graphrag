"""Unit and evaluation tests for GraphRAG Grounded Answer Generation (Day 25)."""

from company_graphrag.graph.generation import GraphRAGContextBuilder, GraphRAGGenerator, LLMClient
from company_graphrag.retrieval import HybridSearchResponse, HybridSearchResultItem, RetrievalMode


def test_context_builder_packaging() -> None:
    """Test formatting vector hits and graph paths into context packages."""
    builder = GraphRAGContextBuilder()
    hybrid_res = HybridSearchResponse(
        query="ASELSAN ciro ve ürünler",
        mode_requested=RetrievalMode.HYBRID,
        mode_executed=RetrievalMode.HYBRID,
        results=[
            HybridSearchResultItem(
                id="chunk_1",
                text="Aselsan 2024 yılında 80 Milyar TL ciro elde etti.",
                score=0.95,
                source_retriever="vector",
                company="Aselsan",
                ticker="ASELS",
                year=2024,
                source_file="ASELS__2024.pdf",
                page_number=14,
                chunk_id="chunk_1",
            ),
            HybridSearchResultItem(
                id="path_1",
                text="Graph Path: (ASELSAN) ➔ PRODUCES ➔ (ASELFLIR-500)",
                score=0.90,
                source_retriever="graph",
                ticker="ASELS",
                year=2024,
                source_file="ASELS__2024.pdf",
                page_number=18,
                chunk_id="chunk_2",
                graph_path_summary="(ASELSAN) ➔ PRODUCES ➔ (ASELFLIR-500)",
            ),
        ],
        total_results=2,
    )

    context_str, citations, rels = builder.build_context_package(hybrid_res)

    assert "[Source 1]" in context_str
    assert "[Source 2]" in context_str
    assert len(citations) == 2
    assert citations[0].source_file == "ASELS__2024.pdf"
    assert citations[0].page_number == 14
    assert len(rels) == 1
    assert rels[0] == "(ASELSAN) ➔ PRODUCES ➔ (ASELFLIR-500)"


def test_generator_grounded_answer() -> None:
    """Test generating grounded answer with full citations and relationship tracking."""
    llm = LLMClient(mock_mode=True)
    generator = GraphRAGGenerator(llm_client=llm)

    hybrid_res = HybridSearchResponse(
        query="ASELSAN ürünleri",
        mode_requested=RetrievalMode.HYBRID,
        mode_executed=RetrievalMode.HYBRID,
        results=[
            HybridSearchResultItem(
                id="chunk_1",
                text="Aselsan elektro-optik sistemler üretmektedir.",
                score=0.95,
                source_retriever="vector",
                company="Aselsan",
                ticker="ASELS",
                year=2024,
                source_file="ASELS__2024.pdf",
                page_number=12,
                chunk_id="chk_12",
            )
        ],
        total_results=1,
    )

    ans = generator.generate_answer("ASELSAN ürünleri", hybrid_response=hybrid_res)

    assert ans.insufficient_context is False
    assert len(ans.citations) == 1
    assert ans.citations[0].ticker == "ASELS"
    assert ans.citations[0].page_number == 12
    assert ans.citations[0].chunk_id == "chk_12"
    assert "[Source 1]" in ans.detailed_explanation


def test_generator_insufficient_context() -> None:
    """Test safe handling when query is ungrounded or out of domain."""
    llm = LLMClient(mock_mode=True)
    generator = GraphRAGGenerator(llm_client=llm)

    hybrid_res = HybridSearchResponse(
        query="mars uzay projesi",
        mode_requested=RetrievalMode.AUTO,
        mode_executed=RetrievalMode.VECTOR_ONLY,
        results=[
            HybridSearchResultItem(
                id="chunk_1",
                text="Şirketimiz savunma elektroniği alanında çalışmaktadır.",
                score=0.30,
                source_retriever="vector",
                source_file="ASELS.pdf",
                page_number=1,
                chunk_id="c1",
            )
        ],
    )

    ans = generator.generate_answer("mars uzay projesi", hybrid_response=hybrid_res)

    assert ans.insufficient_context is True
    assert ans.confidence_level == "NONE"
    assert "yeterli kanıt bulunamadı" in ans.short_answer.lower()
