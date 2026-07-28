"""Unified Hybrid Retriever combining Qdrant Vector RAG and Neo4j Graph RAG."""

import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from structlog import get_logger

from company_graphrag.graph.retrieval import MultiHopGraphRetriever
from company_graphrag.retrieval.models import SearchHit
from company_graphrag.retrieval.vector_retriever import VectorRetriever

logger = get_logger(__name__)


class RetrievalMode(StrEnum):
    """Retrieval execution mode."""

    VECTOR_ONLY = "vector_only"
    GRAPH_ONLY = "graph_only"
    HYBRID = "hybrid"
    AUTO = "auto"


class HybridSearchResultItem(BaseModel):
    """Unified result format for vector, graph, and hybrid retrieval results."""

    id: str
    text: str
    score: float = Field(ge=0, le=1)
    source_retriever: str = Field(description="'vector', 'graph', or 'fused'")
    vector_score: float | None = None
    graph_score: float | None = None
    company: str | None = None
    ticker: str | None = None
    year: int | None = None
    report_type: str | None = None
    page_number: int = 1
    source_file: str = ""
    chunk_id: str = ""
    evidence_text: str | None = None
    graph_path_summary: str | None = None


class HybridSearchResponse(BaseModel):
    """Unified response model for hybrid vector + graph search."""

    query: str
    mode_requested: RetrievalMode
    mode_executed: RetrievalMode
    results: list[HybridSearchResultItem] = Field(default_factory=list)
    total_results: int = 0
    vector_hits_count: int = 0
    graph_paths_count: int = 0
    execution_time_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class HybridRetriever:
    """Unified Retriever interface orchestrating Vector RAG, Graph RAG, RRF Fusion, and Fallback."""

    def __init__(
        self,
        vector_retriever: VectorRetriever | None = None,
        graph_retriever: MultiHopGraphRetriever | None = None,
    ) -> None:
        self.vector_retriever = vector_retriever or VectorRetriever()
        self.graph_retriever = graph_retriever or MultiHopGraphRetriever()

    def determine_retrieval_mode(self, query: str) -> RetrievalMode:
        """Auto-route query to vector, graph, or hybrid based on question semantics."""
        q_lower = query.lower()

        # Purely structural / relationship questions -> GRAPH_ONLY
        graph_indicators = [
            "ürünleri nelerdir",
            "yöneticileri kimlerdir",
            "aynı sektördeki",
            "rakipleri kimlerdir",
            "sektördeki diğer",
            "hangi şirketler aynı",
        ]
        if any(ind in q_lower for ind in graph_indicators) and not any(
            w in q_lower for w in ["açıkla", "neden", "strateji"]
        ):
            return RetrievalMode.GRAPH_ONLY

        # Purely narrative / explanatory questions -> VECTOR_ONLY
        vector_indicators = [
            "açıkla",
            "neden",
            "nasıl bir strateji",
            "sürdürülebilirlik yaklaşımı",
            "vizyonu nedir",
            "değerlendirmesi",
            "özetle",
        ]
        if any(ind in q_lower for ind in vector_indicators) and not any(
            w in q_lower for w in ["ciro", "ürün", "yönetici"]
        ):
            return RetrievalMode.VECTOR_ONLY

        # Default for complex/multi-domain questions -> HYBRID
        return RetrievalMode.HYBRID

    def search(
        self,
        query: str,
        mode: RetrievalMode = RetrievalMode.AUTO,
        top_k: int = 5,
        score_threshold: float | None = None,
        company: str | None = None,
        ticker: str | None = None,
        year: int | None = None,
        report_type: str | None = None,
        max_hops: int | None = None,
    ) -> HybridSearchResponse:
        """Execute hybrid search combining Vector RAG and Graph RAG with safe fallback."""
        t_start = time.time()
        warnings: list[str] = []

        executed_mode = mode
        if mode == RetrievalMode.AUTO:
            executed_mode = self.determine_retrieval_mode(query)

        vector_hits: list[SearchHit] = []
        graph_results: list[Any] = []

        # 1. Execute Vector Retrieval if mode is vector_only, hybrid, or auto
        if executed_mode in (RetrievalMode.VECTOR_ONLY, RetrievalMode.HYBRID):
            try:
                v_res = self.vector_retriever.retrieve(
                    query=query,
                    top_k=top_k * 2 if executed_mode == RetrievalMode.HYBRID else top_k,
                    score_threshold=score_threshold,
                    company=company,
                    ticker=ticker,
                    year=year,
                    report_type=report_type,
                )
                vector_hits = v_res.hits
            except Exception as err:
                logger.warning("Vector retrieval failed during hybrid search", error=str(err))
                warnings.append(f"Vector retrieval warning: {err}")

        # 2. Execute Graph Retrieval if mode is graph_only, hybrid, or auto
        if executed_mode in (RetrievalMode.GRAPH_ONLY, RetrievalMode.HYBRID):
            try:
                g_res = self.graph_retriever.search(
                    query=query,
                    max_hops=max_hops,
                    limit=top_k * 2 if executed_mode == RetrievalMode.HYBRID else top_k,
                )
                graph_results = g_res.results
                if g_res.warnings:
                    warnings.extend(g_res.warnings)
            except Exception as err:
                logger.warning("Graph retrieval failed, activating fallback to vector RAG", error=str(err))
                warnings.append(f"Graph retrieval failed (fallback activated): {err}")
                # Safe Fallback to Vector RAG if Graph RAG fails
                if not vector_hits:
                    try:
                        v_res = self.vector_retriever.retrieve(
                            query=query,
                            top_k=top_k,
                            score_threshold=score_threshold,
                            company=company,
                            ticker=ticker,
                            year=year,
                            report_type=report_type,
                        )
                        vector_hits = v_res.hits
                    except Exception as v_err:
                        warnings.append(f"Vector fallback failed: {v_err}")

        # 3. Mode-specific Result Processing & RRF Fusion
        unified_items: list[HybridSearchResultItem] = []

        if executed_mode == RetrievalMode.VECTOR_ONLY or (not graph_results and vector_hits):
            for hit in vector_hits:
                unified_items.append(self._convert_vector_hit(hit))

        elif executed_mode == RetrievalMode.GRAPH_ONLY or (not vector_hits and graph_results):
            for g_item in graph_results:
                unified_items.append(self._convert_graph_result(g_item))

        else:
            # HYBRID Mode: Reciprocal Rank Fusion (RRF) & Deduplication
            unified_items = self._fuse_results_rrf(vector_hits, graph_results, top_k=top_k)

        # Apply score threshold filter if provided
        if score_threshold is not None:
            unified_items = [item for item in unified_items if item.score >= score_threshold]

        t_duration = round((time.time() - t_start) * 1000, 2)

        response = HybridSearchResponse(
            query=query,
            mode_requested=mode,
            mode_executed=executed_mode,
            results=unified_items[:top_k],
            total_results=len(unified_items),
            vector_hits_count=len(vector_hits),
            graph_paths_count=len(graph_results),
            execution_time_ms=t_duration,
            warnings=warnings,
        )

        logger.info(
            "Hybrid retrieval completed",
            mode=executed_mode.value,
            results_count=len(response.results),
            time_ms=t_duration,
        )
        return response

    def _convert_vector_hit(self, hit: SearchHit) -> HybridSearchResultItem:
        """Convert Vector SearchHit into unified HybridSearchResultItem."""
        return HybridSearchResultItem(
            id=hit.chunk_id,
            text=hit.text,
            score=hit.score,
            source_retriever="vector",
            vector_score=hit.score,
            company=hit.company,
            ticker=hit.ticker,
            year=hit.year,
            report_type=hit.report_type,
            page_number=hit.page_number,
            source_file=hit.source_file,
            chunk_id=hit.chunk_id,
            evidence_text=hit.text[:200],
        )

    def _convert_graph_result(self, g_res: Any) -> HybridSearchResultItem:
        """Convert GraphSearchResult into unified HybridSearchResultItem."""
        summary = g_res.path_summary or " ➔ ".join([n.name for n in g_res.nodes])
        chunk_id = g_res.lineage.chunk_id or f"graph_{g_res.path_id}"
        src_file = g_res.lineage.source_file or "graph_knowledge_base"

        # Attempt to extract ticker/year from nodes
        t_ticker = None
        t_year = None
        for n in g_res.nodes:
            if n.properties.get("ticker"):
                t_ticker = str(n.properties["ticker"])
            if n.properties.get("year"):
                t_year = int(n.properties["year"])

        return HybridSearchResultItem(
            id=g_res.path_id,
            text=f"[Graph Path] {summary}",
            score=g_res.relevance_score,
            source_retriever="graph",
            graph_score=g_res.relevance_score,
            ticker=t_ticker,
            year=t_year,
            page_number=g_res.lineage.page_number,
            source_file=src_file,
            chunk_id=chunk_id,
            evidence_text=g_res.lineage.evidence_text or summary,
            graph_path_summary=summary,
        )

    def _fuse_results_rrf(
        self, vector_hits: list[SearchHit], graph_results: list[Any], top_k: int, rrf_k: int = 60
    ) -> list[HybridSearchResultItem]:
        """Perform Reciprocal Rank Fusion (RRF) and deduplication across vector and graph results."""
        rrf_scores: dict[str, float] = {}
        item_map: dict[str, HybridSearchResultItem] = {}

        # 1. Score Vector Hits
        for rank, hit in enumerate(vector_hits, start=1):
            key = hit.chunk_id
            rrf_score = 1.0 / (rrf_k + rank)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + rrf_score

            if key not in item_map:
                item_map[key] = self._convert_vector_hit(hit)

        # 2. Score Graph Results & Deduplicate by Chunk ID / Path
        for rank, g_res in enumerate(graph_results, start=1):
            key = g_res.lineage.chunk_id if g_res.lineage.chunk_id != "chunk_unknown" else g_res.path_id
            rrf_score = 1.0 / (rrf_k + rank)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + rrf_score

            if key in item_map:
                # Mark as fused if item was retrieved by both vector & graph
                item_map[key].source_retriever = "fused"
                item_map[key].graph_score = g_res.relevance_score
                item_map[key].graph_path_summary = g_res.path_summary
            else:
                item_map[key] = self._convert_graph_result(g_res)

        # Normalize RRF scores to [0, 1] range for unified reporting
        max_rrf = max(rrf_scores.values()) if rrf_scores else 1.0
        fused_items: list[HybridSearchResultItem] = []

        for key, raw_score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True):
            item = item_map[key]
            item.score = round(min(1.0, raw_score / max_rrf), 4)
            fused_items.append(item)

        return fused_items

    def close(self) -> None:
        """Close retriever resources."""
        if hasattr(self.vector_retriever, "close"):
            self.vector_retriever.close()
        if hasattr(self.graph_retriever, "neo4j_store"):
            self.graph_retriever.neo4j_store.close()
