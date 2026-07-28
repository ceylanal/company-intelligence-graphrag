"""Unit and integration tests for Neo4j Graph Ingestion, Checkpointing, and Idempotency (Day 21)."""

from pathlib import Path

from company_graphrag.graph.ingestion import GraphIngestionPipeline
from company_graphrag.storage import MockNeo4jStore, Neo4jGraphStore


def test_neo4j_mock_store_basic() -> None:
    """Test MockNeo4jStore cypher MERGE execution and verification queries."""
    store = MockNeo4jStore()

    # Execute constraint query
    store.execute_cypher("CREATE CONSTRAINT c_company_id IF NOT EXISTS FOR (c:Company) REQUIRE c.id IS UNIQUE;")
    assert len(store.constraints) == 1

    # Execute node MERGE batch
    batch_nodes = [
        {
            "id": "company:ASELS",
            "canonical_name": "Aselsan",
            "source_chunk_id": "c1",
            "source_file": "report.pdf",
            "page_number": 1,
            "evidence_text": "Aselsan 2024",
        }
    ]
    store.execute_cypher("UNWIND $batch AS item MERGE (n:Company {id: item.id})", {"batch": batch_nodes})
    assert len(store.nodes) == 1
    assert "company:ASELS" in store.nodes

    # Execute relation MERGE batch
    batch_rels = [
        {
            "id": "rel1",
            "source_id": "company:ASELS",
            "target_id": "report:ASELS:2024",
            "source_chunk_id": "c1",
            "source_file": "report.pdf",
            "page_number": 1,
            "evidence_text": "published report",
        }
    ]
    store.execute_cypher(
        "UNWIND $batch AS item MERGE (source)-[r:PUBLISHED {id: item.id}]->(target)", {"batch": batch_rels}
    )
    assert len(store.relationships) == 1


def test_ingestion_pipeline_run_sample(tmp_path: Path) -> None:
    """Test full pipeline execution over sample_day20 dataset."""
    sample_dir = Path("data/graph/sample_day20")
    if not sample_dir.exists():
        sample_dir = Path("data/graph/sample_day19")

    mock_graph_store = Neo4jGraphStore(mock_mode=True)
    pipeline = GraphIngestionPipeline(neo4j_store=mock_graph_store, batch_size=50)

    # Run pipeline first time
    report1 = pipeline.run_pipeline(input_dir=sample_dir, checkpoint_path=tmp_path / "chk1.json")
    assert report1.status == "PASS"
    assert report1.ingested_nodes > 0
    assert report1.ingested_relations >= 0
    assert (sample_dir / "ingestion_audit_report.json").exists()

    # Run pipeline second time (Idempotent MERGE check)
    report2 = pipeline.run_pipeline(input_dir=sample_dir, checkpoint_path=tmp_path / "chk1.json")
    assert report2.status == "PASS"
    # Secondary run with checkpoint should have duplicate_merge_attempts equal to total inputs
    assert report2.duplicate_merge_attempts == report1.total_input_entities + report1.total_input_relations

    mock_graph_store.close()


def test_grounding_metadata_retention() -> None:
    """Verify that source_chunk_id, source_file, page_number, evidence_text are retained."""
    store = Neo4jGraphStore(mock_mode=True)
    pipeline = GraphIngestionPipeline(neo4j_store=store)

    from company_graphrag.graph.ingestion.models import IngestionEntityItem, IngestionRelationItem

    ent = IngestionEntityItem(
        id="metric:ASELS:2024:revenue",
        type="FinancialMetric",
        canonical_name="Ciro",
        properties={"value": 120.0, "unit": "Milyar TL"},
        source_chunk_id="chunk_7b5a",
        source_file="ASELS__2024__annual_report__tr.pdf",
        page_number=14,
        evidence_text="2024 yılı ciromuz 120 Milyar TL olarak gerçekleşti.",
    )
    pipeline.ingest_entities_batch([ent])

    mock_inner = store._mock_store
    assert mock_inner is not None
    node = mock_inner.nodes.get("metric:ASELS:2024:revenue")
    assert node is not None
    props = node["properties"]
    assert props["source_chunk_id"] == "chunk_7b5a"
    assert props["source_file"] == "ASELS__2024__annual_report__tr.pdf"
    assert props["page_number"] == 14
    assert props["evidence_text"] == "2024 yılı ciromuz 120 Milyar TL olarak gerçekleşti."

    rel = IngestionRelationItem(
        id="rel_sourced_from_1",
        type="SOURCED_FROM",
        source_id="metric:ASELS:2024:revenue",
        source_label="FinancialMetric",
        target_id="chunk:chunk_7b5a",
        target_label="Chunk",
        source_chunk_id="chunk_7b5a",
        source_file="ASELS__2024__annual_report__tr.pdf",
        page_number=14,
        evidence_text="2024 yılı ciromuz 120 Milyar TL olarak gerçekleşti.",
    )
    pipeline.ingest_relations_batch([rel])
    edge = mock_inner.relationships.get("rel_sourced_from_1")
    assert edge is not None
    r_props = edge["properties"]
    assert r_props["source_chunk_id"] == "chunk_7b5a"
    assert r_props["source_file"] == "ASELS__2024__annual_report__tr.pdf"
    assert r_props["page_number"] == 14
    assert r_props["evidence_text"] == "2024 yılı ciromuz 120 Milyar TL olarak gerçekleşti."

    store.close()
