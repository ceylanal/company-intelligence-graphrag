"""Contract tests for the citation-first GraphRAG ontology."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from company_graphrag.chunking.models import ChunkRecord
from company_graphrag.graph.models import (
    ChunkNode,
    CompanyNode,
    DateNode,
    EventNode,
    FinancialMetricNode,
    GraphRelationship,
    PersonNode,
    ProductNode,
    ReportNode,
    SectorNode,
)
from company_graphrag.graph.schema import DEFAULT_SCHEMA_PATH, GraphSchemaManager

PROJECT_ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def manager() -> GraphSchemaManager:
    return GraphSchemaManager()


def test_schema_loads_expected_small_ontology(manager: GraphSchemaManager) -> None:
    """The first version contains the requested types plus the essential Chunk anchor."""
    assert manager.config.version == "1.0.0"
    assert set(manager.get_node_types()) == {
        "Company",
        "Report",
        "Chunk",
        "Person",
        "Product",
        "Sector",
        "FinancialMetric",
        "Event",
        "Date",
    }
    assert set(manager.get_relationship_types()) == {
        "PUBLISHED",
        "HAS_CHUNK",
        "COVERS_DATE",
        "OPERATES_IN",
        "OFFERS",
        "HOLDS_ROLE_AT",
        "REPORTED_METRIC",
        "CONTAINS_METRIC",
        "FOR_DATE",
        "EXPERIENCED",
        "DESCRIBES_EVENT",
        "OCCURRED_ON",
        "OWNS",
        "EVIDENCED_BY",
    }


def test_current_chunk_metadata_is_losslessly_mapped(manager: GraphSchemaManager) -> None:
    """Every current ChunkRecord payload field is declared on the Chunk graph node."""
    graph_fields = set(manager.get_node_types()["Chunk"].all_properties)
    assert set(ChunkRecord.model_fields) <= graph_fields
    assert {"id", "report_id"} <= graph_fields - set(ChunkRecord.model_fields)

    source_mapping = manager.config.source_contract.chunk_metadata
    assert set(ChunkRecord.model_fields) == set(source_mapping)
    assert "1-based PDF page" in source_mapping["page_number"]


def test_all_schema_objects_define_identity_and_provenance(manager: GraphSchemaManager) -> None:
    """Nodes and relationships explicitly declare required/optional fields, IDs, and sources."""
    for node in manager.get_node_types().values():
        assert node.primary_key in node.required_properties
        assert node.id_generation.inputs
        assert node.id_generation.example
        assert set(node.provenance.required_fields) <= set(node.required_properties)
        assert set(node.provenance.optional_fields) <= set(node.all_properties)

    for relationship in manager.get_relationship_types().values():
        assert "id" in relationship.required_properties
        assert relationship.id_generation.strategy == "sha256"
        assert relationship.id_generation.digest_length == 24
        assert set(relationship.provenance.required_fields) <= set(relationship.required_properties)
        assert set(relationship.provenance.optional_fields) <= set(relationship.all_properties)


def test_extracted_facts_require_report_chunk_and_page(manager: GraphSchemaManager) -> None:
    """Fact nodes and claim relationships cannot lose their citation coordinates."""
    citation_fields = {"source_report_id", "source_chunk_id", "source_page"}
    for label in ("Person", "Product", "FinancialMetric", "Event"):
        assert citation_fields <= set(manager.get_node_types()[label].required_properties)

    for rel_type in (
        "OPERATES_IN",
        "OFFERS",
        "HOLDS_ROLE_AT",
        "REPORTED_METRIC",
        "CONTAINS_METRIC",
        "FOR_DATE",
        "EXPERIENCED",
        "DESCRIBES_EVENT",
        "OCCURRED_ON",
        "OWNS",
    ):
        assert citation_fields <= set(manager.get_relationship_types()[rel_type].required_properties)


def test_node_id_generation_is_deterministic_and_collision_aware() -> None:
    """Canonical IDs normalize text and source-specific facts do not overwrite restatements."""
    assert CompanyNode.create_id("asels") == "company:ASELS"
    assert ReportNode.create_id("ASELS", 2024, "annual_report", "tr") == "report:ASELS__2024__annual_report__tr"
    assert ReportNode.create_id("ASELS", 2024, "annual_report", "tr") != ReportNode.create_id(
        "ASELS", 2024, "annual_report", "en"
    )
    assert ChunkNode.create_id("9AE32E0219BCE5D6") == "chunk:9ae32e0219bce5d6"
    assert PersonNode.create_id("ASELS", "Ahmet Akyol") == "person:ASELS:ahmet_akyol"
    assert ProductNode.create_id("ASELS", "SİPER Ürün-1") == "product:ASELS:siper_urun_1"
    assert SectorNode.create_id("Savunma Elektroniği") == "sector:savunma_elektronigi"
    assert DateNode.create_id("2024-q4") == "date:2024-Q4"

    report_2024 = "report:ASELS__2024__annual_report__tr"
    metric_id = FinancialMetricNode.create_id("ASELS", "Toplam Hasılat", "2024", report_2024)
    assert metric_id == "metric:ASELS:1850b44ae9a94e4790efee69"
    assert metric_id == FinancialMetricNode.create_id("ASELS", "Toplam Hasılat", "2024", report_2024)
    assert metric_id != FinancialMetricNode.create_id(
        "ASELS",
        "Toplam Hasılat",
        "2024",
        "report:ASELS__2025__annual_report__tr",
    )

    event_id = EventNode.create_id("ASELS", "2024-11-14", "49. kuruluş yıl dönümü", report_2024)
    assert event_id == EventNode.create_id("ASELS", "2024-11-14", "49. kuruluş yıl dönümü", report_2024)


def test_relationship_id_generation_uses_qualifier() -> None:
    """Role or source qualifiers can distinguish otherwise identical endpoints."""
    report_id = "report:ASELS__2024__annual_report__tr"
    base = GraphRelationship.create_id("HOLDS_ROLE_AT", "person:ASELS:ahmet_akyol", "company:ASELS", "CEO", report_id)
    same = GraphRelationship.create_id("HOLDS_ROLE_AT", "person:ASELS:ahmet_akyol", "company:ASELS", "CEO", report_id)
    different = GraphRelationship.create_id(
        "HOLDS_ROLE_AT",
        "person:ASELS:ahmet_akyol",
        "company:ASELS",
        "Yönetim Kurulu Üyesi",
        report_id,
    )
    assert base == same
    assert base != different
    assert base.startswith("rel:holds_role_at:")
    assert len(base.rsplit(":", 1)[1]) == 24


def test_node_validation_checks_required_type_pattern_enum_and_unknown(
    manager: GraphSchemaManager,
) -> None:
    valid_company = {"id": "company:ASELS", "name": "ASELSAN", "ticker": "ASELS"}
    assert manager.validate_node_dict("Company", valid_company) == []

    errors = manager.validate_node_dict(
        "Company",
        {"id": "bad-id", "name": " ", "ticker": "asels", "invented": True},
    )
    assert any("does not match" in error and "'id'" in error for error in errors)
    assert any("must not be blank" in error for error in errors)
    assert any("does not match" in error and "'ticker'" in error for error in errors)
    assert any("unknown property 'invented'" in error for error in errors)

    metric_errors = manager.validate_node_dict(
        "FinancialMetric",
        {
            "id": "metric:ASELS:1850b44ae9a94e4790efee69",
            "metric_key": "toplam_hasilat",
            "name": "Toplam Hasılat",
            "value": "120206",
            "unit": "TRY",
            "company_id": "company:ASELS",
            "date_id": "date:2024",
            "scope": "GROUP",
        },
    )
    assert any("expected FLOAT" in error for error in metric_errors)
    assert any("must be one of" in error and "'scope'" in error for error in metric_errors)
    assert any("source_report_id" in error for error in metric_errors)
    assert any("source_chunk_id" in error for error in metric_errors)
    assert any("source_page" in error for error in metric_errors)


def test_relationship_validation_checks_endpoints_and_properties(manager: GraphSchemaManager) -> None:
    published_properties = {
        "id": "rel:published:97d7384b7897317ad3b49a1b",
        "source_report_id": "report:ASELS__2024__annual_report__tr",
    }
    assert manager.validate_relationship("PUBLISHED", "Company", "Report", published_properties) == []
    assert (
        manager.validate_relationship(
            "EVIDENCED_BY",
            "FinancialMetric",
            "Chunk",
            {
                "id": "rel:evidenced_by:b28b1808cdd1f30276b6737f",
                "source_report_id": "report:ASELS__2024__annual_report__tr",
                "source_page": 19,
            },
        )
        == []
    )

    errors = manager.validate_relationship("HOLDS_ROLE_AT", "Company", "Person", {"id": "rel:x"})
    assert any("expected source" in error for error in errors)
    assert any("expected target 'Company'" in error for error in errors)
    assert any("missing required property 'role'" in error for error in errors)
    assert any("missing required property 'source_chunk_id'" in error for error in errors)


def test_schema_rejects_dangling_relationship_endpoint(tmp_path: Path) -> None:
    """Cross-reference validation fails before an invalid schema can be used."""
    raw_schema = yaml.safe_load(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    raw_schema["relationship_types"]["PUBLISHED"]["target"] = "MissingLabel"
    invalid_schema = tmp_path / "invalid_schema.yaml"
    invalid_schema.write_text(yaml.safe_dump(raw_schema, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ValidationError, match="unknown target label"):
        GraphSchemaManager(invalid_schema)


def test_neo4j_plan_is_community_safe_and_export_is_in_sync(manager: GraphSchemaManager) -> None:
    """The checked-in Cypher is generated from YAML and avoids Enterprise-only assumptions."""
    statements = manager.generate_neo4j_cypher_statements()
    checked_in = (PROJECT_ROOT / "data" / "neo4j_schema.cypher").read_text(encoding="utf-8").splitlines()

    assert checked_in == statements
    assert manager.config.neo4j.edition == "community"
    assert any("CONSTRAINT c_company_ticker" in statement for statement in statements)
    assert any("CONSTRAINT c_date_value" in statement for statement in statements)
    assert any("INDEX idx_metric_lookup" in statement for statement in statements)
    assert any("FULLTEXT INDEX idx_entity_fulltext" in statement for statement in statements)
    assert any("FOR ()-[r:EVIDENCED_BY]-()" in statement for statement in statements)
    assert not any("REQUIRE r.id IS UNIQUE" in statement for statement in statements)
    assert any("Relationship IDs" in rule for rule in manager.config.neo4j.application_enforced_rules)
