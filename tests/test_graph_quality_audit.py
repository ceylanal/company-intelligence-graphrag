"""Unit tests for Graph Quality Auditor and Repair Engine (Day 22)."""

from pathlib import Path

from company_graphrag.graph.audit import GraphQualityAuditor, GraphQualityRepairer
from company_graphrag.graph.ingestion import GraphIngestionPipeline
from company_graphrag.storage import MockNeo4jStore, Neo4jGraphStore


def test_auditor_clean_graph(tmp_path: Path) -> None:
    """Test auditing a clean graph structure."""
    store = Neo4jGraphStore(mock_mode=True)
    pipeline = GraphIngestionPipeline(neo4j_store=store)

    # Ingest sample_day19 data with fresh checkpoint
    sample_dir = Path("data/graph/sample_day19")
    pipeline.run_pipeline(sample_dir, checkpoint_path=tmp_path / "test_chk.json")

    auditor = GraphQualityAuditor(neo4j_store=store)
    report = auditor.audit_graph()

    assert report.metrics.total_nodes > 0
    assert report.metrics.total_relations > 0
    assert report.metrics.dangling_relations_count == 0
    assert report.metrics.overall_quality_score >= 80.0
    assert report.metrics.status == "PASS"

    store.close()


def test_auditor_detects_anomalies_and_repairs(tmp_path: Path) -> None:
    """Test anomaly detection (dangling, missing grounding, low confidence) and automated repair."""
    store = Neo4jGraphStore(mock_mode=True)

    # Manually inject nodes and dangling relation into mock store
    mock_inner: MockNeo4jStore = store._mock_store  # type: ignore[assignment]
    mock_inner.nodes["company:ASELS"] = {
        "id": "company:ASELS",
        "labels": {"Company"},
        "properties": {"id": "company:ASELS", "name": "Aselsan", "ticker": "ASELS"},
    }
    # Dangling relation pointing to non-existent target 'report:MISSING'
    mock_inner.relationships["rel_dangling_1"] = {
        "id": "rel_dangling_1",
        "type": "PUBLISHED",
        "source_id": "company:ASELS",
        "target_id": "report:MISSING",
        "properties": {"id": "rel_dangling_1", "source_file": "source_unknown.pdf"},
    }

    auditor = GraphQualityAuditor(neo4j_store=store)
    report = auditor.audit_graph()

    assert report.metrics.dangling_relations_count == 1
    assert report.metrics.missing_grounding_count >= 1
    assert report.repairable_count >= 1

    # Execute automated repair
    repairer = GraphQualityRepairer(neo4j_store=store)
    summary = repairer.repair_graph(report, output_dir=tmp_path)

    assert summary.repaired_issues_count >= 1
    assert summary.dangling_relations_removed == 1
    assert (tmp_path / "human_review_queue.jsonl").exists()

    # Re-audit after repair
    report_after = auditor.audit_graph()
    assert report_after.metrics.dangling_relations_count == 0

    store.close()
