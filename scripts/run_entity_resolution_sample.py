"""Run Day 20 resolution on Day 19 records plus a small controlled variant set."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from company_graphrag.graph.extraction import EntityExtractionRecord
from company_graphrag.graph.resolution import EntityResolutionPipeline, MatchClass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAY19_ENTITIES = PROJECT_ROOT / "data" / "graph" / "sample_day19" / "entities.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "data" / "graph" / "sample_day20"
REPORT_2024 = "report:ASELS__2024__annual_report__tr"


def sample_entity(
    name: str,
    entity_type: str,
    chunk_id: str,
    *,
    company_id: str | None = "company:ASELS",
    report_id: str | None = REPORT_2024,
    properties: dict[str, Any] | None = None,
    confidence: float = 0.93,
) -> EntityExtractionRecord:
    payload = dict(properties or {})
    if company_id:
        payload.setdefault("company_id", company_id)
    if report_id:
        payload.setdefault("source_report_id", report_id)
    return EntityExtractionRecord(
        id=f"sample:{entity_type.lower()}:{chunk_id}",
        type=entity_type,
        canonical_name=name,
        properties=payload,
        source_chunk_id=chunk_id,
        source_file=f"{report_id or 'cross-report'}.pdf",
        page_number=42,
        evidence_text=f"{name} örnek bağlam",
        confidence=confidence,
        extraction_version="day19-sample-v1",
    )


def controlled_variants() -> list[EntityExtractionRecord]:
    metric_context = {
        "date_id": "date:2024",
        "scope": "CONSOLIDATED",
        "unit": "TRY",
        "value": 120206.0,
    }
    return [
        sample_entity("ASELS", "Company", "day20-company-alias", properties={}),
        sample_entity("Dr. Ahmet AKYOL", "Person", "day20-person-title"),
        sample_entity("Ahmet Akyal", "Person", "day20-person-typo", confidence=0.86),
        sample_entity(
            "Ahmet Akyol",
            "Person",
            "day20-person-other-company",
            company_id="company:KCHOL",
            report_id="report:KCHOL__2024__annual_report__tr",
        ),
        sample_entity("SİPER Ürün-1", "Product", "day20-product-1"),
        sample_entity("SIPER Urun 1", "Product", "day20-product-1-alias"),
        sample_entity("SİPER Ürün-2", "Product", "day20-product-2"),
        sample_entity("SİPER Ürün Sistemi", "Product", "day20-product-review"),
        sample_entity("Savunma Sanayii", "Sector", "day20-sector-tr", company_id=None),
        sample_entity("Savunma Endüstrisi", "Sector", "day20-sector-alias", company_id=None),
        sample_entity("Ciro", "FinancialMetric", "day20-metric-alias", properties=metric_context),
        sample_entity(
            "Hasılat",
            "FinancialMetric",
            "day20-metric-conflict",
            properties={**metric_context, "value": 99999.0},
        ),
        sample_entity(
            "Ciro",
            "FinancialMetric",
            "day20-metric-2023",
            report_id="report:ASELS__2023__annual_report__tr",
            properties={**metric_context, "date_id": "date:2023", "value": 98242.0},
        ),
    ]


def read_day19_entities() -> list[EntityExtractionRecord]:
    return [
        EntityExtractionRecord.model_validate_json(line)
        for line in DAY19_ENTITIES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_input(records: list[EntityExtractionRecord]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "input_entities.jsonl"
    path.write_text("".join(record.model_dump_json() + "\n" for record in records), encoding="utf-8")
    return path


def main() -> None:
    records = read_day19_entities() + controlled_variants()
    input_path = write_input(records)
    result = EntityResolutionPipeline(OUTPUT_DIR, resolution_version="day20-sample-v1").run(input_path)
    examples = {}
    for match_class in MatchClass:
        example = next(
            (item for item in result.decisions if item.match_class == match_class),
            None,
        )
        if example:
            examples[match_class.value] = example.model_dump(mode="json")
    audit = {
        "scope": {
            "day19_records": len(read_day19_entities()),
            "controlled_variants": len(controlled_variants()),
            "full_dataset_processed": False,
            "neo4j_written": False,
        },
        "metrics": result.metrics.model_dump(mode="json"),
        "example_decisions": examples,
    }
    (OUTPUT_DIR / "audit_report.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
