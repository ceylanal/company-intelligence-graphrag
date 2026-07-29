from scripts.qdrant_snapshot_rehearsal import snapshot_location


def test_snapshot_location_is_collection_scoped() -> None:
    assert (
        snapshot_location("company_documents_staging", "snapshot-1.snapshot")
        == "file:///qdrant/snapshots/company_documents_staging/snapshot-1.snapshot"
    )
