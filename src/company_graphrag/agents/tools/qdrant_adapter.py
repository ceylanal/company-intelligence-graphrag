"""Adapter for Qdrant vector retrieval operations converting raw hits to EvidenceItems."""

from company_graphrag.agents.schema import EvidenceItem
from company_graphrag.retrieval.models import SearchHit, SearchQuery
from company_graphrag.retrieval.vector_retriever import VectorRetriever


class QdrantToolAdapter:
    """Adapter mediating vector search operations without exposing raw Qdrant client handles."""

    def __init__(self, retriever: VectorRetriever | None = None):
        self._retriever = retriever or VectorRetriever()

    def search(
        self,
        query: str,
        top_k: int = 5,
        company: str | None = None,
        ticker: str | None = None,
        year: int | None = None,
        report_type: str | None = None,
        score_threshold: float | None = None,
    ) -> list[EvidenceItem]:
        """Execute vector search and convert SearchHits into EvidenceItems."""
        search_query = SearchQuery(
            query=query,
            top_k=top_k,
            company=company,
            ticker=ticker,
            year=year,
            report_type=report_type,
            score_threshold=score_threshold,
        )
        response = self._retriever.retrieve(search_query)

        evidence_items: list[EvidenceItem] = []
        for hit in response.hits:
            item = self._convert_hit_to_evidence(hit)
            evidence_items.append(item)

        return evidence_items

    def fetch_chunk_by_id(self, chunk_id: str) -> EvidenceItem | None:
        """Fetch a specific chunk by ID."""
        # Use retriever's vector storage or search
        response = self._retriever.retrieve(SearchQuery(query=chunk_id, top_k=10))
        for hit in response.hits:
            if hit.chunk_id == chunk_id:
                return self._convert_hit_to_evidence(hit)
        return None

    def fetch_source_context_window(self, chunk_id: str, window: int = 1) -> tuple[EvidenceItem | None, list[EvidenceItem]]:
        """Fetch target chunk and surrounding window chunks."""
        target = self.fetch_chunk_by_id(chunk_id)
        if not target:
            return None, []

        # Search for adjacent chunks with same ticker and year
        response = self._retriever.retrieve(
            SearchQuery(
                query=target.company,
                top_k=20,
                ticker=target.ticker,
                year=target.year,
            )
        )
        surrounding = [
            self._convert_hit_to_evidence(hit)
            for hit in response.hits
            if hit.chunk_id != chunk_id and abs(hit.page_number - target.page_number) <= window
        ]
        return target, surrounding

    @staticmethod
    def _convert_hit_to_evidence(hit: SearchHit) -> EvidenceItem:
        """Convert a SearchHit into unified EvidenceItem with full provenance."""
        return EvidenceItem(
            company=hit.company or "Unknown Company",
            ticker=hit.ticker or "UNKNOWN",
            year=hit.year or 2024,
            report=hit.report_type or "annual_report",
            report_type=hit.report_type or "annual_report",
            chunk_id=hit.chunk_id,
            page_number=hit.page_number if hit.page_number and hit.page_number > 0 else 1,
            source_file=hit.source_file or f"{hit.ticker}__report.pdf",
            retrieval_method="vector_search",
            content=hit.text,
            text=hit.text,
            relevance_score=hit.final_score if hit.final_score is not None else hit.score,
            metadata={
                "original_rank": hit.original_rank,
                "reranked_rank": hit.reranked_rank,
                "vector_score": hit.vector_score,
                "document_id": hit.document_id,
                "chunk_index": hit.chunk_index,
            },
            citation_status="unverified",
        )
