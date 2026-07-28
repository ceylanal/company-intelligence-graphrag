"""Context builder formatting vector chunks and graph paths into structured LLM context packages."""

from structlog import get_logger

from company_graphrag.graph.generation.models import GraphCitation
from company_graphrag.retrieval.hybrid import HybridSearchResponse

logger = get_logger(__name__)


class GraphRAGContextBuilder:
    """Formats Hybrid Search Results (Vector Chunks + Graph Paths) into structured LLM context packages."""

    def build_context_package(
        self,
        hybrid_response: HybridSearchResponse,
        max_context_chars: int = 6000,
    ) -> tuple[str, list[GraphCitation], list[str]]:
        """Construct formatted context text string, list of citations, and graph path summaries."""
        formatted_blocks: list[str] = []
        citations: list[GraphCitation] = []
        graph_relationships: list[str] = []

        total_chars = 0

        for idx, item in enumerate(hybrid_response.results, start=1):
            source_tag = item.source_retriever.upper()

            # Record graph path summary if item originated from graph or fused search
            if item.graph_path_summary:
                graph_relationships.append(item.graph_path_summary)

            # Build Citation model
            citation = GraphCitation(
                source_number=idx,
                company=item.company,
                ticker=item.ticker,
                year=item.year,
                report_type=item.report_type,
                source_file=item.source_file or "source_unknown.pdf",
                page_number=item.page_number or 1,
                chunk_id=item.chunk_id or item.id,
                evidence_snippet=item.evidence_text or item.text[:200],
            )
            citations.append(citation)

            # Construct formatted text block
            block_header = (
                f"=== [Source {idx}] ({source_tag}) ===\n"
                f"Ticker: {item.ticker or 'N/A'} | Year: {item.year or 'N/A'} | "
                f"File: {citation.source_file} (Page {citation.page_number}) | Chunk: {citation.chunk_id}\n"
            )

            if item.graph_path_summary:
                block_body = f"Graph Traversal Path: {item.graph_path_summary}\nEvidence Text: {item.text}\n"
            else:
                block_body = f"Content Snippet: {item.text}\n"

            block_text = block_header + block_body + "\n"

            if total_chars + len(block_text) > max_context_chars and idx > 1:
                logger.warning(
                    "Context char limit reached, truncating further sources",
                    idx=idx,
                    total_chars=total_chars,
                )
                break

            formatted_blocks.append(block_text)
            total_chars += len(block_text)

        context_str = "".join(formatted_blocks)
        logger.info(
            "Built GraphRAG context package",
            sources_count=len(citations),
            relationships_count=len(graph_relationships),
            total_chars=total_chars,
        )
        return context_str, citations, graph_relationships
