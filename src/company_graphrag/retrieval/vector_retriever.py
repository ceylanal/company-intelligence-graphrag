"""Production Vector RAG Retriever Pipeline querying Qdrant document collection."""

import time
from typing import Any

import structlog
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from company_graphrag.config import settings
from company_graphrag.embeddings.encoder import TextEmbeddingEncoder
from company_graphrag.retrieval.models import SearchHit, SearchQuery, SearchResponse
from company_graphrag.storage.qdrant import QdrantVectorStore

logger = structlog.get_logger(__name__)


def build_retriever_filter(
    ticker: str | list[str] | None = None,
    year: int | list[int] | None = None,
    company: str | None = None,
    report_type: str | None = None,
    language: str | None = None,
) -> Filter | None:
    """Build Qdrant Filter object supporting ticker, year, company, report_type, and language."""
    must_conditions: list[Any] = []

    if ticker:
        if isinstance(ticker, str):
            must_conditions.append(FieldCondition(key="ticker", match=MatchValue(value=ticker.upper())))
        elif isinstance(ticker, list):
            must_conditions.append(FieldCondition(key="ticker", match=MatchAny(any=[t.upper() for t in ticker])))

    if year:
        if isinstance(year, int):
            must_conditions.append(FieldCondition(key="year", match=MatchValue(value=year)))
        elif isinstance(year, list):
            must_conditions.append(FieldCondition(key="year", match=MatchAny(any=year)))

    if company:
        must_conditions.append(FieldCondition(key="company", match=MatchValue(value=company)))

    if report_type:
        must_conditions.append(FieldCondition(key="report_type", match=MatchValue(value=report_type)))

    if language:
        must_conditions.append(FieldCondition(key="language", match=MatchValue(value=language.lower())))

    return Filter(must=must_conditions) if must_conditions else None


class VectorRetriever:
    """Production Vector RAG Retriever class for semantic search against Qdrant."""

    def __init__(
        self,
        encoder: TextEmbeddingEncoder | None = None,
        store: QdrantVectorStore | None = None,
        collection_name: str | None = None,
    ) -> None:
        self.encoder = encoder or TextEmbeddingEncoder()
        self.store = store or QdrantVectorStore()
        self.collection_name = collection_name or settings.qdrant_collection_name

    def close(self) -> None:
        """Close vector store connection and release locks."""
        if self.store:
            self.store.close()

    def retrieve(
        self,
        query: str | SearchQuery,
        top_k: int = 5,
        ticker: str | list[str] | None = None,
        year: int | list[int] | None = None,
        company: str | None = None,
        report_type: str | None = None,
        score_threshold: float | None = None,
    ) -> SearchResponse:
        """Execute semantic search query and return clean SearchResponse."""
        start_time = time.time()
        use_qr = False
        use_mq = False
        max_exp = 3

        if isinstance(query, SearchQuery):
            q_str = query.query
            top_k = query.top_k
            ticker = query.ticker or ticker
            year = query.year or year
            company = query.company or company
            report_type = query.report_type or report_type
            score_threshold = query.score_threshold or score_threshold
            use_qr = query.use_query_rewrite
            use_mq = query.use_multi_query
            max_exp = query.max_expanded_queries
        else:
            q_str = str(query)

        # Edge Case 1: Empty or whitespace query
        if not q_str or not q_str.strip():
            logger.warning("Empty query provided to VectorRetriever")
            return SearchResponse(
                query="",
                total_hits=0,
                hits=[],
                execution_time_ms=0.0,
            )

        q_str = q_str.strip()
        query_plan = None

        if use_qr or use_mq:
            from company_graphrag.retrieval.query_transformer import QueryTransformer

            transformer = QueryTransformer()
            query_plan = transformer.transform(
                query=q_str, explicit_ticker=ticker, explicit_year=year, max_expanded_queries=max_exp
            )
            q_str = query_plan.rewritten_query
            if not ticker and query_plan.detected_ticker:
                ticker = query_plan.detected_ticker
            if not year and query_plan.detected_year:
                year = query_plan.detected_year
            if not company and query_plan.detected_company:
                company = query_plan.detected_company

        if use_mq and query_plan and len(query_plan.expanded_queries) > 1:
            from company_graphrag.retrieval.fusion import reciprocal_rank_fusion

            multi_hits = []
            for sub_q in query_plan.expanded_queries[:max_exp]:
                sub_req = SearchQuery(
                    query=sub_q,
                    top_k=top_k,
                    ticker=ticker,
                    year=year,
                    company=company,
                    report_type=report_type,
                    score_threshold=score_threshold,
                )
                sub_resp = self.retrieve(sub_req)
                multi_hits.append(sub_resp.hits)

            fused = reciprocal_rank_fusion(
                multi_hits, expanded_queries=query_plan.expanded_queries[:max_exp], top_k=top_k
            )
            return SearchResponse(
                query=q_str,
                total_hits=len(fused),
                hits=fused,
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                query_plan=query_plan,
            )

        try:
            query_vectors = self.encoder.embed_texts([q_str])
            if not query_vectors:
                return SearchResponse(
                    query=q_str,
                    total_hits=0,
                    hits=[],
                    execution_time_ms=round((time.time() - start_time) * 1000, 2),
                )
            query_vector = query_vectors[0]
        except Exception as err:
            logger.error("Failed to generate query embedding vector", error=str(err))
            return SearchResponse(
                query=q_str,
                total_hits=0,
                hits=[],
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
            )

        q_filter = build_retriever_filter(
            ticker=ticker,
            year=year,
            company=company,
            report_type=report_type,
        )

        try:
            res = self.store.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=q_filter,
                limit=top_k,
                score_threshold=score_threshold,
                with_payload=True,
            )
            scored_points = res.points
        except Exception as err:
            logger.error("Qdrant query execution error in VectorRetriever", error=str(err))
            return SearchResponse(
                query=q_str,
                total_hits=0,
                hits=[],
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
            )

        hits: list[SearchHit] = []
        for p in scored_points:
            payload = p.payload or {}
            hit = SearchHit(
                chunk_id=payload.get("chunk_id", str(p.id)),
                text=payload.get("text", ""),
                score=round(float(p.score), 4),
                company=payload.get("company", "UNKNOWN"),
                ticker=payload.get("ticker", "UNKNOWN"),
                year=payload.get("year", 2025),
                report_type=payload.get("report_type", "annual_report"),
                page_number=payload.get("page_number", 1),
                source_file=payload.get("source_file", ""),
                document_id=payload.get("document_id", ""),
                chunk_index=payload.get("chunk_index", 0),
                language=payload.get("language", "tr"),
            )
            hits.append(hit)

        exec_time = round((time.time() - start_time) * 1000, 2)
        return SearchResponse(
            query=q_str,
            total_hits=len(hits),
            hits=hits,
            execution_time_ms=exec_time,
        )
