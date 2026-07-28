"""End-to-End Vector RAG Pipeline Orchestrator with Query Rewriting, Multi-Query Fusion, and Reranking."""

import re
import time

import structlog

from company_graphrag.rag.context_builder import ContextBuilder
from company_graphrag.rag.generator import RAGGenerator, extract_citations
from company_graphrag.rag.models import VectorRAGResult
from company_graphrag.retrieval.fusion import reciprocal_rank_fusion
from company_graphrag.retrieval.models import QueryPlan, SearchQuery, SearchResponse
from company_graphrag.retrieval.query_transformer import QueryTransformer
from company_graphrag.retrieval.reranker import RetrievalReranker
from company_graphrag.retrieval.vector_retriever import VectorRetriever

logger = structlog.get_logger(__name__)


class VectorRAGPipeline:
    """Orchestrator class for end-to-end Vector RAG execution."""

    def __init__(
        self,
        retriever: VectorRetriever | None = None,
        context_builder: ContextBuilder | None = None,
        generator: RAGGenerator | None = None,
        reranker: RetrievalReranker | None = None,
        query_transformer: QueryTransformer | None = None,
    ) -> None:
        self.retriever = retriever or VectorRetriever()
        self.context_builder = context_builder or ContextBuilder()
        self.generator = generator or RAGGenerator(retriever=self.retriever, context_builder=self.context_builder)
        self.reranker = reranker or RetrievalReranker()
        self.query_transformer = query_transformer or QueryTransformer()

    def close(self) -> None:
        """Close retriever and generator resources cleanly."""
        if self.generator:
            self.generator.close()
        elif self.retriever:
            self.retriever.close()

    def run(
        self,
        query: str | SearchQuery,
        top_k: int = 5,
        candidate_k: int = 20,
        use_reranking: bool = False,
        use_query_rewrite: bool = False,
        use_multi_query: bool = False,
        max_expanded_queries: int = 3,
        diversity_weight: float = 0.2,
        score_threshold: float | None = None,
        max_context_chars: int = 4000,
        company: str | None = None,
        ticker: str | list[str] | None = None,
        year: int | list[int] | None = None,
        report_type: str | None = None,
    ) -> VectorRAGResult:
        """Execute full RAG pipeline with optional Query Rewrite, Multi-Query Fusion, and Reranking."""
        total_start = time.time()
        warnings: list[str] = []
        timings: dict[str, float] = {}

        if isinstance(query, SearchQuery):
            q_str = query.query
            top_k = query.top_k
            candidate_k = query.candidate_k or candidate_k
            use_reranking = query.use_reranking or use_reranking
            use_query_rewrite = query.use_query_rewrite or use_query_rewrite
            use_multi_query = query.use_multi_query or use_multi_query
            max_expanded_queries = query.max_expanded_queries or max_expanded_queries
            diversity_weight = query.diversity_weight or diversity_weight
            score_threshold = query.score_threshold or score_threshold
            ticker = query.ticker or ticker
            year = query.year or year
            company = query.company or company
            report_type = query.report_type or report_type
        else:
            q_str = str(query)

        # Stage 1: Query Validation
        if not q_str or not q_str.strip():
            logger.warning("Pipeline received empty query")
            no_info = "Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli bilgi bulunamadı."
            return VectorRAGResult(
                query="",
                answer=no_info,
                citations=[],
                sources=[],
                retrieved_count=0,
                used_source_count=0,
                insufficient_context=True,
                execution_time_ms=0.0,
                stage_timings_ms={"retrieval_ms": 0.0, "context_ms": 0.0, "generation_ms": 0.0, "total_ms": 0.0},
                warnings=["Empty query string provided."],
            )

        q_str = q_str.strip()
        logger.info(
            "Executing VectorRAGPipeline",
            query=q_str,
            top_k=top_k,
            candidate_k=candidate_k,
            use_reranking=use_reranking,
            use_query_rewrite=use_query_rewrite,
            use_multi_query=use_multi_query,
        )

        # Stage 1.5: Query Rewriting & Multi-Query Transformation
        query_plan: QueryPlan | None = None
        target_query = q_str
        effective_ticker = ticker
        effective_year = year
        effective_company = company

        if use_query_rewrite or use_multi_query:
            t_start = time.time()
            query_plan = self.query_transformer.transform(
                query=q_str,
                explicit_ticker=ticker,
                explicit_year=year,
                max_expanded_queries=max_expanded_queries,
            )
            timings["rewrite_ms"] = round((time.time() - t_start) * 1000, 2)
            if query_plan.warnings:
                warnings.extend(query_plan.warnings)

            # Priority Rule: Explicit CLI filters override auto-detected filters!
            if not effective_ticker and query_plan.detected_ticker:
                effective_ticker = query_plan.detected_ticker
            if not effective_year and query_plan.detected_year:
                effective_year = query_plan.detected_year
            if not effective_company and query_plan.detected_company:
                effective_company = query_plan.detected_company

            target_query = query_plan.rewritten_query

            if query_plan.is_out_of_domain:
                no_info = "Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli bilgi bulunamadı."
                timings["total_ms"] = round((time.time() - total_start) * 1000, 2)
                return VectorRAGResult(
                    query=q_str,
                    answer=no_info,
                    citations=[],
                    sources=[],
                    retrieved_count=0,
                    used_source_count=0,
                    insufficient_context=True,
                    execution_time_ms=timings["total_ms"],
                    stage_timings_ms=timings,
                    query_plan=query_plan,
                    warnings=warnings,
                )

        # Stage 2: Qdrant Retrieval & Optional RRF Multi-Query Fusion
        r_start = time.time()
        fetch_limit = candidate_k if (use_reranking or use_multi_query) else top_k
        search_response: SearchResponse

        try:
            if use_multi_query and query_plan and query_plan.expanded_queries:
                multi_results = []
                for exp_q in query_plan.expanded_queries[:max_expanded_queries]:
                    sub_res = self.retriever.retrieve(
                        query=exp_q,
                        top_k=fetch_limit,
                        score_threshold=score_threshold,
                        ticker=effective_ticker,
                        year=effective_year,
                        company=effective_company,
                        report_type=report_type,
                    )
                    multi_results.append(sub_res.hits)

                fused_hits = reciprocal_rank_fusion(
                    query_results=multi_results,
                    expanded_queries=query_plan.expanded_queries[:max_expanded_queries],
                    top_k=fetch_limit,
                )
                search_response = SearchResponse(
                    query=target_query,
                    total_hits=len(fused_hits),
                    hits=fused_hits,
                    execution_time_ms=0.0,
                    query_plan=query_plan,
                )
            else:
                search_response = self.retriever.retrieve(
                    query=target_query,
                    top_k=fetch_limit,
                    score_threshold=score_threshold,
                    ticker=effective_ticker,
                    year=effective_year,
                    company=effective_company,
                    report_type=report_type,
                )
                search_response.query_plan = query_plan
        except Exception as err:
            logger.error("Pipeline retrieval stage error", error=str(err))
            warnings.append(f"Retrieval error encountered: {err}")
            search_response = SearchResponse(query=q_str, total_hits=0, hits=[], execution_time_ms=0.0)

        timings["retrieval_ms"] = round((time.time() - r_start) * 1000, 2)
        retrieved_count = search_response.total_hits

        # Stage 2.5: Optional Reranking Stage
        if use_reranking and search_response.hits:
            rk_start = time.time()
            q_t = effective_ticker if isinstance(effective_ticker, str) else None
            q_y = effective_year if isinstance(effective_year, int) else None

            reranked_hits = self.reranker.rerank(
                query=target_query,
                candidate_hits=search_response.hits,
                top_k=top_k,
                query_ticker=q_t,
                query_year=q_y,
                diversity_weight=diversity_weight,
            )
            search_response.hits = reranked_hits
            search_response.total_hits = len(reranked_hits)
            timings["reranking_ms"] = round((time.time() - rk_start) * 1000, 2)

        # Stage 3: Context Packaging
        c_start = time.time()
        context_pkg = self.context_builder.build_context(
            search_response, query=target_query, max_chars=max_context_chars
        )
        timings["context_ms"] = round((time.time() - c_start) * 1000, 2)

        if context_pkg.excluded_duplicates > 0:
            warnings.append(f"Filtered out {context_pkg.excluded_duplicates} duplicate chunk(s).")

        if context_pkg.total_characters >= max_context_chars:
            warnings.append(f"Context character budget limit reached ({max_context_chars} max chars).")

        # Stage 4: Grounded LLM Generation
        g_start = time.time()
        insufficient_phrase = "Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli bilgi bulunamadı."

        if context_pkg.total_sources == 0 or context_pkg.formatted_context == "[NO RELEVANT SOURCES FOUND]":
            timings["generation_ms"] = 0.0
            timings["total_ms"] = round((time.time() - total_start) * 1000, 2)
            warnings.append("No relevant sources found in vector database.")

            return VectorRAGResult(
                query=q_str,
                answer=insufficient_phrase,
                citations=[],
                sources=[],
                retrieved_count=retrieved_count,
                used_source_count=0,
                insufficient_context=True,
                execution_time_ms=timings["total_ms"],
                stage_timings_ms=timings,
                query_plan=query_plan,
                warnings=warnings,
            )

        rag_ans = self.generator.generate(
            query=target_query,
            top_k=top_k,
            ticker=effective_ticker if isinstance(effective_ticker, str) else None,
            year=effective_year if isinstance(effective_year, int) else None,
            company=effective_company,
            report_type=report_type,
            max_chars=max_context_chars,
        )
        timings["generation_ms"] = round((time.time() - g_start) * 1000, 2)

        # Stage 5: Citation Validation
        valid_nums = {s.source_number for s in context_pkg.sources}
        raw_citations = extract_citations(rag_ans.answer, valid_nums)

        raw_llm_citations = [
            int(m) for m in re.findall(r"\[(?:Source\s*)?(\d+)\]", rag_ans.answer, flags=re.IGNORECASE)
        ]
        invalid_cites = set(raw_llm_citations) - valid_nums
        if invalid_cites:
            warnings.append(f"LLM generated invalid citation tag(s) {sorted(invalid_cites)} not in context.")

        timings["total_ms"] = round((time.time() - total_start) * 1000, 2)

        return VectorRAGResult(
            query=q_str,
            answer=rag_ans.answer,
            citations=raw_citations,
            sources=rag_ans.sources,
            retrieved_count=retrieved_count,
            used_source_count=rag_ans.used_source_count,
            insufficient_context=rag_ans.insufficient_context,
            execution_time_ms=timings["total_ms"],
            stage_timings_ms=timings,
            query_plan=query_plan,
            warnings=warnings,
        )
