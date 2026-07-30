"""RAG Context Builder for packaging vector retrieval hits into LLM-ready context."""

from collections.abc import Sequence

import structlog

from company_graphrag.rag.models import ContextPackage, SourceReference
from company_graphrag.retrieval.models import SearchHit, SearchResponse
from company_graphrag.safety.context_isolation import UNTRUSTED_CONTEXT_PREAMBLE, ContextIsolator

logger = structlog.get_logger(__name__)


def compute_text_similarity(text1: str, text2: str) -> float:
    """Compute simple Jaccard character n-gram similarity between two text snippets."""
    if not text1 or not text2:
        return 0.0
    set1 = set(text1.lower().split())
    set2 = set(text2.lower().split())
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


class ContextBuilder:
    """Builder class for deduplicating, packaging, and formatting retrieval hits for RAG prompts."""

    def __init__(
        self,
        default_max_chars: int = 4000,
        default_max_chunk_chars: int = 1200,
        deduplicate_threshold: float = 0.80,
    ) -> None:
        self.default_max_chars = default_max_chars
        self.default_max_chunk_chars = default_max_chunk_chars
        self.deduplicate_threshold = deduplicate_threshold
        self._isolator = ContextIsolator()

    def build_context(
        self,
        hits: Sequence[SearchHit] | SearchResponse,
        query: str = "",
        max_chars: int | None = None,
        max_chunk_chars: int | None = None,
        deduplicate: bool = True,
    ) -> ContextPackage:
        """Transform retrieval hits into a structured ContextPackage."""
        max_chars_limit = max_chars or self.default_max_chars
        chunk_chars_limit = max_chunk_chars or self.default_max_chunk_chars

        if isinstance(hits, SearchResponse):
            hit_list = hits.hits
            q_str = query or hits.query
        else:
            hit_list = list(hits)
            q_str = query

        isolation = self._isolator.isolate(hit_list)
        hit_list = isolation.accepted
        if not hit_list:
            no_src_text = "[NO RELEVANT SOURCES FOUND]"
            return ContextPackage(
                query=q_str,
                formatted_context=no_src_text,
                total_sources=0,
                total_characters=len(no_src_text),
                excluded_duplicates=isolation.excluded_count,
                sources=[],
            )

        seen_chunk_ids: set[str] = set()
        seen_texts: list[str] = []
        valid_sources: list[SourceReference] = []
        formatted_blocks: list[str] = []
        excluded_duplicates_count = 0
        current_char_count = 0

        source_num = 1

        for hit in hit_list:
            cid = hit.chunk_id
            txt = hit.text.strip()

            # Deduplication Check 1: Exact chunk_id duplicate
            if deduplicate and cid in seen_chunk_ids:
                excluded_duplicates_count += 1
                continue

            # Deduplication Check 2: Text Jaccard overlap check
            if deduplicate:
                is_duplicate_text = False
                for prev_txt in seen_texts:
                    sim = compute_text_similarity(txt, prev_txt)
                    if sim >= self.deduplicate_threshold:
                        is_duplicate_text = True
                        break
                if is_duplicate_text:
                    excluded_duplicates_count += 1
                    continue

            # Truncate overly long text snippets without breaking words
            if len(txt) > chunk_chars_limit:
                truncated = txt[:chunk_chars_limit].rsplit(" ", 1)[0] + "..."
            else:
                truncated = txt

            # Format source block text
            header = f"[Source {source_num}] (Score: {hit.score:.4f})"
            meta_line = (
                f"Company: {hit.company} ({hit.ticker}) | Year: {hit.year} | "
                f"Type: {hit.report_type} | Page: {hit.page_number} | "
                f"File: {hit.source_file} (Chunk ID: {hit.chunk_id})"
            )
            block_text = f"{header}\n{meta_line}\n{UNTRUSTED_CONTEXT_PREAMBLE}Text:\n{truncated}\n"

            # Check Character Budget Limit
            projected_chars = current_char_count + len(block_text) + (2 if formatted_blocks else 0)
            if formatted_blocks and projected_chars > max_chars_limit:
                logger.info(
                    "Context character budget limit reached",
                    current_chars=current_char_count,
                    max_chars=max_chars_limit,
                    sources_included=len(valid_sources),
                )
                break

            seen_chunk_ids.add(cid)
            seen_texts.append(txt)

            src_ref = SourceReference(
                source_number=source_num,
                chunk_id=hit.chunk_id,
                company=hit.company,
                ticker=hit.ticker,
                year=hit.year,
                report_type=hit.report_type,
                page_number=hit.page_number,
                source_file=hit.source_file,
                text=truncated,
                retrieval_score=hit.score,
                character_count=len(truncated),
            )
            valid_sources.append(src_ref)
            formatted_blocks.append(block_text)
            current_char_count += len(block_text)
            source_num += 1

        final_formatted_context = "\n".join(formatted_blocks)
        return ContextPackage(
            query=q_str,
            formatted_context=final_formatted_context,
            total_sources=len(valid_sources),
            total_characters=len(final_formatted_context),
            excluded_duplicates=excluded_duplicates_count + isolation.excluded_count,
            sources=valid_sources,
        )
