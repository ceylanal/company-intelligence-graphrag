"""Graph Quality Auditor checking 8 graph quality dimensions without re-extracting data."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from structlog import get_logger

from company_graphrag.graph.audit.models import (
    AuditIssue,
    GraphQualityMetrics,
    GraphQualityReport,
    IssueCategory,
    IssueSeverity,
)
from company_graphrag.graph.schema import GraphSchemaManager
from company_graphrag.storage.neo4j import Neo4jGraphStore

logger = get_logger(__name__)


class GraphQualityAuditor:
    """Audits active Neo4j Graph database against 8 quality dimensions."""

    def __init__(
        self,
        neo4j_store: Neo4jGraphStore | None = None,
        schema_manager: GraphSchemaManager | None = None,
        confidence_threshold: float = 0.50,
    ) -> None:
        self.neo4j_store = neo4j_store or Neo4jGraphStore()
        self.schema_manager = schema_manager or GraphSchemaManager()
        self.confidence_threshold = confidence_threshold

    def audit_graph(self) -> GraphQualityReport:
        """Execute all 8 quality audit checks and compute summary metrics."""
        issues: list[AuditIssue] = []

        # Fetch all nodes & relations from Neo4j (or mock store)
        nodes = self._fetch_all_nodes()
        relations = self._fetch_all_relations()

        # 1. Duplicate Nodes & Relations
        dup_nodes, dup_rels = self._check_duplicates(nodes, relations)
        issues.extend(dup_nodes)
        issues.extend(dup_rels)

        # 2. Dangling Relations (Missing Source / Target Node)
        dangling = self._check_dangling_relations(nodes, relations)
        issues.extend(dangling)

        # 3. Orphan Nodes (0 Relationships)
        orphans = self._check_orphan_nodes(nodes, relations)
        issues.extend(orphans)

        # 4. Missing Grounding Lineage Metadata
        missing_grounding = self._check_missing_grounding(nodes, relations)
        issues.extend(missing_grounding)

        # 5. Schema Violations
        schema_viols = self._check_schema_violations(nodes, relations)
        issues.extend(schema_viols)

        # 6. Invalid Properties
        invalid_props = self._check_invalid_properties(nodes, relations)
        issues.extend(invalid_props)

        # 7. Conflicting Entity Information
        conflicts = self._check_conflicting_data(nodes)
        issues.extend(conflicts)

        # 8. Low Confidence Records
        low_conf = self._check_low_confidence(nodes, relations)
        issues.extend(low_conf)

        # Metrics calculation
        crit_count = sum(1 for i in issues if i.severity == IssueSeverity.CRITICAL)
        warn_count = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)

        deduction = (crit_count * 5.0) + (warn_count * 1.0)
        quality_score = max(0.0, min(100.0, round(100.0 - deduction, 2)))
        status = "PASS" if (quality_score >= 80.0 and crit_count == 0) else "FAIL"

        metrics = GraphQualityMetrics(
            total_nodes=len(nodes),
            total_relations=len(relations),
            duplicate_nodes_count=len(dup_nodes),
            duplicate_relations_count=len(dup_rels),
            dangling_relations_count=len(dangling),
            orphan_nodes_count=len(orphans),
            missing_grounding_count=len(missing_grounding),
            schema_violations_count=len(schema_viols),
            invalid_properties_count=len(invalid_props),
            conflicting_data_count=len(conflicts),
            low_confidence_count=len(low_conf),
            overall_quality_score=quality_score,
            status=status,
        )

        repairable_cnt = sum(1 for i in issues if i.auto_repairable)
        human_cnt = len(issues) - repairable_cnt

        report = GraphQualityReport(
            audit_date=datetime.now(UTC).isoformat(),
            metrics=metrics,
            issues=issues,
            human_review_required_count=human_cnt,
            repairable_count=repairable_cnt,
        )

        logger.info(
            "Completed graph quality audit",
            total_nodes=len(nodes),
            total_relations=len(relations),
            quality_score=quality_score,
            status=status,
            total_issues=len(issues),
        )
        return report

    def _fetch_all_nodes(self) -> list[dict[str, Any]]:
        """Fetch all node records from Neo4j / mock store."""
        if self.neo4j_store.mock_mode and self.neo4j_store._mock_store is not None:
            res = []
            for n in self.neo4j_store._mock_store.nodes.values():
                props = dict(n["properties"])
                props["_id"] = n["id"]
                props["_label"] = list(n["labels"])[0] if n["labels"] else "Entity"
                res.append(props)
            return res

        q = "MATCH (n) RETURN id(n) AS internal_id, n.id AS id, labels(n)[0] AS _label, properties(n) AS props"
        records = self.neo4j_store.run_query(q)
        nodes = []
        for r in records:
            p = dict(r.get("props", {}))
            p["_id"] = str(r.get("id") or r.get("internal_id"))
            p["_label"] = r.get("_label", "Entity")
            nodes.append(p)
        return nodes

    def _fetch_all_relations(self) -> list[dict[str, Any]]:
        """Fetch all relationship records from Neo4j / mock store."""
        if self.neo4j_store.mock_mode and self.neo4j_store._mock_store is not None:
            res = []
            for r in self.neo4j_store._mock_store.relationships.values():
                props = dict(r["properties"])
                props["_id"] = r["id"]
                props["_type"] = r["type"]
                props["_source_id"] = r["source_id"]
                props["_target_id"] = r["target_id"]
                res.append(props)
            return res

        q = "MATCH (source)-[r]->(target) RETURN r.id AS id, type(r) AS _type, source.id AS _source_id, target.id AS _target_id, properties(r) AS props"
        records = self.neo4j_store.run_query(q)
        rels: list[dict[str, Any]] = []
        for r in records:
            p = dict(r.get("props", {}))
            p["_id"] = str(r.get("id") or f"rel_{len(rels) + 1}")
            p["_type"] = r.get("_type", "RELATED_TO")
            p["_source_id"] = str(r.get("_source_id"))
            p["_target_id"] = str(r.get("_target_id"))
            rels.append(p)
        return rels

    def _check_duplicates(
        self, nodes: list[dict[str, Any]], relations: list[dict[str, Any]]
    ) -> tuple[list[AuditIssue], list[AuditIssue]]:
        node_issues = []
        rel_issues = []

        seen_nodes: dict[str, str] = {}
        for n in nodes:
            nid = n.get("_id") or n.get("id")
            if nid in seen_nodes:
                node_issues.append(
                    AuditIssue(
                        issue_id=f"issue_dup_node_{nid}",
                        category=IssueCategory.DUPLICATE_NODE,
                        severity=IssueSeverity.WARNING,
                        item_id=str(nid),
                        item_type=n.get("_label", "Entity"),
                        description=f"Duplicate node with ID '{nid}' detected.",
                        auto_repairable=False,
                    )
                )
            else:
                seen_nodes[str(nid)] = n.get("_label", "Entity")

        seen_rels: dict[str, str] = {}
        for r in relations:
            key = f"{r.get('_source_id')}:{r.get('_type')}:{r.get('_target_id')}"
            if key in seen_rels:
                rel_issues.append(
                    AuditIssue(
                        issue_id=f"issue_dup_rel_{r.get('_id')}",
                        category=IssueCategory.DUPLICATE_RELATION,
                        severity=IssueSeverity.WARNING,
                        item_id=str(r.get("_id")),
                        item_type=r.get("_type", "RELATION"),
                        description=f"Duplicate relationship '{key}' detected.",
                        auto_repairable=True,
                    )
                )
            else:
                seen_rels[key] = str(r.get("_id"))

        return node_issues, rel_issues

    def _check_dangling_relations(
        self, nodes: list[dict[str, Any]], relations: list[dict[str, Any]]
    ) -> list[AuditIssue]:
        issues = []
        node_ids = {str(n.get("_id") or n.get("id")) for n in nodes}

        for r in relations:
            src_id = str(r.get("_source_id"))
            tgt_id = str(r.get("_target_id"))
            missing = []
            if src_id not in node_ids:
                missing.append(f"source '{src_id}'")
            if tgt_id not in node_ids:
                missing.append(f"target '{tgt_id}'")

            if missing:
                issues.append(
                    AuditIssue(
                        issue_id=f"issue_dangling_{r.get('_id')}",
                        category=IssueCategory.DANGLING_RELATION,
                        severity=IssueSeverity.CRITICAL,
                        item_id=str(r.get("_id")),
                        item_type=r.get("_type", "RELATION"),
                        description=f"Dangling relation '{r.get('_id')}' missing {', '.join(missing)}.",
                        details={"source_id": src_id, "target_id": tgt_id},
                        auto_repairable=True,  # Safe to delete dangling edge
                    )
                )
        return issues

    def _check_orphan_nodes(self, nodes: list[dict[str, Any]], relations: list[dict[str, Any]]) -> list[AuditIssue]:
        issues = []
        connected_node_ids = set()
        for r in relations:
            connected_node_ids.add(str(r.get("_source_id")))
            connected_node_ids.add(str(r.get("_target_id")))

        for n in nodes:
            nid = str(n.get("_id") or n.get("id"))
            if nid not in connected_node_ids:
                issues.append(
                    AuditIssue(
                        issue_id=f"issue_orphan_{nid}",
                        category=IssueCategory.ORPHAN_NODE,
                        severity=IssueSeverity.WARNING,
                        item_id=nid,
                        item_type=n.get("_label", "Entity"),
                        description=f"Orphan node '{nid}' has no connecting relationship edges.",
                        auto_repairable=False,  # Needs human review or link synthesis
                    )
                )
        return issues

    def _check_missing_grounding(
        self, nodes: list[dict[str, Any]], relations: list[dict[str, Any]]
    ) -> list[AuditIssue]:
        issues = []
        placeholder_values = {"", "chunk_unknown", "source_unknown.pdf", "none", "null"}

        for n in nodes:
            nid = str(n.get("_id") or n.get("id"))
            chunk = str(n.get("source_chunk_id") or "").lower()
            file_name = str(n.get("source_file") or "").lower()
            evidence = str(n.get("evidence_text") or "").strip()

            if chunk in placeholder_values or file_name in placeholder_values or not evidence:
                issues.append(
                    AuditIssue(
                        issue_id=f"issue_grounding_node_{nid}",
                        category=IssueCategory.MISSING_GROUNDING,
                        severity=IssueSeverity.WARNING,
                        item_id=nid,
                        item_type=n.get("_label", "Entity"),
                        description=f"Node '{nid}' missing lineage grounding metadata (chunk, file, or evidence).",
                        auto_repairable=True,  # Can patch default placeholders
                    )
                )

        for r in relations:
            rid = str(r.get("_id"))
            chunk = str(r.get("source_chunk_id") or "").lower()
            file_name = str(r.get("source_file") or "").lower()

            if chunk in placeholder_values or file_name in placeholder_values:
                issues.append(
                    AuditIssue(
                        issue_id=f"issue_grounding_rel_{rid}",
                        category=IssueCategory.MISSING_GROUNDING,
                        severity=IssueSeverity.WARNING,
                        item_id=rid,
                        item_type=r.get("_type", "RELATION"),
                        description=f"Relation '{rid}' missing lineage grounding metadata.",
                        auto_repairable=True,
                    )
                )

        return issues

    def _check_schema_violations(
        self, nodes: list[dict[str, Any]], relations: list[dict[str, Any]]
    ) -> list[AuditIssue]:
        issues = []
        node_type_map = {str(n.get("_id") or n.get("id")): n.get("_label", "Entity") for n in nodes}
        schema_rels = self.schema_manager.get_relationship_types()

        for r in relations:
            rid = str(r.get("_id"))
            rtype = r.get("_type", "")
            src_type = node_type_map.get(str(r.get("_source_id")))
            tgt_type = node_type_map.get(str(r.get("_target_id")))

            if not src_type or not tgt_type:
                continue

            if rtype in schema_rels:
                errs = self.schema_manager.validate_relationship(rtype, src_type, tgt_type)
                if errs:
                    issues.append(
                        AuditIssue(
                            issue_id=f"issue_schema_rel_{rid}",
                            category=IssueCategory.SCHEMA_VIOLATION,
                            severity=IssueSeverity.CRITICAL,
                            item_id=rid,
                            item_type=rtype,
                            description=f"Schema violation on relation '{rid}': {'; '.join(errs)}",
                            auto_repairable=False,
                        )
                    )

        return issues

    def _check_invalid_properties(
        self, nodes: list[dict[str, Any]], relations: list[dict[str, Any]]
    ) -> list[AuditIssue]:
        issues = []

        for n in nodes:
            nid = str(n.get("_id") or n.get("id"))
            page = n.get("page_number")
            year = n.get("year")

            if page is not None and isinstance(page, int) and page < 1:
                issues.append(
                    AuditIssue(
                        issue_id=f"issue_invalid_page_{nid}",
                        category=IssueCategory.INVALID_PROPERTY,
                        severity=IssueSeverity.WARNING,
                        item_id=nid,
                        item_type=n.get("_label", "Entity"),
                        description=f"Node '{nid}' has invalid negative page number ({page}).",
                        auto_repairable=True,
                    )
                )

            if year is not None and isinstance(year, int) and (year < 1900 or year > 2030):
                issues.append(
                    AuditIssue(
                        issue_id=f"issue_invalid_year_{nid}",
                        category=IssueCategory.INVALID_PROPERTY,
                        severity=IssueSeverity.WARNING,
                        item_id=nid,
                        item_type=n.get("_label", "Entity"),
                        description=f"Node '{nid}' has out-of-range year ({year}).",
                        auto_repairable=False,
                    )
                )

        return issues

    def _check_conflicting_data(self, nodes: list[dict[str, Any]]) -> list[AuditIssue]:
        issues = []
        ticker_company_map: dict[str, set[str]] = {}

        for n in nodes:
            if n.get("_label") == "Company":
                t = str(n.get("ticker", "")).upper()
                name = str(n.get("name") or n.get("canonical_name", ""))
                if t and name:
                    if t not in ticker_company_map:
                        ticker_company_map[t] = set()
                    ticker_company_map[t].add(name)

        for t, names in ticker_company_map.items():
            if len(names) > 1:
                issues.append(
                    AuditIssue(
                        issue_id=f"issue_conflict_ticker_{t}",
                        category=IssueCategory.CONFLICTING_DATA,
                        severity=IssueSeverity.WARNING,
                        item_id=f"company:{t}",
                        item_type="Company",
                        description=f"Conflicting company names for ticker '{t}': {list(names)}",
                        auto_repairable=False,  # Human review required
                    )
                )

        return issues

    def _check_low_confidence(self, nodes: list[dict[str, Any]], relations: list[dict[str, Any]]) -> list[AuditIssue]:
        issues = []

        for n in nodes:
            nid = str(n.get("_id") or n.get("id"))
            conf = float(n.get("confidence", 1.0))
            if conf < self.confidence_threshold:
                issues.append(
                    AuditIssue(
                        issue_id=f"issue_low_conf_node_{nid}",
                        category=IssueCategory.LOW_CONFIDENCE,
                        severity=IssueSeverity.WARNING,
                        item_id=nid,
                        item_type=n.get("_label", "Entity"),
                        description=f"Node '{nid}' has low confidence ({conf:.2f} < {self.confidence_threshold}).",
                        auto_repairable=True,  # Soft-tag as LOW_CONFIDENCE
                    )
                )

        for r in relations:
            rid = str(r.get("_id"))
            conf = float(r.get("confidence", 1.0))
            if conf < self.confidence_threshold:
                issues.append(
                    AuditIssue(
                        issue_id=f"issue_low_conf_rel_{rid}",
                        category=IssueCategory.LOW_CONFIDENCE,
                        severity=IssueSeverity.WARNING,
                        item_id=rid,
                        item_type=r.get("_type", "RELATION"),
                        description=f"Relation '{rid}' has low confidence ({conf:.2f} < {self.confidence_threshold}).",
                        auto_repairable=True,
                    )
                )

        return issues

    def export_reports(self, report: GraphQualityReport, output_dir: Path) -> tuple[Path, Path]:
        """Save JSON report and Markdown audit report to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "graph_quality_report.json"
        md_path = output_dir / "graph_quality_report.md"

        json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        # Generate Markdown Report
        md_lines = [
            "# 📊 Graph Quality Audit & Integrity Report",
            "",
            f"**Audit Date:** `{report.audit_date}`  ",
            f"**Overall Quality Score:** `{report.metrics.overall_quality_score:.2f} / 100.0`  ",
            f"**Audit Status:** `[{report.metrics.status}]`  ",
            "",
            "## 📌 1. Graph Metrics Overview",
            "",
            "| Metric | Count / Value | Status / Condition |",
            "| :--- | :---: | :---: |",
            f"| Total Nodes | **{report.metrics.total_nodes}** | Active Nodes |",
            f"| Total Relations | **{report.metrics.total_relations}** | Active Edges |",
            f"| Duplicate Nodes | {report.metrics.duplicate_nodes_count} | {'✅ 0' if report.metrics.duplicate_nodes_count == 0 else '⚠️ Warning'} |",
            f"| Duplicate Relations | {report.metrics.duplicate_relations_count} | {'✅ 0' if report.metrics.duplicate_relations_count == 0 else '⚠️ Warning'} |",
            f"| Dangling Relations | {report.metrics.dangling_relations_count} | {'✅ 0' if report.metrics.dangling_relations_count == 0 else '❌ CRITICAL'} |",
            f"| Orphan Nodes | {report.metrics.orphan_nodes_count} | {'✅ 0' if report.metrics.orphan_nodes_count == 0 else '⚠️ Warning'} |",
            f"| Missing Grounding Metadata | {report.metrics.missing_grounding_count} | {'✅ 0' if report.metrics.missing_grounding_count == 0 else '⚠️ Warning'} |",
            f"| Schema Violations | {report.metrics.schema_violations_count} | {'✅ 0' if report.metrics.schema_violations_count == 0 else '❌ CRITICAL'} |",
            f"| Invalid Properties | {report.metrics.invalid_properties_count} | {'✅ 0' if report.metrics.invalid_properties_count == 0 else '⚠️ Warning'} |",
            f"| Conflicting Data | {report.metrics.conflicting_data_count} | {'✅ 0' if report.metrics.conflicting_data_count == 0 else '⚠️ Warning'} |",
            f"| Low Confidence Records | {report.metrics.low_confidence_count} | {'✅ 0' if report.metrics.low_confidence_count == 0 else '⚠️ Warning'} |",
            "",
            "## ⚠️ 2. Detailed Audit Issues & Action Items",
            "",
        ]

        if not report.issues:
            md_lines.append("✨ **No quality issues detected! The graph is 100% clean.**\n")
        else:
            md_lines.append("| Issue ID | Category | Severity | Item ID | Description | Auto-Repairable |")
            md_lines.append("| :--- | :--- | :---: | :--- | :--- | :---: |")
            for issue in report.issues:
                rep_str = "✅ Yes" if issue.auto_repairable else "🔍 Human Review"
                md_lines.append(
                    f"| `{issue.issue_id}` | `{issue.category}` | `{issue.severity}` | `{issue.item_id}` | {issue.description} | {rep_str} |"
                )

        md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        logger.info("Exported audit report files", json_path=str(json_path), md_path=str(md_path))

        return json_path, md_path
