"""Safe automated graph quality repair engine and Human Review Queue exporter."""

import json
from pathlib import Path

from structlog import get_logger

from company_graphrag.graph.audit.models import (
    GraphQualityReport,
    IssueCategory,
    RepairSummary,
)
from company_graphrag.storage.neo4j import Neo4jGraphStore

logger = get_logger(__name__)


class GraphQualityRepairer:
    """Performs safe, automated graph repair actions and routes ambiguous items to human review queue."""

    def __init__(self, neo4j_store: Neo4jGraphStore | None = None) -> None:
        self.neo4j_store = neo4j_store or Neo4jGraphStore()

    def repair_graph(self, report: GraphQualityReport, output_dir: Path) -> RepairSummary:
        """Execute safe repair actions for repairable issues and export review queue."""
        repaired_cnt = 0
        dangling_cnt = 0
        grounding_cnt = 0
        low_conf_cnt = 0

        human_review_items = []
        review_queue_path = output_dir / "human_review_queue.jsonl"

        for issue in report.issues:
            if issue.auto_repairable:
                if issue.category == IssueCategory.DANGLING_RELATION:
                    # Remove dangling relation
                    cypher = "MATCH ()-[r {id: $id}]->() DELETE r"
                    self.neo4j_store.run_query(cypher, {"id": issue.item_id})
                    dangling_cnt += 1
                    repaired_cnt += 1
                    issue.repaired = True

                elif issue.category == IssueCategory.DUPLICATE_RELATION:
                    # Keep one, delete duplicate relation by id
                    cypher = "MATCH ()-[r {id: $id}]->() DELETE r"
                    self.neo4j_store.run_query(cypher, {"id": issue.item_id})
                    repaired_cnt += 1
                    issue.repaired = True

                elif issue.category == IssueCategory.MISSING_GROUNDING:
                    # Patch default placeholders
                    if "node" in issue.issue_id:
                        cypher = """
                        MATCH (n {id: $id})
                        SET n.source_chunk_id = COALESCE(n.source_chunk_id, 'chunk_unknown'),
                            n.source_file = COALESCE(n.source_file, 'source_unknown.pdf'),
                            n.page_number = CASE WHEN n.page_number IS NULL OR n.page_number < 1 THEN 1 ELSE n.page_number END
                        """
                    else:
                        cypher = """
                        MATCH ()-[r {id: $id}]->()
                        SET r.source_chunk_id = COALESCE(r.source_chunk_id, 'chunk_unknown'),
                            r.source_file = COALESCE(r.source_file, 'source_unknown.pdf'),
                            r.page_number = CASE WHEN r.page_number IS NULL OR r.page_number < 1 THEN 1 ELSE r.page_number END
                        """
                    self.neo4j_store.run_query(cypher, {"id": issue.item_id})
                    grounding_cnt += 1
                    repaired_cnt += 1
                    issue.repaired = True

                elif issue.category == IssueCategory.LOW_CONFIDENCE:
                    # Soft-tag with low_confidence attribute
                    if "node" in issue.issue_id:
                        cypher = "MATCH (n {id: $id}) SET n.low_confidence_flag = true"
                    else:
                        cypher = "MATCH ()-[r {id: $id}]->() SET r.low_confidence_flag = true"
                    self.neo4j_store.run_query(cypher, {"id": issue.item_id})
                    low_conf_cnt += 1
                    repaired_cnt += 1
                    issue.repaired = True

                elif issue.category == IssueCategory.INVALID_PROPERTY:
                    cypher = "MATCH (n {id: $id}) SET n.page_number = 1"
                    self.neo4j_store.run_query(cypher, {"id": issue.item_id})
                    repaired_cnt += 1
                    issue.repaired = True
            else:
                # Ambiguous / Non-repairable: Export to Human Review Queue
                human_review_items.append(
                    {
                        "review_id": f"rev_{issue.issue_id}",
                        "category": issue.category.value,
                        "severity": issue.severity.value,
                        "item_id": issue.item_id,
                        "item_type": issue.item_type,
                        "description": issue.description,
                        "details": issue.details,
                        "recommended_action": "Manual review required by domain expert.",
                    }
                )

        # Write human review queue JSONL
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(review_queue_path, "w", encoding="utf-8") as f:
            for item in human_review_items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        summary = RepairSummary(
            repaired_issues_count=repaired_cnt,
            dangling_relations_removed=dangling_cnt,
            missing_grounding_patched=grounding_cnt,
            low_confidence_tagged=low_conf_cnt,
            human_review_queue_path=str(review_queue_path),
        )

        logger.info(
            "Graph repair completed",
            repaired_count=repaired_cnt,
            review_queue_count=len(human_review_items),
        )
        return summary
