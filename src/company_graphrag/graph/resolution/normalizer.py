"""Type-aware normalization and contextual feature extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from company_graphrag.chunking.chunker import COMPANY_NAME_MAP
from company_graphrag.graph.extraction.models import EntityExtractionRecord
from company_graphrag.graph.models import normalize_id_component
from company_graphrag.graph.resolution.models import EntityContext
from company_graphrag.retrieval.query_transformer import COMPANY_ALIAS_MAP

DEFAULT_COMPANIES_PATH = Path(__file__).parents[4] / "config" / "companies.yaml"

PERSON_TITLE_TOKENS = {
    "bay",
    "bayan",
    "doc",
    "docent",
    "dr",
    "mr",
    "mrs",
    "ms",
    "prof",
    "profesor",
    "sayin",
}

SECTOR_ALIASES = {
    "savunma endustrisi": "savunma_sanayii",
    "savunma sanayi": "savunma_sanayii",
    "savunma sanayii": "savunma_sanayii",
    "defence industry": "savunma_sanayii",
    "defense industry": "savunma_sanayii",
    "telekom": "telekomunikasyon",
    "telecommunications": "telekomunikasyon",
    "telekomunikasyon": "telekomunikasyon",
    "otomotiv endustrisi": "otomotiv",
    "otomotiv sanayi": "otomotiv",
    "otomotiv sanayii": "otomotiv",
}

METRIC_ALIASES = {
    "ciro": "total_revenue",
    "hasilat": "total_revenue",
    "net sales": "total_revenue",
    "revenue": "total_revenue",
    "satis gelirleri": "total_revenue",
    "toplam hasilat": "total_revenue",
    "donem net kari": "net_profit",
    "net income": "net_profit",
    "net kar": "net_profit",
    "net kari": "net_profit",
    "net profit": "net_profit",
    "ebitda": "ebitda",
    "favok": "ebitda",
    "toplam aktifler": "total_assets",
    "total assets": "total_assets",
}


def normalize_words(value: str) -> str:
    """Return space-separated ASCII tokens for comparison."""
    return normalize_id_component(value).replace("_", " ")


def normalize_person_name(value: str) -> str:
    tokens = [token for token in normalize_words(value).split() if token not in PERSON_TITLE_TOKENS]
    return "_".join(tokens)


def normalize_product_name(value: str) -> str:
    return normalize_id_component(value)


def normalize_sector_name(value: str) -> str:
    normalized_words = normalize_words(value)
    return SECTOR_ALIASES.get(normalized_words, normalized_words.replace(" ", "_"))


def normalize_metric_name(value: str) -> str:
    normalized_words = normalize_words(value)
    return METRIC_ALIASES.get(normalized_words, normalized_words.replace(" ", "_"))


def normalize_entity_name(entity_type: str, value: str, properties: dict[str, Any]) -> str:
    """Apply conservative rules appropriate to the entity type."""
    if entity_type == "Company":
        ticker = properties.get("ticker")
        if isinstance(ticker, str) and ticker.strip():
            return ticker.upper().strip()
        return normalize_id_component(value)
    if entity_type == "Person":
        return normalize_person_name(value)
    if entity_type == "Product":
        return normalize_product_name(value)
    if entity_type == "Sector":
        return normalize_sector_name(value)
    if entity_type == "FinancialMetric":
        metric_key = properties.get("metric_key")
        if isinstance(metric_key, str) and metric_key.strip():
            return normalize_metric_name(metric_key)
        return normalize_metric_name(value)
    if entity_type == "Date":
        date_value = properties.get("value")
        return str(date_value or value).upper().strip()
    if entity_type == "Report":
        return str(properties.get("document_id") or value).strip()
    if entity_type == "Chunk":
        return str(properties.get("chunk_id") or value).lower().strip()
    if entity_type == "Event":
        return normalize_id_component(str(properties.get("title") or value))
    return normalize_id_component(value)


@dataclass(frozen=True)
class CompanyIdentity:
    ticker: str
    canonical_name: str
    aliases: tuple[str, ...]


class CompanyRegistry:
    """Combine ticker, legal-name, and known-alias sources already in the repository."""

    def __init__(self, companies_path: Path = DEFAULT_COMPANIES_PATH) -> None:
        self.by_ticker: dict[str, CompanyIdentity] = {}
        aliases_by_ticker: dict[str, set[str]] = {}

        for ticker, legal_name in COMPANY_NAME_MAP.items():
            aliases_by_ticker[ticker] = {ticker, legal_name}
        for ticker, metadata in COMPANY_ALIAS_MAP.items():
            aliases_by_ticker.setdefault(ticker, set()).add(str(metadata["name"]))
            configured_aliases = metadata["aliases"]
            if isinstance(configured_aliases, list):
                aliases_by_ticker[ticker].update(str(alias) for alias in configured_aliases)

        raw_config = yaml.safe_load(Path(companies_path).read_text(encoding="utf-8"))
        for company in raw_config.get("companies", []):
            configured_name = str(company["name"])
            ticker = self._ticker_for_legal_name(configured_name)
            aliases_by_ticker[ticker].add(configured_name)
            aliases_by_ticker[ticker].update(str(alias) for alias in company.get("aliases", []))

        self.alias_to_ticker: dict[str, str] = {}
        for ticker, aliases in aliases_by_ticker.items():
            canonical_name = COMPANY_NAME_MAP[ticker]
            identity = CompanyIdentity(
                ticker=ticker,
                canonical_name=canonical_name,
                aliases=tuple(sorted(aliases)),
            )
            self.by_ticker[ticker] = identity
            for alias in identity.aliases:
                normalized = normalize_id_component(alias)
                existing = self.alias_to_ticker.get(normalized)
                if existing and existing != ticker:
                    raise ValueError(f"Ambiguous company alias {alias!r}: {existing} vs {ticker}")
                self.alias_to_ticker[normalized] = ticker

    @staticmethod
    def _ticker_for_legal_name(legal_name: str) -> str:
        normalized = normalize_id_component(legal_name)
        for ticker, known_name in COMPANY_NAME_MAP.items():
            if normalize_id_component(known_name) == normalized:
                return ticker
        raise ValueError(f"No ticker mapping for configured company {legal_name!r}")

    def resolve(
        self,
        name: str,
        properties: dict[str, Any],
        report_id: str | None = None,
    ) -> CompanyIdentity | None:
        ticker_hint = properties.get("ticker")
        if isinstance(ticker_hint, str) and ticker_hint.upper() in self.by_ticker:
            return self.by_ticker[ticker_hint.upper()]
        company_id = properties.get("company_id")
        if isinstance(company_id, str) and company_id.startswith("company:"):
            ticker = company_id.split(":", 1)[1].upper()
            if ticker in self.by_ticker:
                return self.by_ticker[ticker]
        if report_id and report_id.startswith("report:"):
            ticker = report_id.removeprefix("report:").split("__", 1)[0].upper()
            if ticker in self.by_ticker:
                return self.by_ticker[ticker]
        resolved_ticker = self.alias_to_ticker.get(normalize_id_component(name))
        return self.by_ticker.get(resolved_ticker) if resolved_ticker else None


def build_entity_context(record: EntityExtractionRecord) -> EntityContext:
    properties = record.properties
    report_id = _string_or_none(properties.get("source_report_id"))
    company_id = _string_or_none(properties.get("company_id"))
    if company_id is None and record.type == "Company":
        ticker = properties.get("ticker")
        if isinstance(ticker, str):
            company_id = f"company:{ticker.upper()}"
    if company_id is None and report_id and report_id.startswith("report:"):
        ticker = report_id.removeprefix("report:").split("__", 1)[0]
        company_id = f"company:{ticker.upper()}"

    date_id = _string_or_none(properties.get("date_id"))
    year = _extract_year(date_id, report_id, record.source_file)
    numeric_value = properties.get("value")
    return EntityContext(
        company_id=company_id,
        year=year,
        report_id=report_id,
        date_id=date_id,
        scope=_upper_or_none(properties.get("scope")),
        unit=_upper_or_none(properties.get("unit")),
        numeric_value=float(numeric_value) if isinstance(numeric_value, (int, float)) else None,
        model_codes=sorted(set(re.findall(r"\d+", record.canonical_name))),
        evidence_tokens=sorted(set(normalize_words(record.evidence_text).split())),
    )


def _extract_year(*values: str | None) -> int | None:
    for value in values:
        if value:
            match = re.search(r"\b(19|20)\d{2}\b", value)
            if match:
                return int(match.group(0))
    return None


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _upper_or_none(value: Any) -> str | None:
    return value.upper().strip() if isinstance(value, str) and value.strip() else None
