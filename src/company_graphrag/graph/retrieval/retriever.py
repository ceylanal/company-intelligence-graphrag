"""Multi-Hop Graph Retriever executing controlled Cypher traversals with relevance scoring and lineage."""

import time

from structlog import get_logger

from company_graphrag.graph.retrieval.cypher_builder import CypherQueryBuilder
from company_graphrag.graph.retrieval.intent import GraphIntentExtractor
from company_graphrag.graph.retrieval.models import (
    GraphPathEdge,
    GraphPathNode,
    GraphQueryIntent,
    GraphSearchResponse,
    GraphSearchResult,
    LineageMetadata,
)
from company_graphrag.storage.neo4j import Neo4jGraphStore

logger = get_logger(__name__)


class MultiHopGraphRetriever:
    """Retriever for executing multi-hop graph traversals with relevance scoring and lineage extraction."""

    def __init__(
        self,
        neo4j_store: Neo4jGraphStore | None = None,
        intent_extractor: GraphIntentExtractor | None = None,
        query_builder: CypherQueryBuilder | None = None,
    ) -> None:
        self.neo4j_store = neo4j_store or Neo4jGraphStore()
        self.intent_extractor = intent_extractor or GraphIntentExtractor()
        self.query_builder = query_builder or CypherQueryBuilder()

    def search(
        self,
        query: str | GraphQueryIntent,
        max_hops: int | None = None,
        limit: int = 10,
    ) -> GraphSearchResponse:
        """Execute end-to-end multi-hop graph retrieval for natural language question or GraphQueryIntent."""
        t_start = time.time()

        # 1. Intent Extraction
        if isinstance(query, GraphQueryIntent):
            intent = query
        else:
            intent = self.intent_extractor.extract_intent(query, max_hops=max_hops, limit=limit)

        # 2. Parameterized Cypher Building
        cypher_str, params = self.query_builder.build_multi_hop_query(intent)

        # 3. Query Execution against Neo4j / Mock Store
        results: list[GraphSearchResult] = []
        warnings: list[str] = []

        try:
            records = self.neo4j_store.run_query(cypher_str, params)

            # Fallback in mock mode if empty result from mock store
            if not records and self.neo4j_store.mock_mode and self.neo4j_store._mock_store is not None:
                records = self._generate_mock_fallback_paths(intent)

            # 4. Parse Path Records into GraphSearchResult
            for idx, r in enumerate(records, start=1):
                res_item = self._parse_path_record(r, intent, idx)
                if res_item:
                    results.append(res_item)

        except Exception as err:
            logger.error("Multi-hop graph retrieval failed", error=str(err), query=query)
            warnings.append(f"Graph query execution error: {err}")

        # 5. Relevance Scoring & Ranking
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        t_duration = round((time.time() - t_start) * 1000, 2)

        response = GraphSearchResponse(
            query=query if isinstance(query, str) else query.raw_query,
            intent=intent,
            results=results[:limit],
            total_paths_found=len(results),
            execution_time_ms=t_duration,
            warnings=warnings,
        )

        logger.info(
            "Multi-hop graph search completed",
            paths_found=len(results),
            time_ms=t_duration,
            hops=intent.max_hops,
        )
        return response

    def _parse_path_record(self, record: dict, intent: GraphQueryIntent, idx: int) -> GraphSearchResult | None:
        """Parse raw Cypher return record into GraphSearchResult."""
        raw_nodes = record.get("path_nodes") or record.get("nodes") or []
        raw_rels = record.get("path_rels") or record.get("rels") or []

        parsed_nodes: list[GraphPathNode] = []
        parsed_edges: list[GraphPathEdge] = []
        lineage = LineageMetadata()

        # Handle Mock or Neo4j record structures
        if isinstance(raw_nodes, list):
            for n in raw_nodes:
                if isinstance(n, dict):
                    nid = str(n.get("_id") or n.get("id") or f"node_{len(parsed_nodes) + 1}")
                    nlbl = str(n.get("_label") or n.get("label") or "Entity")
                    name = str(n.get("canonical_name") or n.get("name") or nid)
                    parsed_nodes.append(GraphPathNode(id=nid, label=nlbl, name=name, properties=dict(n)))

                    # Extract lineage metadata if present
                    if n.get("source_chunk_id") and n.get("source_chunk_id") != "chunk_unknown":
                        lineage.chunk_id = str(n["source_chunk_id"])
                    if n.get("source_file") and n.get("source_file") != "source_unknown.pdf":
                        lineage.source_file = str(n["source_file"])
                    if n.get("page_number"):
                        lineage.page_number = int(n["page_number"])
                    if n.get("evidence_text"):
                        lineage.evidence_text = str(n["evidence_text"])

        if isinstance(raw_rels, list):
            for r in raw_rels:
                if isinstance(r, dict):
                    rid = str(r.get("id") or f"edge_{len(parsed_edges) + 1}")
                    rtype = str(r.get("_type") or r.get("type") or "RELATED_TO")
                    src = str(r.get("_source_id") or r.get("source_id") or "")
                    tgt = str(r.get("_target_id") or r.get("target_id") or "")
                    parsed_edges.append(
                        GraphPathEdge(id=rid, type=rtype, source_id=src, target_id=tgt, properties=dict(r))
                    )

                    # Extract lineage from edge if present
                    if r.get("source_chunk_id"):
                        lineage.chunk_id = str(r["source_chunk_id"])
                    if r.get("source_file"):
                        lineage.source_file = str(r["source_file"])
                    if r.get("page_number"):
                        lineage.page_number = int(r["page_number"])
                    if r.get("evidence_text"):
                        lineage.evidence_text = str(r["evidence_text"])

        if not parsed_nodes:
            # Fallback if record returned start and target directly
            start = record.get("start")
            target = record.get("target")
            r_edge = record.get("r")
            if isinstance(start, dict) and isinstance(target, dict):
                s_id = str(start.get("id") or start.get("_id", "start"))
                s_lbl = str(start.get("_label", "Company"))
                s_name = str(start.get("name", s_id))
                parsed_nodes.append(GraphPathNode(id=s_id, label=s_lbl, name=s_name, properties=start))

                t_id = str(target.get("id") or target.get("_id", "target"))
                t_lbl = str(target.get("_label", "Entity"))
                t_name = str(target.get("name", t_id))
                parsed_nodes.append(GraphPathNode(id=t_id, label=t_lbl, name=t_name, properties=target))

                if isinstance(r_edge, dict):
                    r_id = str(r_edge.get("id", "rel_1"))
                    r_t = str(r_edge.get("_type", "RELATED_TO"))
                    parsed_edges.append(GraphPathEdge(id=r_id, type=r_t, source_id=s_id, target_id=t_id))

        hops = max(1, len(parsed_edges))

        # Compute Relevance Score
        score = 1.0 - (0.1 * hops)
        if intent.starting_ticker and any(intent.starting_ticker in n.id for n in parsed_nodes):
            score += 0.1
        if intent.year_filter and any(n.properties.get("year") == intent.year_filter for n in parsed_nodes):
            score += 0.1
        score = max(0.1, min(1.0, round(score, 2)))

        # Build Path Summary
        path_summary = " ➔ ".join([f"({n.name})" for n in parsed_nodes])

        return GraphSearchResult(
            path_id=f"path_{idx}",
            hops=hops,
            nodes=parsed_nodes,
            edges=parsed_edges,
            relevance_score=score,
            lineage=lineage,
            path_summary=path_summary,
        )

    def _generate_mock_fallback_paths(self, intent: GraphQueryIntent) -> list[dict]:
        """Generate path dicts from mock store for testing when Cypher path matching is empty."""
        assert self.neo4j_store._mock_store is not None
        mock = self.neo4j_store._mock_store
        records = []

        ticker = intent.starting_ticker or "ASELS"
        start_id = f"company:{ticker}"

        # Find matching node in mock store
        start_node = mock.nodes.get(start_id)
        if not start_node:
            for n in mock.nodes.values():
                if "Company" in n["labels"]:
                    start_node = n
                    break

        if not start_node:
            return []

        # 1-Hop / 2-Hop edges from start node
        connected_edges = [e for e in mock.relationships.values() if e["source_id"] == start_node["id"]]

        for _idx, edge in enumerate(connected_edges[: intent.limit], start=1):
            target_node = mock.nodes.get(edge["target_id"])
            if target_node:
                records.append(
                    {
                        "path_nodes": [
                            {
                                "_id": start_node["id"],
                                "_label": list(start_node["labels"])[0],
                                **start_node["properties"],
                            },
                            {
                                "_id": target_node["id"],
                                "_label": list(target_node["labels"])[0],
                                **target_node["properties"],
                            },
                        ],
                        "path_rels": [
                            {
                                "id": edge["id"],
                                "_type": edge["type"],
                                "_source_id": edge["source_id"],
                                "_target_id": edge["target_id"],
                                **edge["properties"],
                            }
                        ],
                    }
                )

        return records
