from __future__ import annotations

import pytest
from scripts.neo4j_logical_restore_rehearsal import _safe_token, graph_checksum


def test_graph_checksum_is_order_and_temp_id_independent() -> None:
    nodes = [
        {"source_id": "2", "labels": ["Company"], "properties": {"name": "B"}},
        {"source_id": "1", "labels": ["Company"], "properties": {"name": "A"}},
    ]
    relationships = [
        {
            "start_id": "1",
            "end_id": "2",
            "type": "PEER_OF",
            "properties": {"year": 2024},
        }
    ]
    restored_nodes = [
        {
            "source_id": "1",
            "labels": ["Company"],
            "properties": {"name": "A", "__dr_source_id": "1"},
        },
        {
            "source_id": "2",
            "labels": ["Company"],
            "properties": {"name": "B", "__dr_source_id": "2"},
        },
    ]

    assert graph_checksum(nodes, relationships) == graph_checksum(restored_nodes, relationships)


def test_unsafe_schema_tokens_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unsafe Neo4j label"):
        _safe_token("Company`) DETACH DELETE n //", "label")
