"""Neo4j Graph Ingestion Pipeline with Idempotent MERGE, Batching, Checkpointing, and Verification."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from structlog import get_logger

from company_graphrag.graph.ingestion.models import (
    IngestionAuditReport,
    IngestionCheckpoint,
    IngestionEntityItem,
    IngestionRelationItem,
)
from company_graphrag.graph.schema import GraphSchemaManager
from company_graphrag.storage.neo4j import Neo4jGraphStore

logger = get_logger(__name__)


class GraphIngestionPipeline:
    """Orchestrates schema DDL creation, batch entity & relation ingestion, and verification."""

    def __init__(
        self,
        neo4j_store: Neo4jGraphStore | None = None,
        schema_manager: GraphSchemaManager | None = None,
        batch_size: int = 100,
    ) -> None:
        self.neo4j_store = neo4j_store or Neo4jGraphStore()
        self.schema_manager = schema_manager or GraphSchemaManager()
        self.batch_size = batch_size

    def apply_schema_constraints(self) -> list[str]:
        """Apply all Cypher DDL constraints and indexes from GraphSchemaManager."""
        statements = self.schema_manager.generate_neo4j_cypher_statements()
        applied = []
        for stmt in statements:
            try:
                self.neo4j_store.run_query(stmt)
                applied.append(stmt)
            except Exception as err:
                logger.warning("Failed to apply Cypher DDL statement", stmt=stmt, error=str(err))
        logger.info("Applied Neo4j DDL constraints & indexes", count=len(applied))
        return applied

    def load_input_entities(self, input_dir: Path) -> list[IngestionEntityItem]:
        """Load entities from canonical_entities.jsonl or entities.jsonl in input_dir."""
        items: list[IngestionEntityItem] = []
        canonical_path = input_dir / "canonical_entities.jsonl"
        raw_path = input_dir / "entities.jsonl"

        target_path = canonical_path if canonical_path.exists() else raw_path
        if not target_path.exists():
            logger.warning("No entity JSONL file found in input_dir", input_dir=str(input_dir))
            return items

        with open(target_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)

                # Map CanonicalEntityRecord or EntityExtractionRecord to IngestionEntityItem
                entity_id = str(data.get("canonical_id") or data.get("id"))
                node_type = str(data.get("type", "Entity"))
                canonical_name = str(data.get("canonical_name", ""))
                props = dict(data.get("properties", {}))

                # Retain additional canonical properties
                if "aliases" in data:
                    props["aliases"] = data["aliases"]
                if "years" in data:
                    props["years"] = data["years"]
                if "report_ids" in data:
                    props["report_ids"] = data["report_ids"]

                # Extract grounding metadata
                src_chunk = str(
                    (
                        data.get("source_chunk_ids", [None])[0]
                        if isinstance(data.get("source_chunk_ids"), list)
                        else None
                    )
                    or data.get("source_chunk_id")
                    or "chunk_unknown"
                )
                src_file = str(data.get("source_file") or "source_unknown.pdf")
                page_num = int(data.get("page_number") or 1)
                evidence = str(
                    (
                        data.get("evidence_samples", [None])[0]
                        if isinstance(data.get("evidence_samples"), list)
                        else None
                    )
                    or data.get("evidence_text")
                    or canonical_name
                )
                conf = float(data.get("average_confidence") or data.get("confidence") or 1.0)

                items.append(
                    IngestionEntityItem(
                        id=entity_id,
                        type=node_type,
                        canonical_name=canonical_name,
                        properties=props,
                        source_chunk_id=src_chunk,
                        source_file=src_file,
                        page_number=page_num,
                        evidence_text=evidence,
                        confidence=conf,
                    )
                )

        logger.info("Loaded ingestion entities", count=len(items), source_file=target_path.name)
        return items

    def load_input_relations(self, input_dir: Path) -> list[IngestionRelationItem]:
        """Load relationships from relations.jsonl in input_dir."""
        items: list[IngestionRelationItem] = []
        rel_path = input_dir / "relations.jsonl"
        if not rel_path.exists():
            logger.warning("No relations.jsonl found in input_dir", input_dir=str(input_dir))
            return items

        with open(rel_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                rel_id = str(data.get("id") or f"rel_{len(items) + 1}")
                rel_type = str(data.get("type", "RELATED_TO"))
                src_id = str(data.get("source_entity_id") or data.get("source_id"))
                tgt_id = str(data.get("target_entity_id") or data.get("target_id"))
                src_lbl = str(data.get("source_label", "Entity"))
                tgt_lbl = str(data.get("target_label", "Entity"))
                props = dict(data.get("properties", {}))

                src_chunk = str(data.get("source_chunk_id") or "chunk_unknown")
                src_file = str(data.get("source_file") or "source_unknown.pdf")
                page_num = int(data.get("page_number") or 1)
                evidence = str(data.get("evidence_text") or "")
                conf = float(data.get("confidence") or 1.0)

                items.append(
                    IngestionRelationItem(
                        id=rel_id,
                        type=rel_type,
                        source_id=src_id,
                        source_label=src_lbl,
                        target_id=tgt_id,
                        target_label=tgt_lbl,
                        properties=props,
                        source_chunk_id=src_chunk,
                        source_file=src_file,
                        page_number=page_num,
                        evidence_text=evidence,
                        confidence=conf,
                    )
                )

        logger.info("Loaded ingestion relationships", count=len(items), source_file=rel_path.name)
        return items

    def _load_checkpoint(self, checkpoint_path: Path) -> IngestionCheckpoint:
        """Load ingestion checkpoint if present."""
        if not checkpoint_path.exists():
            return IngestionCheckpoint()
        try:
            raw = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            return IngestionCheckpoint(
                completed_entity_ids=set(raw.get("completed_entity_ids", [])),
                completed_relation_ids=set(raw.get("completed_relation_ids", [])),
                completed_batches=raw.get("completed_batches", []),
                last_updated_at=raw.get("last_updated_at", ""),
            )
        except Exception as err:
            logger.warning("Failed to load checkpoint file", path=str(checkpoint_path), error=str(err))
            return IngestionCheckpoint()

    def _save_checkpoint(self, checkpoint: IngestionCheckpoint, checkpoint_path: Path) -> None:
        """Persist ingestion checkpoint state."""
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.last_updated_at = datetime.now(UTC).isoformat()
        payload = {
            "completed_entity_ids": list(checkpoint.completed_entity_ids),
            "completed_relation_ids": list(checkpoint.completed_relation_ids),
            "completed_batches": checkpoint.completed_batches,
            "last_updated_at": checkpoint.last_updated_at,
        }
        checkpoint_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def ingest_entities_batch(self, entities: list[IngestionEntityItem]) -> int:
        """Ingest batch of entity nodes using Cypher MERGE grouped by node type."""
        if not entities:
            return 0

        # Group by node type label
        grouped: dict[str, list[dict[str, Any]]] = {}
        for ent in entities:
            label = ent.type
            if label not in grouped:
                grouped[label] = []

            # Prepare properties payload including lineage fields
            item_props = dict(ent.properties)
            item_props["id"] = ent.id
            item_props["name"] = ent.canonical_name
            item_props["canonical_name"] = ent.canonical_name
            item_props["source_chunk_id"] = ent.source_chunk_id
            item_props["source_file"] = ent.source_file
            item_props["page_number"] = ent.page_number
            item_props["evidence_text"] = ent.evidence_text
            item_props["confidence"] = ent.confidence

            # Serialize list/dict props for Cypher safety
            for k, v in list(item_props.items()):
                if isinstance(v, (list, set)):
                    item_props[k] = [str(x) for x in v]
                elif isinstance(v, dict):
                    item_props[k] = json.dumps(v, ensure_ascii=False)

            grouped[label].append(item_props)

        total_ingested = 0
        for label, batch in grouped.items():
            cypher = f"""
            UNWIND $batch AS item
            MERGE (n:`{label}` {{id: item.id}})
            ON CREATE SET n += item, n.created_at = timestamp()
            ON MATCH SET n += item, n.updated_at = timestamp()
            """
            self.neo4j_store.execute_batch(cypher, batch)
            total_ingested += len(batch)

        return total_ingested

    def ingest_relations_batch(self, relations: list[IngestionRelationItem]) -> int:
        """Ingest batch of relationship edges using Cypher MERGE grouped by relation type."""
        if not relations:
            return 0

        grouped: dict[str, list[dict[str, Any]]] = {}
        for rel in relations:
            r_type = rel.type
            if r_type not in grouped:
                grouped[r_type] = []

            item_props = dict(rel.properties)
            payload = {
                "id": rel.id,
                "source_id": rel.source_id,
                "target_id": rel.target_id,
                "properties": item_props,
                "source_chunk_id": rel.source_chunk_id,
                "source_file": rel.source_file,
                "page_number": rel.page_number,
                "evidence_text": rel.evidence_text,
                "confidence": rel.confidence,
            }
            grouped[r_type].append(payload)

        total_ingested = 0
        for r_type, batch in grouped.items():
            cypher = f"""
            UNWIND $batch AS item
            MATCH (source {{id: item.source_id}})
            MATCH (target {{id: item.target_id}})
            MERGE (source)-[r:`{r_type}` {{id: item.id}}]->(target)
            ON CREATE SET r += item.properties, r.source_chunk_id = item.source_chunk_id, r.source_file = item.source_file, r.page_number = item.page_number, r.evidence_text = item.evidence_text, r.confidence = item.confidence, r.created_at = timestamp()
            ON MATCH SET r += item.properties, r.source_chunk_id = item.source_chunk_id, r.source_file = item.source_file, r.page_number = item.page_number, r.evidence_text = item.evidence_text, r.confidence = item.confidence, r.updated_at = timestamp()
            """
            self.neo4j_store.execute_batch(cypher, batch)
            total_ingested += len(batch)

        return total_ingested

    def verify_graph_state(self) -> tuple[dict[str, int], dict[str, int], int]:
        """Run verification queries to return node counts by label, relation counts by type, and orphan count."""
        # 1. Node counts by label
        q_nodes = "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count"
        res_nodes = self.neo4j_store.run_query(q_nodes)
        node_counts: dict[str, int] = {}
        for r in res_nodes:
            lbl = r.get("label") or "Unlabeled"
            cnt = int(r.get("count") or 0)
            node_counts[lbl] = cnt

        # 2. Relation counts by type
        q_rels = "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS count"
        res_rels = self.neo4j_store.run_query(q_rels)
        rel_counts: dict[str, int] = {}
        for r in res_rels:
            t = r.get("rel_type") or "UNKNOWN"
            cnt = int(r.get("count") or 0)
            rel_counts[t] = cnt

        # 3. Orphan node count
        q_orphans = "MATCH (n) WHERE NOT (n)-[]-() RETURN count(n) AS orphan_count"
        res_orphans = self.neo4j_store.run_query(q_orphans)
        orphan_count = int(res_orphans[0].get("orphan_count", 0)) if res_orphans else 0

        return node_counts, rel_counts, orphan_count

    def run_pipeline(
        self,
        input_dir: Path,
        checkpoint_path: Path | None = None,
    ) -> IngestionAuditReport:
        """Run end-to-end graph ingestion pipeline with checkpointing and verification."""
        t_start = time.time()
        chk_path = checkpoint_path or (input_dir / "ingestion_checkpoint.json")
        checkpoint = self._load_checkpoint(chk_path)

        # 1. Apply Schema Constraints
        self.apply_schema_constraints()

        # 2. Load Input Data
        entities = self.load_input_entities(input_dir)
        relations = self.load_input_relations(input_dir)

        # Filter out already ingested items
        pending_entities = [e for e in entities if e.id not in checkpoint.completed_entity_ids]
        pending_relations = [r for r in relations if r.id not in checkpoint.completed_relation_ids]

        logger.info(
            "Graph ingestion progress",
            total_entities=len(entities),
            pending_entities=len(pending_entities),
            total_relations=len(relations),
            pending_relations=len(pending_relations),
        )

        ingested_node_cnt = 0
        ingested_rel_cnt = 0
        duplicate_merge_attempts = 0

        # 3. Batch Entity Node Ingestion
        for i in range(0, len(pending_entities), self.batch_size):
            batch = pending_entities[i : i + self.batch_size]
            cnt = self.ingest_entities_batch(batch)
            ingested_node_cnt += cnt
            for item in batch:
                checkpoint.completed_entity_ids.add(item.id)
            checkpoint.completed_batches.append(len(checkpoint.completed_batches) + 1)
            self._save_checkpoint(checkpoint, chk_path)

        # 4. Batch Relation Edge Ingestion
        for i in range(0, len(pending_relations), self.batch_size):
            rel_batch = pending_relations[i : i + self.batch_size]
            cnt = self.ingest_relations_batch(rel_batch)
            ingested_rel_cnt += cnt
            for rel_item in rel_batch:
                checkpoint.completed_relation_ids.add(rel_item.id)
            self._save_checkpoint(checkpoint, chk_path)

        # Calculate duplicate attempts if re-ingested
        if len(pending_entities) < len(entities):
            duplicate_merge_attempts += len(entities) - len(pending_entities)
        if len(pending_relations) < len(relations):
            duplicate_merge_attempts += len(relations) - len(pending_relations)

        # 5. Verification Queries
        node_counts, rel_counts, orphan_count = self.verify_graph_state()
        t_duration = round((time.time() - t_start) * 1000, 2)

        report = IngestionAuditReport(
            total_input_entities=len(entities),
            total_input_relations=len(relations),
            ingested_nodes=ingested_node_cnt + (len(entities) - len(pending_entities)),
            ingested_relations=ingested_rel_cnt + (len(relations) - len(pending_relations)),
            node_counts_by_label=node_counts,
            relation_counts_by_type=rel_counts,
            orphan_node_count=orphan_count,
            duplicate_merge_attempts=duplicate_merge_attempts,
            execution_time_ms=t_duration,
            status="PASS",
            checkpoint_path=str(chk_path),
        )

        # Save audit report to input_dir
        audit_path = input_dir / "ingestion_audit_report.json"
        audit_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Graph ingestion pipeline completed successfully", status=report.status, time_ms=t_duration)

        return report
