"""Semantic search engine for retrieving relevant document chunks from Qdrant."""

import time
from typing import Any

import structlog
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from company_graphrag.config import settings
from company_graphrag.embeddings.encoder import TextEmbeddingEncoder
from company_graphrag.retrieval.models import SearchHit, SearchQuery, SearchResponse
from company_graphrag.storage.qdrant import QdrantVectorStore

logger = structlog.get_logger(__name__)


def build_qdrant_filter(
    ticker: str | list[str] | None = None,
    year: int | list[int] | None = None,
    language: str | None = None,
) -> Filter | None:
    """Build Qdrant Filter object for metadata filtering."""
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

    if language:
        must_conditions.append(FieldCondition(key="language", match=MatchValue(value=language.lower())))

    return Filter(must=must_conditions) if must_conditions else None


class VectorSearchEngine:
    """Semantic vector search engine querying Qdrant document collection."""

    def __init__(
        self,
        encoder: TextEmbeddingEncoder | None = None,
        store: QdrantVectorStore | None = None,
        collection_name: str | None = None,
    ) -> None:
        self.encoder = encoder or TextEmbeddingEncoder()
        self.store = store or QdrantVectorStore()
        self.collection_name = collection_name or settings.qdrant_collection_name

    def search(self, query_request: SearchQuery) -> SearchResponse:
        """Execute semantic search query and return formatted SearchResponse."""
        start_time = time.time()
        logger.info(
            "Executing semantic search query",
            query=query_request.query,
            top_k=query_request.top_k,
            ticker=query_request.ticker,
            year=query_request.year,
        )

        query_vectors = self.encoder.embed_texts([query_request.query])
        if not query_vectors:
            return SearchResponse(
                query=query_request.query,
                total_hits=0,
                hits=[],
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
            )

        query_vector = query_vectors[0]
        q_filter = build_qdrant_filter(
            ticker=query_request.ticker,
            year=query_request.year,
            language=query_request.language,
        )

        try:
            res = self.store.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=q_filter,
                limit=query_request.top_k,
                score_threshold=query_request.score_threshold,
                with_payload=True,
            )
            scored_points = res.points
        except Exception as err:
            logger.error("Qdrant query execution failed", error=str(err))
            raise RuntimeError(f"Search query failed on collection {self.collection_name}") from err

        hits: list[SearchHit] = []
        for p in scored_points:
            payload = p.payload or {}
            hit = SearchHit(
                score=round(float(p.score), 4),
                chunk_id=payload.get("chunk_id", str(p.id)),
                document_id=payload.get("document_id", "UNKNOWN"),
                ticker=payload.get("ticker", "UNKNOWN"),
                company=payload.get("company", "UNKNOWN"),
                year=payload.get("year", 2025),
                page_number=payload.get("page_number", 1),
                chunk_index=payload.get("chunk_index", 0),
                text=payload.get("text", ""),
                source_file=payload.get("source_file", ""),
                language=payload.get("language", "tr"),
            )
            hits.append(hit)

        exec_time = round((time.time() - start_time) * 1000, 2)
        logger.info(
            "Semantic search executed successfully",
            hits_count=len(hits),
            duration_ms=exec_time,
        )
        return SearchResponse(
            query=query_request.query,
            total_hits=len(hits),
            hits=hits,
            execution_time_ms=exec_time,
        )
