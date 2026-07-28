"""Query Transformer for Query Rewriting, Entity Detection, and Multi-Query Expansion."""

import re
import time

import structlog

from company_graphrag.retrieval.models import QueryPlan

logger = structlog.get_logger(__name__)

# BIST 10 Company Metadata & Alias Dictionary
COMPANY_ALIAS_MAP: dict[str, dict[str, str | list[str]]] = {
    "AKBNK": {"name": "Akbank T.A.Ş.", "aliases": ["akbank", "ak bank", "akb"]},
    "ARCLK": {"name": "Arçelik A.Ş.", "aliases": ["arçelik", "arcelik", "arc"]},
    "ASELS": {"name": "Aselsan Elektronik Sanayi ve Ticaret A.Ş.", "aliases": ["aselsan", "asels"]},
    "FROTO": {"name": "Ford Otomotiv Sanayi A.Ş.", "aliases": ["ford otosan", "ford", "froto"]},
    "KCHOL": {"name": "Koç Holding A.Ş.", "aliases": ["koç holding", "koc holding", "kchol"]},
    "MGROS": {"name": "Migros Ticaret A.Ş.", "aliases": ["migros", "mgros"]},
    "SISE": {"name": "Türkiye Şişe ve Cam Fabrikaları A.Ş.", "aliases": ["şişecam", "sisecam", "sise"]},
    "TCELL": {"name": "Turkcell İletişim Hizmetleri A.Ş.", "aliases": ["turkcell", "tcell"]},
    "THYAO": {"name": "Türk Hava Yolları A.O.", "aliases": ["thy", "türk hava yolları", "turk hava yollari", "thyao"]},
    "TUPRS": {"name": "Türkiye Petrol Rafinerileri A.Ş.", "aliases": ["tüpraş", "tupras", "tuprs"]},
}


def normalize_query_text(text: str) -> str:
    """Normalize query text preserving Turkish characters and removing extra whitespace."""
    if not text:
        return ""
    norm = text.strip()
    norm = re.sub(r"\s+", " ", norm)
    return norm


def detect_company_entity(norm_text: str) -> tuple[str | None, str | None]:
    """Detect company name and ticker symbol from normalized query text."""
    lowered = norm_text.lower()
    for ticker, info in COMPANY_ALIAS_MAP.items():
        aliases = info["aliases"]
        assert isinstance(aliases, list)
        for alias in aliases:
            # Word boundary regex match for short tickers/aliases
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, lowered):
                return str(info["name"]), ticker
    return None, None


def detect_year_entity(norm_text: str) -> tuple[int | None, str | None]:
    """Detect explicit or relative year from query text."""
    lowered = norm_text.lower()

    # Relative Year Matching
    if any(p in lowered for p in ["geçen yıl", "geçen sene", "önceki yıl", "geçen faaliyet dönemi"]):
        return 2024, "Relative date expression detected: 'geçen yıl/sene' mapped to year 2024."
    if any(p in lowered for p in ["bu yıl", "bu sene", "son dönem"]):
        return 2025, "Relative date expression detected: 'bu yıl/son dönem' mapped to year 2025."

    # Explicit Year Matching (2020-2029)
    match = re.search(r"\b(202[0-9])\b", norm_text)
    if match:
        return int(match.group(1)), None

    return None, None


class QueryTransformer:
    """Rule-Based and LLM-assisted Query Transformer and Multi-Query Generator."""

    def __init__(self, use_llm_fallback: bool = True) -> None:
        self.use_llm_fallback = use_llm_fallback

    def transform(
        self,
        query: str,
        explicit_ticker: str | list[str] | None = None,
        explicit_year: int | list[int] | None = None,
        max_expanded_queries: int = 3,
    ) -> QueryPlan:
        """Transform user query, extract entities, and generate query variations."""
        start_time = time.time()
        warnings: list[str] = []

        if not query or not query.strip():
            return QueryPlan(
                original_query="",
                normalized_query="",
                rewritten_query="",
                expanded_queries=[],
                warnings=["Empty query input provided."],
            )

        norm_query = normalize_query_text(query)

        # Out-of-Domain / Unanswerable Query Detection
        is_ood = False
        ood_keywords = [
            "spacex",
            "apple",
            "iphone",
            "mars projesi",
            "tesla",
            "microsoft",
            "amazon",
            "google",
            "facebook",
        ]
        if any(kw in norm_query.lower() for kw in ood_keywords):
            is_ood = True
            warnings.append("Out-of-domain query detected (not present in BIST 10 company dataset).")

        match_future_year = re.search(r"\b(20[2-9][6-9]|20[3-9][0-9])\b", norm_query)
        if match_future_year:
            is_ood = True
            warnings.append(f"Out-of-scope year detected ({match_future_year.group(1)} > 2025 dataset limit).")

        # 1. Entity Detection
        det_company, det_ticker = detect_company_entity(norm_query)
        det_year, relative_warning = detect_year_entity(norm_query)
        if relative_warning:
            warnings.append(relative_warning)

        # Priority Rule: Explicit CLI filters override auto-detected filters!
        final_ticker = explicit_ticker if isinstance(explicit_ticker, str) else det_ticker
        final_year = explicit_year if isinstance(explicit_year, int) else det_year

        # 2. Query Rewriting (Clean Standalone Query)
        company_label = det_company or (final_ticker if final_ticker else "")
        year_label = str(final_year) if final_year else ""

        # Remove noise terms like "iyi miydi", "nasıl", "hakkında ne var"
        clean_text = norm_query
        noise_words = [
            r"\bgeçen yıl\b",
            r"\bgeçen sene\b",
            r"\biyi miydi\b",
            r"\bnasıldı\b",
            r"\bnasıl\b",
            r"\bnedir\b",
            r"\bhakkında\b",
        ]
        for nw in noise_words:
            clean_text = re.sub(nw, "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"[?.,!]", "", clean_text)
        clean_text = normalize_query_text(clean_text)

        parts = [company_label, year_label, clean_text]
        rewritten = " ".join([p for p in parts if p]).strip()
        if not rewritten:
            rewritten = norm_query

        # 3. Multi-Query Expansion (up to max_expanded_queries)
        expanded: list[str] = [rewritten]

        # Query 2: Financial Term Expansion
        fin_query = f"{rewritten} gelir net kâr cirosu operasyonel ve finansal performansı"
        if fin_query not in expanded:
            expanded.append(normalize_query_text(fin_query))

        # Query 3: Bilingual / Alternative Term Query
        alt_query = f"{rewritten} revenue net profit investment performance"
        if alt_query not in expanded:
            expanded.append(normalize_query_text(alt_query))

        expanded = expanded[:max_expanded_queries]

        duration = round((time.time() - start_time) * 1000, 2)
        logger.info(
            "QueryTransformer generated plan",
            original=query,
            rewritten=rewritten,
            detected_ticker=det_ticker,
            detected_year=det_year,
            expanded_count=len(expanded),
            duration_ms=duration,
        )

        return QueryPlan(
            original_query=query,
            normalized_query=norm_query,
            rewritten_query=rewritten,
            expanded_queries=expanded,
            detected_company=det_company,
            detected_ticker=det_ticker,
            detected_year=det_year,
            detected_report_type="annual_report",
            is_out_of_domain=is_ood,
            warnings=warnings,
        )
