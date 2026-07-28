"""Tests for context-aware entity resolution and canonicalization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from company_graphrag.graph.extraction import EntityExtractionRecord
from company_graphrag.graph.resolution import EntityResolutionPipeline, MatchClass

REPORT = "report:ASELS__2024__annual_report__tr"


def entity(
    name: str,
    entity_type: str,
    *,
    chunk: str,
    company_id: str | None = "company:ASELS",
    report_id: str | None = REPORT,
    properties: dict[str, Any] | None = None,
) -> EntityExtractionRecord:
    record_properties: dict[str, Any] = dict(properties or {})
    if company_id:
        record_properties.setdefault("company_id", company_id)
    if report_id:
        record_properties.setdefault("source_report_id", report_id)
    return EntityExtractionRecord(
        id=f"source:{entity_type.lower()}:{chunk}",
        type=entity_type,
        canonical_name=name,
        properties=record_properties,
        source_chunk_id=chunk,
        source_file=f"{report_id or 'unknown'}.pdf",
        page_number=1,
        evidence_text=f"{name} bağlamı",
        confidence=0.95,
        extraction_version="day19-test-v1",
    )


def decision_classes(result: Any) -> set[MatchClass]:
    return {decision.match_class for decision in result.decisions}


def test_company_registry_merges_ticker_legal_name_and_alias(tmp_path: Path) -> None:
    records = [
        entity("ASELSAN", "Company", chunk="c1", properties={"ticker": "ASELS"}),
        entity(
            "Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
            "Company",
            chunk="c2",
            properties={},
        ),
        entity("ASELS", "Company", chunk="c3", properties={}),
    ]

    result = EntityResolutionPipeline(tmp_path).resolve(records)

    assert result.metrics.canonical_entity_count == 1
    assert result.metrics.merged_record_count == 2
    assert result.canonical_entities[0].canonical_id == "company:ASELS"
    assert all(decision.match_class == MatchClass.EXACT_MATCH for decision in result.decisions)


def test_person_title_normalization_merges_only_with_same_company(tmp_path: Path) -> None:
    records = [
        entity("Ahmet Akyol", "Person", chunk="p1"),
        entity("Dr. Ahmet AKYOL", "Person", chunk="p2"),
        entity("Ahmet Akyol", "Person", chunk="p3", company_id="company:KCHOL"),
    ]

    result = EntityResolutionPipeline(tmp_path).resolve(records)

    assert result.metrics.merged_record_count == 1
    assert MatchClass.EXACT_MATCH in decision_classes(result)
    assert MatchClass.DIFFERENT_ENTITY in decision_classes(result)
    assert result.metrics.canonical_entity_count == 2


def test_minor_person_typo_with_report_context_is_high_confidence(tmp_path: Path) -> None:
    records = [
        entity("Ahmet Akyol", "Person", chunk="p1"),
        entity("Ahmet Akyal", "Person", chunk="p2"),
    ]

    result = EntityResolutionPipeline(tmp_path).resolve(records)

    assert result.metrics.merged_record_count == 1
    assert result.decisions[0].match_class == MatchClass.HIGH_CONFIDENCE_MATCH


def test_product_model_conflict_blocks_name_only_merge(tmp_path: Path) -> None:
    records = [
        entity("SİPER Ürün-1", "Product", chunk="x1"),
        entity("SİPER Ürün-2", "Product", chunk="x2"),
    ]

    result = EntityResolutionPipeline(tmp_path).resolve(records)

    assert result.metrics.merged_record_count == 0
    assert result.decisions[0].match_class == MatchClass.DIFFERENT_ENTITY
    assert "model-number conflict" in result.decisions[0].rationale


def test_sector_synonyms_are_exact_match(tmp_path: Path) -> None:
    result = EntityResolutionPipeline(tmp_path).resolve(
        [
            entity("Savunma Sanayii", "Sector", chunk="s1", company_id=None),
            entity("Savunma Endüstrisi", "Sector", chunk="s2", company_id=None),
        ]
    )

    assert result.metrics.merged_record_count == 1
    assert result.decisions[0].match_class == MatchClass.EXACT_MATCH
    assert result.canonical_entities[0].canonical_id == "sector:savunma_sanayii"


def test_metric_alias_requires_matching_observation_context(tmp_path: Path) -> None:
    base = {
        "date_id": "date:2024",
        "scope": "CONSOLIDATED",
        "unit": "TRY",
        "value": 120206.0,
    }
    records = [
        entity("Toplam Hasılat", "FinancialMetric", chunk="m1", properties=base),
        entity("Ciro", "FinancialMetric", chunk="m2", properties=base),
        entity(
            "Ciro",
            "FinancialMetric",
            chunk="m3",
            report_id="report:ASELS__2023__annual_report__tr",
            properties={**base, "date_id": "date:2023"},
        ),
    ]

    result = EntityResolutionPipeline(tmp_path).resolve(records)

    assert result.metrics.merged_record_count == 1
    assert MatchClass.EXACT_MATCH in decision_classes(result)
    assert MatchClass.DIFFERENT_ENTITY in decision_classes(result)


def test_conflicting_metric_value_requires_review_and_is_not_merged(tmp_path: Path) -> None:
    common = {"date_id": "date:2024", "scope": "CONSOLIDATED", "unit": "TRY"}
    result = EntityResolutionPipeline(tmp_path).resolve(
        [
            entity("Ciro", "FinancialMetric", chunk="m1", properties={**common, "value": 100.0}),
            entity("Hasılat", "FinancialMetric", chunk="m2", properties={**common, "value": 200.0}),
        ]
    )

    assert result.metrics.merged_record_count == 0
    assert result.metrics.ambiguous_record_count == 2
    assert result.decisions[0].match_class == MatchClass.REVIEW_REQUIRED
    assert result.aliases[0].candidate_canonical_id is not None


def test_canonical_ids_and_outputs_are_order_independent(tmp_path: Path) -> None:
    records = [
        entity("Dr. Ahmet Akyol", "Person", chunk="p2"),
        entity("Ahmet Akyol", "Person", chunk="p1"),
        entity("Savunma Sanayii", "Sector", chunk="s1", company_id=None),
    ]
    first = EntityResolutionPipeline(tmp_path / "first").resolve(records)
    second = EntityResolutionPipeline(tmp_path / "second").resolve(reversed(records))

    assert [item.canonical_id for item in first.canonical_entities] == [
        item.canonical_id for item in second.canonical_entities
    ]
    assert first.aliases_path.read_text(encoding="utf-8") == second.aliases_path.read_text(encoding="utf-8")
    assert first.decisions_path.read_text(encoding="utf-8") == second.decisions_path.read_text(encoding="utf-8")


def test_alias_and_decision_audit_files_are_machine_readable(tmp_path: Path) -> None:
    result = EntityResolutionPipeline(tmp_path).resolve(
        [entity("Ahmet Akyol", "Person", chunk="p1"), entity("Ahmet Akyal", "Person", chunk="p2")]
    )

    aliases = [json.loads(line) for line in result.aliases_path.read_text().splitlines()]
    decisions = [json.loads(line) for line in result.decisions_path.read_text().splitlines()]
    metrics = json.loads(result.metrics_path.read_text())

    assert len(aliases) == 2
    assert aliases[0]["source_chunk_id"]
    assert decisions[0]["rationale"]
    assert decisions[0]["signals"]
    assert metrics["merged_record_count"] == 1
