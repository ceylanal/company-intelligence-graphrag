"""Safe parameterized Cypher query generator enforcing allowlists and parameterized inputs."""

from typing import Any

from structlog import get_logger

from company_graphrag.graph.retrieval.intent import ALLOWED_NODE_LABELS
from company_graphrag.graph.retrieval.models import GraphQueryIntent

logger = get_logger(__name__)


class CypherQueryBuilder:
    """Generates safe, parameterized Cypher queries with strict allowlist validation."""

    def build_multi_hop_query(self, intent: GraphQueryIntent) -> tuple[str, dict[str, Any]]:
        """Construct parameterized Cypher query string and query parameters dict."""
        ticker = intent.starting_ticker
        year = intent.year_filter
        hops = intent.max_hops
        limit = intent.limit
        metric_filter = intent.metric_name_filter

        target_labels = [lbl for lbl in intent.target_node_labels if lbl in ALLOWED_NODE_LABELS]
        if not target_labels:
            target_labels = list(ALLOWED_NODE_LABELS)

        params: dict[str, Any] = {
            "ticker": ticker,
            "year": year,
            "limit": limit,
            "target_labels": target_labels,
            "metric_filter": metric_filter,
        }

        # Case 1: Competitors in same sector (2-hop)
        if "Sector" in target_labels and "Company" in target_labels and ticker:
            cypher = """
            MATCH path = (start:Company {ticker: $ticker})-[r1:OPERATES_IN]->(s:Sector)<-[r2:OPERATES_IN]-(competitor:Company)
            WHERE competitor.ticker <> $ticker
            RETURN path, nodes(path) AS path_nodes, relationships(path) AS path_rels
            LIMIT $limit
            """
            return cypher.strip(), params

        # Case 2: 1-Hop Direct Query (e.g. Products or Executive of Company)
        if hops == 1 and ticker:
            cypher = """
            MATCH path = (start:Company {ticker: $ticker})-[r]->(target)
            WHERE labels(target)[0] IN $target_labels
              AND ($year IS NULL OR target.year = $year OR r.year = $year)
            RETURN path, nodes(path) AS path_nodes, relationships(path) AS path_rels
            LIMIT $limit
            """
            return cypher.strip(), params

        # Case 3: 2-Hop Traversal Query
        if hops == 2:
            if ticker:
                cypher = """
                MATCH path = (start:Company {ticker: $ticker})-[r1]->(m)-[r2]->(target)
                WHERE labels(target)[0] IN $target_labels
                  AND ($year IS NULL OR target.year = $year OR m.year = $year OR r1.year = $year)
                RETURN path, nodes(path) AS path_nodes, relationships(path) AS path_rels
                LIMIT $limit
                """
            else:
                cypher = """
                MATCH path = (start:Company)-[r1]->(m)-[r2]->(target)
                WHERE labels(target)[0] IN $target_labels
                  AND ($year IS NULL OR target.year = $year OR m.year = $year OR r1.year = $year)
                  AND ($metric_filter IS NULL OR toLower(m.name) CONTAINS toLower($metric_filter) OR toLower(target.name) CONTAINS toLower($metric_filter))
                RETURN path, nodes(path) AS path_nodes, relationships(path) AS path_rels
                LIMIT $limit
                """
            return cypher.strip(), params

        # Case 4: 3-Hop Traversal Query (Deep Lineage / Multi-rel)
        if ticker:
            cypher = """
            MATCH path = (start:Company {ticker: $ticker})-[r1]->(m1)-[r2]->(m2)-[r3]->(target)
            WHERE labels(target)[0] IN $target_labels
              AND ($year IS NULL OR target.year = $year OR m1.year = $year OR m2.year = $year)
            RETURN path, nodes(path) AS path_nodes, relationships(path) AS path_rels
            LIMIT $limit
            """
        else:
            cypher = """
            MATCH path = (start:Company)-[r1]->(m1)-[r2]->(m2)-[r3]->(target)
            WHERE labels(target)[0] IN $target_labels
              AND ($year IS NULL OR target.year = $year OR m1.year = $year OR m2.year = $year)
            RETURN path, nodes(path) AS path_nodes, relationships(path) AS path_rels
            LIMIT $limit
            """

        return cypher.strip(), params
