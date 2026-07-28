"""Typed Agent Tool implementations for search, graph traversal, and metadata inspection."""

from typing import Any

from company_graphrag.agents.schema import EvidenceItem
from company_graphrag.agents.tools.base import BaseTool, sort_evidence_deterministically
from company_graphrag.agents.tools.models import (
    FetchChunkInput,
    FetchChunkOutput,
    FetchSourceContextInput,
    FetchSourceContextOutput,
    GraphSearchInput,
    GraphSearchOutput,
    HybridSearchInput,
    HybridSearchOutput,
    InspectCompanyInput,
    InspectCompanyOutput,
    InspectReportInput,
    InspectReportOutput,
    VectorSearchInput,
    VectorSearchOutput,
)
from company_graphrag.agents.tools.neo4j_adapter import Neo4jToolAdapter, validate_read_only_cypher
from company_graphrag.agents.tools.qdrant_adapter import QdrantToolAdapter


class VectorSearchTool(BaseTool[VectorSearchOutput]):
    """Tool executing dense semantic retrieval against Qdrant collections."""

    name = "vector_search"
    description = "Executes dense semantic vector search over company annual reports."

    def __init__(self, qdrant_adapter: QdrantToolAdapter | None = None):
        self._adapter = qdrant_adapter or QdrantToolAdapter()

    def _run(self, input_payload: VectorSearchInput | dict[str, Any]) -> VectorSearchOutput:
        if isinstance(input_payload, dict):
            input_payload = VectorSearchInput(**input_payload)

        if not input_payload.query or not input_payload.query.strip():
            raise ValueError("Query string cannot be empty")

        top_k = min(input_payload.top_k, 50)

        hits = self._adapter.search(
            query=input_payload.query,
            top_k=top_k,
            company=input_payload.company,
            ticker=input_payload.ticker,
            year=input_payload.year,
            report_type=input_payload.report_type,
            score_threshold=input_payload.score_threshold,
        )

        sorted_hits = sort_evidence_deterministically(hits)
        return VectorSearchOutput(
            query=input_payload.query,
            hits=sorted_hits,
            total_hits=len(sorted_hits),
        )


class GraphSearchTool(BaseTool[GraphSearchOutput]):
    """Tool traversing Neo4j Knowledge Graph for multi-hop relational paths with read-only security."""

    name = "graph_search"
    description = "Traverses knowledge graph for multi-hop entity relationships and lineage."

    def __init__(self, neo4j_adapter: Neo4jToolAdapter | None = None):
        self._adapter = neo4j_adapter or Neo4jToolAdapter()

    def _run(self, input_payload: GraphSearchInput | dict[str, Any]) -> GraphSearchOutput:
        if isinstance(input_payload, dict):
            input_payload = GraphSearchInput(**input_payload)

        if input_payload.raw_query:
            validate_read_only_cypher(input_payload.raw_query)

        limit = min(input_payload.limit, 50)

        hits = self._adapter.search_paths(
            starting_ticker=input_payload.starting_ticker,
            starting_entity_ids=input_payload.starting_entity_ids,
            target_node_labels=input_payload.target_node_labels,
            year_filter=input_payload.year_filter,
            max_hops=input_payload.max_hops,
            limit=limit,
            raw_query=input_payload.raw_query,
        )

        sorted_hits = sort_evidence_deterministically(hits)
        return GraphSearchOutput(
            query=input_payload.raw_query or input_payload.starting_ticker or "Graph search",
            hits=sorted_hits,
            paths_found=len(sorted_hits),
        )


class HybridSearchTool(BaseTool[HybridSearchOutput]):
    """Tool combining vector search and graph search results with score fusion."""

    name = "hybrid_search"
    description = "Executes hybrid vector + graph search with reciprocal rank score fusion."

    def __init__(
        self,
        qdrant_adapter: QdrantToolAdapter | None = None,
        neo4j_adapter: Neo4jToolAdapter | None = None,
    ):
        self._vector_adapter = qdrant_adapter or QdrantToolAdapter()
        self._graph_adapter = neo4j_adapter or Neo4jToolAdapter()

    def _run(self, input_payload: HybridSearchInput | dict[str, Any]) -> HybridSearchOutput:
        if isinstance(input_payload, dict):
            input_payload = HybridSearchInput(**input_payload)

        top_k = min(input_payload.top_k, 50)

        vec_hits = self._vector_adapter.search(
            query=input_payload.query,
            top_k=top_k,
            company=input_payload.company,
            ticker=input_payload.ticker,
            year=input_payload.year,
            report_type=input_payload.report_type,
        )

        grp_hits = self._graph_adapter.search_paths(
            starting_ticker=input_payload.ticker,
            year_filter=input_payload.year,
            limit=top_k,
            raw_query=input_payload.query,
        )

        # Merge hits and apply weights
        combined_hits: list[EvidenceItem] = []
        seen_chunks = set()

        for item in vec_hits:
            item.relevance_score = round(item.relevance_score * input_payload.vector_weight, 4)
            combined_hits.append(item)
            seen_chunks.add(item.chunk_id)

        for item in grp_hits:
            if item.chunk_id not in seen_chunks:
                item.relevance_score = round(item.relevance_score * input_payload.graph_weight, 4)
                combined_hits.append(item)
                seen_chunks.add(item.chunk_id)

        sorted_hits = sort_evidence_deterministically(combined_hits)[:top_k]

        return HybridSearchOutput(
            query=input_payload.query,
            hits=sorted_hits,
            total_hits=len(sorted_hits),
        )


class FetchChunkTool(BaseTool[FetchChunkOutput]):
    """Tool looking up a single chunk by chunk_id."""

    name = "fetch_chunk"
    description = "Fetches specific chunk by chunk ID."

    def __init__(self, qdrant_adapter: QdrantToolAdapter | None = None):
        self._adapter = qdrant_adapter or QdrantToolAdapter()

    def _run(self, input_payload: FetchChunkInput | dict[str, Any]) -> FetchChunkOutput:
        if isinstance(input_payload, dict):
            input_payload = FetchChunkInput(**input_payload)

        if not input_payload.chunk_id or not input_payload.chunk_id.strip():
            raise ValueError("chunk_id cannot be empty")

        evidence = self._adapter.fetch_chunk_by_id(input_payload.chunk_id)
        return FetchChunkOutput(
            chunk_id=input_payload.chunk_id,
            evidence=evidence,
            found=evidence is not None,
        )


class FetchSourceContextTool(BaseTool[FetchSourceContextOutput]):
    """Tool extracting context window surrounding a target chunk."""

    name = "fetch_source_context"
    description = "Fetches surrounding context window chunks for a target chunk."

    def __init__(self, qdrant_adapter: QdrantToolAdapter | None = None):
        self._adapter = qdrant_adapter or QdrantToolAdapter()

    def _run(self, input_payload: FetchSourceContextInput | dict[str, Any]) -> FetchSourceContextOutput:
        if isinstance(input_payload, dict):
            input_payload = FetchSourceContextInput(**input_payload)

        target, surrounding = self._adapter.fetch_source_context_window(
            chunk_id=input_payload.chunk_id, window=input_payload.window
        )

        all_text_snippets = []
        if target:
            all_text_snippets.append(target.content)
        for s in surrounding:
            all_text_snippets.append(s.content)

        return FetchSourceContextOutput(
            target_chunk_id=input_payload.chunk_id,
            target_chunk=target,
            surrounding_chunks=surrounding,
            combined_text="\n\n".join(all_text_snippets),
        )


class InspectCompanyTool(BaseTool[InspectCompanyOutput]):
    """Tool inspecting company metadata, available report years, and graph nodes."""

    name = "inspect_company"
    description = "Inspects company metadata, available report years, and graph structure."

    def __init__(self, neo4j_adapter: Neo4jToolAdapter | None = None):
        self._adapter = neo4j_adapter or Neo4jToolAdapter()

    def _run(self, input_payload: InspectCompanyInput | dict[str, Any]) -> InspectCompanyOutput:
        if isinstance(input_payload, dict):
            input_payload = InspectCompanyInput(**input_payload)

        if not input_payload.ticker or not input_payload.ticker.strip():
            raise ValueError("ticker symbol cannot be empty")

        info = self._adapter.inspect_company_graph(
            ticker=input_payload.ticker.upper(), company_name=input_payload.company_name
        )

        return InspectCompanyOutput(**info)


class InspectReportTool(BaseTool[InspectReportOutput]):
    """Tool inspecting report section structure, page count, and chunk stats."""

    name = "inspect_report"
    description = "Inspects report sections, page count, and chunk stats for a given ticker and year."

    def __init__(self, neo4j_adapter: Neo4jToolAdapter | None = None):
        self._adapter = neo4j_adapter or Neo4jToolAdapter()

    def _run(self, input_payload: InspectReportInput | dict[str, Any]) -> InspectReportOutput:
        if isinstance(input_payload, dict):
            input_payload = InspectReportInput(**input_payload)

        if not input_payload.ticker or not input_payload.ticker.strip():
            raise ValueError("ticker symbol cannot be empty")

        info = self._adapter.inspect_report(
            ticker=input_payload.ticker.upper(),
            year=input_payload.year,
            report_type=input_payload.report_type,
        )

        return InspectReportOutput(**info)
