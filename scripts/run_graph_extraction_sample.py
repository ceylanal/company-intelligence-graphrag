"""Run the Day 19 extraction pipeline on two curated ASELSAN chunks without network calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from company_graphrag.chunking.models import ChunkRecord
from company_graphrag.graph.extraction import GraphExtractionPipeline, StaticExtractionProvider

PROJECT_ROOT = Path(__file__).parents[1]
SOURCE_CHUNKS = PROJECT_ROOT / "data" / "processed" / "chunks" / "ASELS" / "ASELS__2024__annual_report__tr_chunks.jsonl"
SAMPLE_CHUNK_IDS = ("9ae32e0219bce5d6", "bc9ba3dc0a3d1242")
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "graph" / "sample_day19"
EXTRACTION_VERSION = "day19-sample-v1"


def load_sample_chunks() -> list[ChunkRecord]:
    """Load exactly the two curated records from the existing chunk JSONL."""
    selected: dict[str, ChunkRecord] = {}
    with SOURCE_CHUNKS.open(encoding="utf-8") as chunk_file:
        for line in chunk_file:
            if not line.strip():
                continue
            chunk = ChunkRecord.model_validate_json(line)
            if chunk.chunk_id in SAMPLE_CHUNK_IDS:
                selected[chunk.chunk_id] = chunk
    missing = set(SAMPLE_CHUNK_IDS) - set(selected)
    if missing:
        raise RuntimeError(f"Curated sample chunks are missing: {sorted(missing)}")
    return [selected[chunk_id] for chunk_id in SAMPLE_CHUNK_IDS]


def candidate_provenance(chunk: ChunkRecord) -> dict[str, Any]:
    return {
        "source_chunk_id": chunk.chunk_id,
        "source_file": chunk.source_file,
        "page_number": chunk.page_number,
    }


def build_responses(chunks: list[ChunkRecord]) -> dict[str, dict[str, Any]]:
    """Build deterministic fake-provider output grounded in exact source substrings."""
    metric_chunk, person_chunk = chunks
    metric_evidence = "Toplam Hasılat (Milyon TL) 2024 120.206"
    person_evidence = "Ahmet AKYOL\nCEO/Genel Müdür"

    return {
        metric_chunk.chunk_id: {
            "entities": [
                {
                    "ref": "company",
                    "type": "Company",
                    "canonical_name": "ASELSAN",
                    "properties": {
                        "name": "Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
                        "ticker": "ASELS",
                    },
                    "evidence_text": "ASELSAN",
                    "confidence": 0.99,
                    **candidate_provenance(metric_chunk),
                },
                {
                    "ref": "metric",
                    "type": "FinancialMetric",
                    "canonical_name": "Toplam Hasılat",
                    "properties": {
                        "metric_key": "toplam_hasilat",
                        "name": "Toplam Hasılat",
                        "value": 120206.0,
                        "unit": "TRY",
                        "company_id": "company:ASELS",
                        "date_id": "date:2024",
                        "scope": "CONSOLIDATED",
                        "reported_value": "120.206 milyon TL",
                        "scale": 1000000,
                    },
                    "evidence_text": metric_evidence,
                    "confidence": 0.98,
                    **candidate_provenance(metric_chunk),
                },
                {
                    "ref": "date",
                    "type": "Date",
                    "canonical_name": "2024",
                    "properties": {
                        "value": "2024",
                        "granularity": "YEAR",
                        "fiscal_year": 2024,
                    },
                    "evidence_text": "2024",
                    "confidence": 0.99,
                    **candidate_provenance(metric_chunk),
                },
                {
                    "ref": "invalid_event",
                    "type": "Event",
                    "canonical_name": "Kaynakta Olmayan Olay",
                    "properties": {
                        "title": "Kaynakta Olmayan Olay",
                        "normalized_title": "kaynakta_olmayan_olay",
                        "event_type": "OTHER",
                        "company_id": "company:ASELS",
                        "date_id": "date:2024",
                    },
                    "evidence_text": "Bu ifade kaynak chunk içinde bulunmuyor.",
                    "confidence": 0.51,
                    **candidate_provenance(metric_chunk),
                },
            ],
            "relations": [
                {
                    "type": "REPORTED_METRIC",
                    "source_ref": "company",
                    "target_ref": "metric",
                    "properties": {},
                    "evidence_text": metric_evidence,
                    "confidence": 0.97,
                    **candidate_provenance(metric_chunk),
                },
                {
                    "type": "FOR_DATE",
                    "source_ref": "metric",
                    "target_ref": "date",
                    "properties": {},
                    "evidence_text": metric_evidence,
                    "confidence": 0.98,
                    **candidate_provenance(metric_chunk),
                },
            ],
        },
        person_chunk.chunk_id: {
            "entities": [
                {
                    "ref": "company",
                    "type": "Company",
                    "canonical_name": "ASELSAN",
                    "properties": {
                        "name": "Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
                        "ticker": "ASELS",
                    },
                    "evidence_text": "ASELSAN",
                    "confidence": 0.99,
                    **candidate_provenance(person_chunk),
                },
                {
                    "ref": "person",
                    "type": "Person",
                    "canonical_name": "Ahmet Akyol",
                    "properties": {
                        "name": "Ahmet AKYOL",
                        "normalized_name": "ahmet_akyol",
                        "company_id": "company:ASELS",
                    },
                    "evidence_text": person_evidence,
                    "confidence": 0.97,
                    **candidate_provenance(person_chunk),
                },
            ],
            "relations": [
                {
                    "type": "HOLDS_ROLE_AT",
                    "source_ref": "person",
                    "target_ref": "company",
                    "properties": {"role": "CEO/Genel Müdür"},
                    "evidence_text": person_evidence,
                    "confidence": 0.96,
                    **candidate_provenance(person_chunk),
                }
            ],
        },
    }


def write_audit_report(output_dir: Path, result: Any) -> Path:
    audit_path = output_dir / "audit_report.json"
    payload = {
        "metrics": result.metrics.model_dump(mode="json"),
        "accepted_entity_example": result.entities[0].model_dump(mode="json") if result.entities else None,
        "accepted_relation_example": result.relations[0].model_dump(mode="json") if result.relations else None,
        "rejection_example": result.rejections[0].model_dump(mode="json") if result.rejections else None,
    }
    temporary_path = audit_path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(audit_path)
    return audit_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--single-run",
        action="store_true",
        help="Do not run a second pass that demonstrates cache hits.",
    )
    args = parser.parse_args()

    chunks = load_sample_chunks()
    provider = StaticExtractionProvider(build_responses(chunks))
    pipeline = GraphExtractionPipeline(
        provider=provider,
        output_dir=args.output_dir,
        extraction_version=EXTRACTION_VERSION,
    )
    result = pipeline.run_chunks(chunks)
    if not args.single_run:
        result = pipeline.run_chunks(chunks)

    audit_path = write_audit_report(args.output_dir, result)
    print(
        json.dumps(
            {
                "source_file": str(SOURCE_CHUNKS),
                "selected_chunk_ids": list(SAMPLE_CHUNK_IDS),
                "metrics": result.metrics.model_dump(mode="json"),
                "audit_report": str(audit_path),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
