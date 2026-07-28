"""Unit tests for QueryTransformer, entity detection, and multi-query expansion (Day 16)."""

from company_graphrag.retrieval.query_transformer import QueryTransformer, detect_company_entity, detect_year_entity


def test_detect_company_entity() -> None:
    """Test company name and stock ticker extraction from alias dictionary."""
    comp1, tick1 = detect_company_entity("THY geçen sene net kârı nasıldı?")
    assert tick1 == "THYAO"
    assert comp1 == "Türk Hava Yolları A.O."

    comp2, tick2 = detect_company_entity("Arçelik 2024 sürdürülebilirlik raporu")
    assert tick2 == "ARCLK"

    comp3, tick3 = detect_company_entity("Rastgele genel bir finans sorusu")
    assert tick3 is None
    assert comp3 is None


def test_detect_year_entity() -> None:
    """Test explicit year and relative date expressions detection."""
    y1, w1 = detect_year_entity("ASELSAN 2024 cirosu")
    assert y1 == 2024
    assert w1 is None

    y2, w2 = detect_year_entity("THY geçen yıl iyi miydi?")
    assert y2 == 2024
    assert w2 is not None
    assert "geçen yıl" in w2

    y3, w3 = detect_year_entity("Ford Otosan bu yıl yatırımları")
    assert y3 == 2025
    assert w3 is not None


def test_clear_query_transformation() -> None:
    """Scenario 1: Clear and well-formed query transformation."""
    transformer = QueryTransformer()
    plan = transformer.transform("ASELSAN 2024 yılı ciro ve net kâr rakamları")

    assert plan.detected_ticker == "ASELS"
    assert plan.detected_year == 2024
    assert plan.rewritten_query != ""
    assert len(plan.expanded_queries) == 3


def test_vague_query_transformation() -> None:
    """Scenario 2: Vague and short query expansion."""
    transformer = QueryTransformer()
    plan = transformer.transform("THY geçen sene iyi miydi?")

    assert plan.detected_ticker == "THYAO"
    assert plan.detected_year == 2024
    assert "Türk Hava Yolları" in plan.rewritten_query or "THYAO" in plan.rewritten_query
    assert any("revenue" in q for q in plan.expanded_queries)


def test_company_alias_matching() -> None:
    """Scenario 3: Company alias matching (e.g. Sisecam -> SISE)."""
    transformer = QueryTransformer()
    plan = transformer.transform("sisecam fırın yatırımları")

    assert plan.detected_ticker == "SISE"


def test_ticker_matching() -> None:
    """Scenario 4: Stock ticker matching (e.g. TCELL -> Turkcell)."""
    transformer = QueryTransformer()
    plan = transformer.transform("TCELL 5G abone sayısı")

    assert plan.detected_ticker == "TCELL"


def test_financial_terms_expansion() -> None:
    """Scenario 5: Multi-query expansion includes financial and English terms."""
    transformer = QueryTransformer()
    plan = transformer.transform("Akbank dijital müşteri sayısı", max_expanded_queries=3)

    assert len(plan.expanded_queries) == 3
    assert any("net kâr" in q for q in plan.expanded_queries)
    assert any("revenue" in q for q in plan.expanded_queries)


def test_cli_filter_override() -> None:
    """Scenario 8: Explicit CLI filter overrides auto-detected filter."""
    transformer = QueryTransformer()

    # Query mentions 2024, but explicit CLI filter specifies year=2023!
    plan = transformer.transform(
        query="ASELSAN 2024 bilançosu",
        explicit_ticker="AKBNK",
        explicit_year=2023,
    )

    assert plan.detected_ticker == "ASELS"
    assert plan.detected_year == 2024


def test_empty_query_fallback() -> None:
    """Scenario 9: Empty query input returns safe empty plan with warning."""
    transformer = QueryTransformer()
    plan = transformer.transform("")

    assert plan.original_query == ""
    assert plan.expanded_queries == []
    assert len(plan.warnings) > 0
