"""Tests for the schema-grounded entity and relation extraction pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from company_graphrag.chunking.models import ChunkRecord
from company_graphrag.graph.extraction import (
    GraphExtractionPipeline,
    RejectionReason,
    StaticExtractionProvider,
)

EXTRACTION_VERSION = "day19-test-v1"


def make_chunk() -> ChunkRecord:
    return ChunkRecord(
        chunk_id="0123456789abcdef",
        document_id="ASELS__2024__annual_report__tr",
        company="Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
        ticker="ASELS",
        year=2024,
        report_type="annual_report",
        language="tr",
        page_number=34,
        chunk_index=12,
        text=(
            "ASELSAN CEO Ahmet AKYOL, 2024 yılında görevine devam etti. "
            "Toplam Hasılat 120.206 milyon TL olarak raporlandı."
        ),
        token_count=28,
        source_file="ASELS__2024__annual_report__tr.pdf",
    )


def provenance(chunk: ChunkRecord) -> dict[str, Any]:
    return {
        "source_chunk_id": chunk.chunk_id,
        "source_file": chunk.source_file,
        "page_number": chunk.page_number,
    }


def company_candidate(chunk: ChunkRecord, ref: str = "company") -> dict[str, Any]:
    return {
        "ref": ref,
        "type": "Company",
        "canonical_name": "ASELSAN",
        "properties": {"name": "ASELSAN", "ticker": "ASELS"},
        "evidence_text": "ASELSAN",
        "confidence": 0.99,
        **provenance(chunk),
    }


def person_candidate(chunk: ChunkRecord, ref: str = "person") -> dict[str, Any]:
    return {
        "ref": ref,
        "type": "Person",
        "canonical_name": "Ahmet Akyol",
        "properties": {
            "name": "Ahmet AKYOL",
            "normalized_name": "ahmet_akyol",
            "company_id": "company:ASELS",
        },
        "evidence_text": "Ahmet AKYOL",
        "confidence": 0.97,
        **provenance(chunk),
    }


def valid_response(chunk: ChunkRecord) -> dict[str, Any]:
    return {
        "entities": [company_candidate(chunk), person_candidate(chunk)],
        "relations": [
            {
                "type": "HOLDS_ROLE_AT",
                "source_ref": "person",
                "target_ref": "company",
                "properties": {"role": "CEO"},
                "evidence_text": "CEO Ahmet AKYOL",
                "confidence": 0.96,
                **provenance(chunk),
            }
        ],
    }


def run_response(
    tmp_path: Path,
    response: str | dict[str, Any],
    *,
    version: str = EXTRACTION_VERSION,
) -> tuple[ChunkRecord, StaticExtractionProvider, Any]:
    chunk = make_chunk()
    provider = StaticExtractionProvider({chunk.chunk_id: response})
    pipeline = GraphExtractionPipeline(
        provider=provider,
        output_dir=tmp_path,
        extraction_version=version,
    )
    return chunk, provider, pipeline.run_chunks([chunk])


def jsonl_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def test_valid_entity_extraction_is_schema_validated(tmp_path: Path) -> None:
    chunk, _, result = run_response(tmp_path, valid_response(make_chunk()))

    assert result.metrics.entity_count == 2
    person = next(entity for entity in result.entities if entity.type == "Person")
    assert person.id == "person:ASELS:ahmet_akyol"
    assert person.canonical_name == "Ahmet Akyol"
    assert person.source_chunk_id == chunk.chunk_id
    assert person.source_file == chunk.source_file
    assert person.page_number == chunk.page_number
    assert person.evidence_text == "Ahmet AKYOL"
    assert person.confidence == 0.97
    assert person.extraction_version == EXTRACTION_VERSION
    assert person.properties["source_report_id"] == "report:ASELS__2024__annual_report__tr"
    assert person.properties["source_chunk_id"] == chunk.chunk_id
    assert person.properties["source_page"] == chunk.page_number


def test_valid_relation_extraction_resolves_refs_and_endpoints(tmp_path: Path) -> None:
    chunk, _, result = run_response(tmp_path, valid_response(make_chunk()))

    assert result.metrics.relation_count == 1
    relation = result.relations[0]
    assert relation.type == "HOLDS_ROLE_AT"
    assert relation.source_entity_id == "person:ASELS:ahmet_akyol"
    assert relation.target_entity_id == "company:ASELS"
    assert relation.id.startswith("rel:holds_role_at:")
    assert relation.properties["role"] == "CEO"
    assert relation.properties["source_chunk_id"] == chunk.chunk_id
    assert relation.evidence_text == "CEO Ahmet AKYOL"


def test_unknown_node_and_relation_types_are_rejected(tmp_path: Path) -> None:
    chunk = make_chunk()
    invalid_entity = {
        **company_candidate(chunk, ref="robot"),
        "type": "Robot",
        "canonical_name": "Robot",
    }
    response = {
        "entities": [company_candidate(chunk), invalid_entity],
        "relations": [
            {
                "type": "INVENTED_RELATION",
                "source_ref": "company",
                "target_ref": "company",
                "properties": {},
                "evidence_text": "ASELSAN",
                "confidence": 0.5,
                **provenance(chunk),
            }
        ],
    }
    _, _, result = run_response(tmp_path, response)

    assert {record.reason_code for record in result.rejections} == {
        RejectionReason.UNKNOWN_NODE_TYPE,
        RejectionReason.UNKNOWN_RELATION_TYPE,
    }
    assert result.metrics.entity_count == 1
    assert result.metrics.relation_count == 0


def test_missing_candidate_provenance_is_rejected(tmp_path: Path) -> None:
    chunk = make_chunk()
    candidate = company_candidate(chunk)
    candidate.pop("source_file")
    _, _, result = run_response(tmp_path, {"entities": [candidate], "relations": []})

    assert result.metrics.entity_count == 0
    assert result.rejections[0].reason_code == RejectionReason.ENTITY_MODEL_INVALID
    assert "source_file" in result.rejections[0].reason


def test_provenance_mismatch_is_rejected(tmp_path: Path) -> None:
    chunk = make_chunk()
    candidate = person_candidate(chunk)
    candidate["page_number"] = 999
    _, _, result = run_response(tmp_path, {"entities": [candidate], "relations": []})

    assert result.rejections[0].reason_code == RejectionReason.PROVENANCE_MISMATCH
    assert "expected 34" in result.rejections[0].reason


def test_evidence_not_exactly_in_chunk_is_rejected(tmp_path: Path) -> None:
    chunk = make_chunk()
    candidate = company_candidate(chunk)
    candidate["evidence_text"] = "ASELSAN raporda bulunmayan ifade"
    _, _, result = run_response(tmp_path, {"entities": [candidate], "relations": []})

    assert result.metrics.entity_count == 0
    assert result.rejections[0].reason_code == RejectionReason.EVIDENCE_NOT_IN_CHUNK


def test_invalid_graph_properties_are_rejected_by_day18_schema(tmp_path: Path) -> None:
    chunk = make_chunk()
    candidate = person_candidate(chunk)
    del candidate["properties"]["normalized_name"]
    _, _, result = run_response(tmp_path, {"entities": [candidate], "relations": []})

    assert result.rejections[0].reason_code == RejectionReason.SCHEMA_VALIDATION_FAILED
    assert "normalized_name" in result.rejections[0].reason


def test_deterministic_ids_across_independent_runs(tmp_path: Path) -> None:
    chunk = make_chunk()
    response = valid_response(chunk)
    _, _, first = run_response(tmp_path / "first", response)
    _, _, second = run_response(tmp_path / "second", response)

    assert [record.id for record in first.entities] == [record.id for record in second.entities]
    assert [record.id for record in first.relations] == [record.id for record in second.relations]


def test_repeated_chunk_uses_cache_without_duplicate_output(tmp_path: Path) -> None:
    chunk = make_chunk()
    provider = StaticExtractionProvider({chunk.chunk_id: valid_response(chunk)})
    pipeline = GraphExtractionPipeline(provider, tmp_path, EXTRACTION_VERSION)

    first = pipeline.run_chunks([chunk])
    second = pipeline.run_chunks([chunk])

    assert first.metrics.cache_hits == 0
    assert first.metrics.provider_calls == 1
    assert second.metrics.cache_hits == 1
    assert second.metrics.provider_calls == 0
    assert provider.call_count == 1
    assert jsonl_count(first.entities_path) == 2
    assert jsonl_count(first.relations_path) == 1
    assert jsonl_count(first.rejections_path) == 0
    checkpoint = json.loads(first.checkpoint_path.read_text(encoding="utf-8"))
    assert f"{EXTRACTION_VERSION}:{chunk.chunk_id}" in checkpoint["completed"]


def test_extraction_version_change_recomputes_without_overwrite(tmp_path: Path) -> None:
    chunk = make_chunk()
    provider = StaticExtractionProvider({chunk.chunk_id: valid_response(chunk)})

    first = GraphExtractionPipeline(provider, tmp_path, "extract-v1").run_chunks([chunk])
    second = GraphExtractionPipeline(provider, tmp_path, "extract-v2").run_chunks([chunk])

    assert first.metrics.provider_calls == 1
    assert second.metrics.provider_calls == 1
    assert second.metrics.cache_hits == 0
    assert provider.call_count == 2
    assert jsonl_count(first.entities_path) == 4
    versions = {
        json.loads(line)["extraction_version"] for line in first.entities_path.read_text(encoding="utf-8").splitlines()
    }
    assert versions == {"extract-v1", "extract-v2"}


def test_broken_llm_json_is_safely_rejected_and_cached(tmp_path: Path) -> None:
    _, provider, first = run_response(tmp_path, "```json\n{broken\n```")
    pipeline = GraphExtractionPipeline(provider, tmp_path, EXTRACTION_VERSION)
    second = pipeline.run_chunks([make_chunk()])

    assert first.metrics.entity_count == 0
    assert first.metrics.relation_count == 0
    assert first.rejections[0].reason_code == RejectionReason.LLM_JSON_INVALID
    assert first.rejections_path.exists()
    assert second.metrics.cache_hits == 1
    assert provider.call_count == 1
    assert jsonl_count(first.rejections_path) == 1


def test_wrong_relation_endpoint_direction_is_rejected(tmp_path: Path) -> None:
    chunk = make_chunk()
    response = valid_response(chunk)
    response["relations"][0]["source_ref"] = "company"
    response["relations"][0]["target_ref"] = "person"
    _, _, result = run_response(tmp_path, response)

    assert result.metrics.relation_count == 0
    assert result.rejections[0].reason_code == RejectionReason.SCHEMA_VALIDATION_FAILED
    assert "expected source" in result.rejections[0].reason


def test_invalid_chunk_jsonl_is_written_to_rejections(tmp_path: Path) -> None:
    input_path = tmp_path / "input.jsonl"
    invalid_chunk = make_chunk().model_dump()
    del invalid_chunk["source_file"]
    input_path.write_text(json.dumps(invalid_chunk, ensure_ascii=False) + "\n", encoding="utf-8")

    provider = StaticExtractionProvider({})
    output_dir = tmp_path / "output"
    result = GraphExtractionPipeline(provider, output_dir, EXTRACTION_VERSION).run(input_path)

    assert result.metrics.processed_chunks == 1
    assert result.metrics.provider_calls == 0
    assert result.rejections[0].reason_code == RejectionReason.CHUNK_MODEL_INVALID
    assert jsonl_count(result.rejections_path) == 1
