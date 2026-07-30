"""Grounded Answer Generation & Citation Tracking for RAG Pipeline."""

import re
import time

import httpx
import structlog

from company_graphrag.config import settings
from company_graphrag.rag.context_builder import ContextBuilder
from company_graphrag.rag.models import ContextPackage, RAGAnswer
from company_graphrag.rag.prompts import GROUNDED_RAG_SYSTEM_PROMPT, GROUNDED_RAG_USER_PROMPT_TEMPLATE
from company_graphrag.retrieval.models import SearchQuery
from company_graphrag.retrieval.vector_retriever import VectorRetriever
from company_graphrag.safety.input_guardrails import InputGuardrails
from company_graphrag.safety.output_guardrails import OutputGuardrails

logger = structlog.get_logger(__name__)


def extract_citations(answer_text: str, valid_source_numbers: set[int]) -> list[int]:
    """Extract and validate citation numbers like [Source 1], [Source 2], [1] from LLM answer."""
    raw_matches = re.findall(r"\[(?:Source\s*)?(\d+)\]", answer_text, flags=re.IGNORECASE)
    found_nums = {int(m) for m in raw_matches}
    # Keep only citations that match actual sources in context
    valid_citations = sorted(found_nums & valid_source_numbers)
    return valid_citations


def generate_mock_grounded_answer(query: str, context_package: ContextPackage) -> tuple[str, bool]:
    """Generate deterministic mock grounded answer for unit tests and fallback execution."""
    if not context_package.sources or context_package.formatted_context == "[NO RELEVANT SOURCES FOUND]":
        return "Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli bilgi bulunamadı.", True

    # Synthesize answer using top 1 or 2 sources
    src1 = context_package.sources[0]
    txt_snippet = src1.text.strip()
    if len(txt_snippet) > 150:
        txt_snippet = txt_snippet[:147] + "..."

    answer_parts = [f"{src1.company} ({src1.ticker}) {src1.year} yılı raporu verilerine göre; {txt_snippet} [Source 1]"]

    if len(context_package.sources) >= 2:
        src2 = context_package.sources[1]
        txt_snippet2 = src2.text.strip()
        if len(txt_snippet2) > 150:
            txt_snippet2 = txt_snippet2[:147] + "..."
        answer_parts.append(
            f"Ayrıca {src2.company} ({src2.ticker}) {src2.year} raporu sayfa {src2.page_number}'deki bilgilere göre; {txt_snippet2} [Source 2]"
        )

    full_answer = "\n".join(answer_parts)
    return full_answer, False


class RAGGenerator:
    """Production Grounded RAG Generator invoking LLM with strict context constraints."""

    def __init__(
        self,
        retriever: VectorRetriever | None = None,
        context_builder: ContextBuilder | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        api_key: str | None = None,
        mock_mode: bool = False,
    ) -> None:
        self.retriever = retriever or VectorRetriever()
        self.context_builder = context_builder or ContextBuilder()
        self.llm_provider = llm_provider or settings.llm_provider
        self.llm_model = llm_model or settings.llm_model
        self.api_key = api_key or settings.llm_api_key
        self.mock_mode = (
            mock_mode or (self.llm_provider == "mock") or (not self.api_key and self.llm_provider != "ollama")
        )

    def close(self) -> None:
        """Close retriever connection."""
        if self.retriever:
            self.retriever.close()

    def _call_external_llm(self, prompt: str) -> str:
        """Call external LLM API via HTTP (Gemini, OpenAI, or Ollama)."""
        if self.llm_provider == "openai":
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {
                "model": self.llm_model or "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": GROUNDED_RAG_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            }
            res = httpx.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=15.0)
            res.raise_for_status()
            data = res.json()
            return str(data["choices"][0]["message"]["content"])
        elif self.llm_provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.llm_model or 'gemini-1.5-flash'}:generateContent?key={self.api_key}"
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": f"{GROUNDED_RAG_SYSTEM_PROMPT}\n\n{prompt}"}],
                    }
                ]
            }
            res = httpx.post(url, json=payload, timeout=15.0)
            res.raise_for_status()
            data = res.json()
            return str(data["candidates"][0]["content"]["parts"][0]["text"])
        else:
            raise ValueError(f"Unsupported or unconfigured LLM provider: {self.llm_provider}")

    def generate(
        self,
        query: str | SearchQuery,
        top_k: int = 5,
        ticker: str | None = None,
        year: int | None = None,
        company: str | None = None,
        report_type: str | None = None,
        max_chars: int = 4000,
    ) -> RAGAnswer:
        """Execute RAG pipeline: Retrieve hits -> Package context -> Generate grounded answer."""
        start_time = time.time()

        if isinstance(query, SearchQuery):
            q_str = query.query
            top_k = query.top_k
            ticker = query.ticker if isinstance(query.ticker, str) else ticker
            year = query.year if isinstance(query.year, int) else year
            company = query.company or company
            report_type = query.report_type or report_type
        else:
            q_str = str(query)

        raw_filters = {
            key: value
            for key, value in {
                "ticker": ticker,
                "year": year,
                "company": company,
                "report_type": report_type,
            }.items()
            if value is not None
        }
        input_result = InputGuardrails().evaluate(q_str, filters=raw_filters or None)
        if input_result.blocked:
            return RAGAnswer(
                query="",
                answer="Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli bilgi bulunamadı.",
                citations=[],
                sources=[],
                used_source_count=0,
                insufficient_context=True,
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
                fallback_used=True,
                fallback_reason="input_guardrail_block",
            )
        q_str = input_result.question
        if input_result.filters is not None:
            ticker = input_result.filters.ticker if isinstance(input_result.filters.ticker, str) else ticker
            year = input_result.filters.year if isinstance(input_result.filters.year, int) else year
            company = input_result.filters.company
            report_type = input_result.filters.report_type

        # Step 1: Retrieve search hits
        search_hits = self.retriever.retrieve(
            query=q_str,
            top_k=top_k,
            ticker=ticker,
            year=year,
            company=company,
            report_type=report_type,
        )

        # Step 2: Package context
        context_pkg = self.context_builder.build_context(search_hits, query=q_str, max_chars=max_chars)

        # Check Insufficient Context Condition
        insufficient_phrase = "Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli bilgi bulunamadı."
        if context_pkg.total_sources == 0 or context_pkg.formatted_context == "[NO RELEVANT SOURCES FOUND]":
            return RAGAnswer(
                query=q_str,
                answer=insufficient_phrase,
                citations=[],
                sources=[],
                used_source_count=0,
                insufficient_context=True,
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
            )

        user_prompt = GROUNDED_RAG_USER_PROMPT_TEMPLATE.format(
            context=context_pkg.formatted_context,
            query=q_str,
        )

        # Step 3: LLM Generation
        answer_text = ""
        is_insufficient = False
        fallback_used = False
        fallback_reason: str | None = None

        if self.mock_mode:
            answer_text, is_insufficient = generate_mock_grounded_answer(q_str, context_pkg)
        else:
            try:
                answer_text = self._call_external_llm(user_prompt)
            except Exception as err:
                fallback_used = True
                fallback_reason = type(err).__name__
                logger.error(
                    "llm_call_failed",
                    error_type=fallback_reason,
                    fallback="deterministic_grounded",
                )
                answer_text, is_insufficient = generate_mock_grounded_answer(q_str, context_pkg)

        # Check if answer indicates insufficient info
        if insufficient_phrase in answer_text:
            is_insufficient = True

        # Step 4: Extract and validate citations
        valid_source_nums = {s.source_number for s in context_pkg.sources}
        output_result = OutputGuardrails().evaluate(
            answer_text,
            valid_citations=valid_source_nums,
            retrieved_context=[source.text for source in context_pkg.sources],
        )
        answer_text = output_result.text
        citations = output_result.citations

        # Filter sources to only cited ones (or return all included sources if no citations found)
        if citations:
            cited_sources = [s for s in context_pkg.sources if s.source_number in citations]
        else:
            cited_sources = context_pkg.sources

        exec_time = round((time.time() - start_time) * 1000, 2)
        return RAGAnswer(
            query=q_str,
            answer=answer_text,
            citations=citations,
            sources=cited_sources,
            used_source_count=len(cited_sources),
            insufficient_context=is_insufficient or output_result.blocked,
            execution_time_ms=exec_time,
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
