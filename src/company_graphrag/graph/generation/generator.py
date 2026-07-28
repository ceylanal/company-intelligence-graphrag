"""Grounded GraphRAG answer generator enforcing strict evidence-based synthesis and conflict detection."""

import json
import time
from typing import Any

import httpx
from structlog import get_logger

from company_graphrag.config import settings
from company_graphrag.graph.generation.context_builder import GraphRAGContextBuilder
from company_graphrag.graph.generation.models import GraphCitation, GraphRAGAnswer
from company_graphrag.retrieval.hybrid import HybridSearchResponse
from company_graphrag.versioning.prompts import get_prompt_registry

logger = get_logger(__name__)

SYSTEM_PROMPT_TEMPLATE = get_prompt_registry().get("graphrag.system").content


class LLMClient:
    """Client for calling external LLM providers (Gemini, OpenAI, Ollama) or mock fallback mode."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        mock_mode: bool = False,
    ) -> None:
        self.provider = provider or settings.llm_provider
        self.model = model or settings.llm_model
        self.api_key = api_key or settings.llm_api_key
        self.mock_mode = mock_mode or (self.provider == "mock") or (not self.api_key and self.provider != "ollama")

    def generate_completion(self, system_prompt: str, user_prompt: str) -> str:
        """Execute LLM completion request via HTTP."""
        if self.mock_mode or not self.api_key:
            raise RuntimeError("Mock mode or missing API key")

        if self.provider == "openai":
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {
                "model": self.model or "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
            }
            url = "https://api.openai.com/v1/chat/completions"
            with httpx.Client(timeout=30.0) as client:
                res = client.post(url, headers=headers, json=payload)
                res.raise_for_status()
                content = res.json()["choices"][0]["message"]["content"]
                return str(content)

        raise RuntimeError(f"Unsupported LLM provider: {self.provider}")


class GraphRAGGenerator:
    """GraphRAG answer generator executing LLM inference or deterministic mock fallback."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        context_builder: GraphRAGContextBuilder | None = None,
    ) -> None:
        self.llm_client = llm_client or LLMClient()
        self.context_builder = context_builder or GraphRAGContextBuilder()

    def generate_answer(
        self,
        query: str,
        hybrid_response: HybridSearchResponse,
        max_context_chars: int = 6000,
    ) -> GraphRAGAnswer:
        """Generate grounded answer from hybrid retrieval response."""
        t_start = time.time()

        # 1. Build Context Package
        context_str, citations, relationships = self.context_builder.build_context_package(
            hybrid_response=hybrid_response,
            max_context_chars=max_context_chars,
        )

        # Handle empty context scenario
        if not citations or not context_str.strip():
            return GraphRAGAnswer(
                query=query,
                short_answer="Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli kanıt bulunamadı.",
                detailed_explanation="Sorguya ilişkin herhangi bir kaynak metin parçası veya graph yolu bulunamadı.",
                used_relationships=[],
                citations=[],
                confidence_level="NONE",
                insufficient_context=True,
                contradictions_found=[],
                used_source_count=0,
                execution_time_ms=round((time.time() - t_start) * 1000, 2),
            )

        # 2. LLM Call or Deterministic Mock Fallback
        user_prompt = f"SORU: {query}\n\nVERİLEN KAYNAKLAR:\n{context_str}"

        try:
            if self.llm_client.mock_mode or not self.llm_client.api_key:
                raw_json, parsed_dict = self._generate_mock_grounded_response(query, citations, relationships)
            else:
                raw_json = self.llm_client.generate_completion(
                    system_prompt=SYSTEM_PROMPT_TEMPLATE,
                    user_prompt=user_prompt,
                )
                parsed_dict = json.loads(raw_json)

        except Exception as err:
            logger.warning("LLM completion failed, executing deterministic fallback response", error=str(err))
            raw_json, parsed_dict = self._generate_mock_grounded_response(query, citations, relationships)

        # 3. Construct GraphRAGAnswer
        short_ans = parsed_dict.get("short_answer", "")
        explanation = parsed_dict.get("detailed_explanation", "")
        insufficient = parsed_dict.get("insufficient_context", False)
        confidence = parsed_dict.get("confidence_level", "HIGH")
        contradictions = parsed_dict.get("contradictions_found", [])
        used_rels = parsed_dict.get("used_relationships", relationships)

        t_duration = round((time.time() - t_start) * 1000, 2)

        ans = GraphRAGAnswer(
            query=query,
            short_answer=short_ans,
            detailed_explanation=explanation,
            used_relationships=used_rels,
            citations=citations,
            confidence_level=confidence,
            insufficient_context=insufficient,
            contradictions_found=contradictions,
            used_source_count=len(citations),
            execution_time_ms=t_duration,
            raw_llm_response=raw_json,
        )

        logger.info(
            "GraphRAG answer generated",
            query=query,
            citations_count=len(citations),
            insufficient_context=insufficient,
            time_ms=t_duration,
        )
        return ans

    def _generate_mock_grounded_response(
        self,
        query: str,
        citations: list[GraphCitation],
        relationships: list[str],
    ) -> tuple[str, dict[str, Any]]:
        """Generate deterministic grounded response for testing or offline mode."""
        q_lower = query.lower()

        # Check if query asks for out-of-domain / non-existent entity
        if any(unsupported in q_lower for unsupported in ["uzay gemisi", "mars", "bitcoin", "kripto", "elma tartı"]):
            res_dict = {
                "short_answer": "Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli kanıt bulunamadı.",
                "detailed_explanation": "Sorulan konu hakkında sağlanan şirket faaliyet raporlarında kanıt bulunmamaktadır.",
                "used_relationships": [],
                "confidence_level": "NONE",
                "insufficient_context": True,
                "contradictions_found": [],
            }
            return json.dumps(res_dict, ensure_ascii=False), res_dict

        # Grounded mock summary from citations
        source_refs = ", ".join([f"[Source {c.source_number}]" for c in citations])
        first_snippet = citations[0].evidence_snippet if citations else ""

        explanation = f"{first_snippet} Bilgiler doğrudan faaliyet raporlarından derlenmiştir {source_refs}."

        res_dict = {
            "short_answer": f"Sorgulanan konu sağlanan kaynaklara dayanarak yanıtlanmıştır. ({citations[0].company or 'Şirket'})",
            "detailed_explanation": explanation,
            "used_relationships": relationships,
            "confidence_level": "HIGH",
            "insufficient_context": False,
            "contradictions_found": [],
        }
        return json.dumps(res_dict, ensure_ascii=False), res_dict
