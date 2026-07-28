"""Unit and integration tests for End-to-End GraphRAG Final Audit (Day 26)."""

from pathlib import Path

from company_graphrag.graph.audit import GraphRAGFinalAuditor
from company_graphrag.graph.ingestion import GraphIngestionPipeline
from company_graphrag.storage import Neo4jGraphStore


def test_graphrag_final_auditor_mock(tmp_path: Path) -> None:
    """Test executing full end-to-end GraphRAG audit and exporting reports."""
    store = Neo4jGraphStore(mock_mode=True)
    pipeline = GraphIngestionPipeline(neo4j_store=store)

    # Ingest sample dataset
    sample_dir = Path("data/graph/sample_day19")
    pipeline.run_pipeline(sample_dir, checkpoint_path=tmp_path / "chk_final.json")

    auditor = GraphRAGFinalAuditor(neo4j_store=store)
    report = auditor.run_final_audit()

    assert report.metrics.total_nodes > 0
    assert report.metrics.total_relations > 0
    assert report.metrics.lineage_traceability_rate >= 90.0
    assert report.metrics.multi_hop_test_success_rate >= 90.0
    assert report.metrics.sign_off_status == "PRODUCTION-READY"

    # Export reports
    json_path, md_path = auditor.export_reports(report, output_dir=tmp_path)
    assert json_path.exists()
    assert md_path.exists()

    store.close()
