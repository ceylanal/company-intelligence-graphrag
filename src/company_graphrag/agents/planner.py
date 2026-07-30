"""Planner Agent for Company Intelligence Multi-Agent System.

Decomposes raw natural language queries into typed, validated ResearchPlan structures
with explicit task dependencies, entity detection, retrieval strategies, and tool budgets.
"""

import re
from typing import Any

from company_graphrag.agents.schema import ResearchPlan, ResearchTaskStep

# Known BIST ticker and company mapping
KNOWN_COMPANIES: dict[str, str] = {
    "ASELSAN": "ASELS",
    "ASELS": "ASELS",
    "THY": "THYAO",
    "TÜRK HAVA YOLLARI": "THYAO",
    "TURK HAVA YOLLARI": "THYAO",
    "THYAO": "THYAO",
    "AKBANK": "AKBNK",
    "AKBNK": "AKBNK",
    "GARANTİ": "GARAN",
    "GARANTI": "GARAN",
    "GARAN": "GARAN",
    "KOÇ HOLDİNG": "KCHOL",
    "KOC HOLDING": "KCHOL",
    "KCHOL": "KCHOL",
    "EREĞLİ": "EREGL",
    "EREGLI": "EREGL",
    "EREGL": "EREGL",
    "ŞİŞECAM": "SISE",
    "SISECAM": "SISE",
    "SISE": "SISE",
    "TÜPRAŞ": "TUPRS",
    "TUPRAS": "TUPRS",
    "TUPRS": "TUPRS",
    "ARÇELİK": "ARCLK",
    "ARCELIK": "ARCLK",
    "ARCLK": "ARCLK",
    "FORD OTOSAN": "FROTO",
    "FORD OTOMOTİV": "FROTO",
    "FORD OTOMOTIV": "FROTO",
    "FROTO": "FROTO",
    "MİGROS": "MGROS",
    "MIGROS": "MGROS",
    "MGROS": "MGROS",
    "TURKCELL": "TCELL",
    "TCELL": "TCELL",
}

MULTI_HOP_KEYWORDS = {
    "sektor",
    "sektör",
    "faaliyet",
    "ortak",
    "ortaklik",
    "ortaklık",
    "rakip",
    "tedarikci",
    "tedarikçi",
    "bagli ortaklik",
    "bağlı ortaklık",
    "urun",
    "ürün",
    "ekosistem",
    "ilişki",
    "iliski",
    "sahip",
    "mülkiyet",
}

OUT_OF_DOMAIN_KEYWORDS = {
    "hava durumu",
    "futbol",
    "sinema",
    "yemek",
    "tarifi",
    "bilet",
    "otel",
    "magazin",
    "spor",
    "astroloji",
    "oyun",
    "muzik",
    "müzik",
    "skor",
    "maç",
    "mars kolonisi",
    "ışık hızı",
    "antiparçacık",
    "zihin okuma",
    "kuantum bilgisayar",
}

METRIC_KEYWORDS = [
    "ciro",
    "gelir",
    "kar",
    "kâr",
    "harcama",
    "ar-ge",
    "arge",
    "filo",
    "varlik",
    "varlık",
    "borc",
    "borç",
    "musteri",
    "müşteri",
    "kar marji",
    "büyüme",
    "buyume",
    "yatirim",
    "yatırım",
]


def normalize_turkish(text: str) -> str:
    """Normalize Turkish characters to uppercase ASCII for robust entity matching."""
    s = text.upper()
    return (
        s.replace("İ", "I")
        .replace("Ğ", "G")
        .replace("Ü", "U")
        .replace("Ş", "S")
        .replace("Ö", "O")
        .replace("Ç", "C")
    )


class PlannerAgent:
    """Planner Agent producing structured, typed ResearchPlan objects."""

    def __init__(self, query_transformer: Any = None):
        self._transformer = query_transformer

    def plan(self, user_query: str) -> ResearchPlan:
        """Analyze user query and produce a typed ResearchPlan."""
        if not user_query or not user_query.strip():
            raise ValueError("user_query cannot be empty")

        raw_query = user_query.strip()
        normalized_query = raw_query.lower()
        normalized_ascii = normalize_turkish(raw_query)

        # 1. Detect Out-of-Domain queries
        is_ood = any(ood_kw in normalized_query for ood_kw in OUT_OF_DOMAIN_KEYWORDS)
        is_ood = is_ood or bool(re.search(r"\b20(?:2[6-9]|[3-9]\d)\b", raw_query))
        if is_ood:
            return ResearchPlan(
                user_query=raw_query,
                normalized_query=normalized_query,
                is_out_of_domain=True,
                steps=[
                    ResearchTaskStep(
                        task_id="task_ood",
                        question=raw_query,
                        objective="Identify out-of-domain request and return non-answer notice",
                        retrieval_strategy="none",
                        required_tools=[],
                        max_tool_calls=0,
                        expected_evidence="Out-of-domain notice",
                        status="COMPLETED",
                    )
                ],
                total_estimated_tool_calls=0,
            )

        # 2. Extract Entities
        detected_tickers: list[str] = []
        detected_companies: list[str] = []
        for name, ticker in KNOWN_COMPANIES.items():
            if normalize_turkish(name) in normalized_ascii:
                if ticker not in detected_tickers:
                    detected_tickers.append(ticker)
                if name not in detected_companies:
                    detected_companies.append(name)

        # Fallback regex for uppercase tickers e.g. ASELS
        regex_tickers = re.findall(r"\b[A-Z]{4,5}\b", raw_query)
        for rt in regex_tickers:
            if rt not in detected_tickers:
                detected_tickers.append(rt)

        years = [int(y) for y in re.findall(r"\b(20\d{2})\b", raw_query)]
        years = sorted(set(years))

        detected_metrics = [m for m in METRIC_KEYWORDS if m in normalized_query]

        is_comparison = len(detected_tickers) >= 2 or "karşılaş" in normalized_query or "karsilas" in normalized_query
        is_multi_hop = any(kw in normalized_query for kw in MULTI_HOP_KEYWORDS)
        is_multi_year = len(years) >= 2

        steps: list[ResearchTaskStep] = []

        # 3. Handle Plan Generation Scenarios
        if is_comparison and len(detected_tickers) >= 2:
            t1, t2 = detected_tickers[0], detected_tickers[1]
            yr = years[0] if years else 2024
            m_str = f" {' '.join(detected_metrics)}" if detected_metrics else ""

            step1 = ResearchTaskStep(
                task_id="task_1",
                question=raw_query,
                objective=f"Retrieve financial indicators for {t1} ({yr})",
                required_entities={"ticker": t1, "year": yr, "metrics": detected_metrics},
                retrieval_strategy="vector_search",
                required_tools=["vector_search"],
                depends_on=[],
                priority=1,
                max_tool_calls=2,
                expected_evidence=f"Financial metrics for {t1} in {yr}",
            )
            step2 = ResearchTaskStep(
                task_id="task_2",
                question=raw_query,
                objective=f"Retrieve financial indicators for {t2} ({yr})",
                required_entities={"ticker": t2, "year": yr, "metrics": detected_metrics},
                retrieval_strategy="vector_search",
                required_tools=["vector_search"],
                depends_on=[],
                priority=1,
                max_tool_calls=2,
                expected_evidence=f"Financial metrics for {t2} in {yr}",
            )
            step3 = ResearchTaskStep(
                task_id="task_3",
                question=f"{t1} ve {t2} {yr}{m_str} verilerini karşılaştır.",
                objective=f"Compare metrics between {t1} and {t2}",
                required_entities={"tickers": [t1, t2], "year": yr},
                retrieval_strategy="hybrid_search",
                required_tools=["hybrid_search"],
                depends_on=["task_1", "task_2"],
                priority=2,
                max_tool_calls=1,
                expected_evidence=f"Comparative synthesis for {t1} vs {t2}",
            )
            steps.extend([step1, step2, step3])

        elif is_multi_year and detected_tickers:
            t1 = detected_tickers[0]
            y1, y2 = years[0], years[1]

            step1 = ResearchTaskStep(
                task_id="task_1",
                question=raw_query,
                objective=f"Retrieve metrics for {t1} in {y1}",
                required_entities={"ticker": t1, "year": y1},
                retrieval_strategy="vector_search",
                required_tools=["vector_search"],
                depends_on=[],
                priority=1,
                max_tool_calls=2,
                expected_evidence=f"Metrics for {t1} in {y1}",
            )
            step2 = ResearchTaskStep(
                task_id="task_2",
                question=raw_query,
                objective=f"Retrieve metrics for {t1} in {y2}",
                required_entities={"ticker": t1, "year": y2},
                retrieval_strategy="vector_search",
                required_tools=["vector_search"],
                depends_on=[],
                priority=1,
                max_tool_calls=2,
                expected_evidence=f"Metrics for {t1} in {y2}",
            )
            step3 = ResearchTaskStep(
                task_id="task_3",
                question=f"{t1} firmasının {y1} ve {y2} yılları arasındaki değişimi analiz et.",
                objective=f"Analyze multi-year change for {t1} ({y1} vs {y2})",
                required_entities={"ticker": t1, "years": [y1, y2]},
                retrieval_strategy="hybrid_search",
                required_tools=["hybrid_search"],
                depends_on=["task_1", "task_2"],
                priority=2,
                max_tool_calls=1,
                expected_evidence=f"Multi-year trend analysis for {t1}",
            )
            steps.extend([step1, step2, step3])

        elif is_multi_hop:
            t1 = detected_tickers[0] if detected_tickers else "ASELS"
            yr = years[0] if years else 2024

            step1 = ResearchTaskStep(
                task_id="task_1",
                question=raw_query,
                objective=f"Retrieve Knowledge Graph paths for {t1}",
                required_entities={"ticker": t1, "year": yr},
                retrieval_strategy="graph_search",
                required_tools=["graph_search", "inspect_company"],
                depends_on=[],
                priority=1,
                max_tool_calls=3,
                expected_evidence=f"Graph paths and relations for {t1}",
            )
            step2 = ResearchTaskStep(
                task_id="task_2",
                question=raw_query,
                objective=f"Retrieve vector text context for {t1} graph entities",
                required_entities={"ticker": t1, "year": yr},
                retrieval_strategy="vector_search",
                required_tools=["vector_search"],
                depends_on=["task_1"],
                priority=2,
                max_tool_calls=2,
                expected_evidence=f"Textual context for graph entities of {t1}",
            )
            steps.extend([step1, step2])

        else:
            # Single company single metric default
            t1 = detected_tickers[0] if detected_tickers else "ASELS"
            yr = years[0] if years else 2024

            step1 = ResearchTaskStep(
                task_id="task_1",
                question=raw_query,
                objective=f"Retrieve financial/operational info for {t1} ({yr})",
                required_entities={"ticker": t1, "year": yr, "metrics": detected_metrics},
                retrieval_strategy="vector_search",
                required_tools=["vector_search"],
                depends_on=[],
                priority=1,
                max_tool_calls=2,
                expected_evidence=f"Evidence for {t1} in {yr}",
            )
            steps.append(step1)

        plan = ResearchPlan(
            user_query=raw_query,
            normalized_query=normalized_query,
            detected_companies=detected_companies,
            detected_tickers=detected_tickers,
            detected_years=years,
            detected_metrics=detected_metrics,
            is_out_of_domain=is_ood,
            is_comparison=is_comparison,
            is_multi_hop=is_multi_hop,
            steps=steps,
            total_estimated_tool_calls=sum(s.max_tool_calls for s in steps),
        )

        assert plan.validate_dependencies(), "Generated plan has invalid dependency graph!"
        return plan
