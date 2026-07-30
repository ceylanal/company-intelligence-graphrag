"""Fail-closed redaction, citation validation, and grounding checks for LLM output."""

from __future__ import annotations

import re
from collections.abc import Iterable

from company_graphrag.safety.models import (
    GuardrailAction,
    GuardrailDecision,
    OutputGuardrailResult,
    aggregate_action,
    safe_error_payload,
)

SAFE_BLOCKED_ANSWER = (
    "Bu yanıt güvenlik ve kaynak doğrulama kontrollerinden geçemedi. "
    "Doğrulanmış kaynaklarla yeniden deneyin."
)
_CITATION_RE = re.compile(r"\[(?:Source\s*)?(\d+)\]", re.IGNORECASE)
_FINANCIAL_TERM_RE = re.compile(
    r"\b(?:revenue|turnover|profit|loss|ebitda|margin|debt|cash flow|market cap|"
    r"ciro|gelir|k[âa]r|zarar|fav[öo]k|marj|bor[çc]|nakit akışı|piyasa değeri|"
    r"tl|try|usd|eur|milyon|milyar)\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"(?:[%$€₺]\s*)?\b\d+(?:[.,]\d+)*(?:\s*%)?")
_SYSTEM_LEAK_RE = re.compile(
    r"(?:^|\n)\s*(?:system|developer)\s+(?:prompt|message)\s*:|"
    r"GROUNDED_RAG_SYSTEM_PROMPT|"
    r"(?:llm_api_key|neo4j_password|qdrant_api_key)\s*=",
    re.IGNORECASE,
)
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bgh[opusr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:api[_ -]?key|access[_ -]?token|auth[_ -]?token|authorization|"
        r"client[_ -]?secret|secret|password|passwd|pwd)\s*[:=]\s*"
        r"(?:['\"])?[^\s,'\";]{8,}(?:['\"])?",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|neo4j(?:\+s)?)://[^/\s:@]+:[^@\s/]+@[^\s]+", re.IGNORECASE),
)
_GROUNDING_STOPWORDS = {
    "the",
    "and",
    "for",
    "ile",
    "bir",
    "bu",
    "ve",
    "için",
    "şirket",
    "company",
    "rapor",
    "report",
    "göre",
}
_WORD_RE = re.compile(r"[\wçğıöşüÇĞİÖŞÜ]+", re.UNICODE)


class OutputGuardrails:
    """Protect public model output while preserving grounded, cited answers."""

    def evaluate(
        self,
        text: str,
        *,
        valid_citations: Iterable[int] = (),
        retrieved_context: str | Iterable[str] = (),
    ) -> OutputGuardrailResult:
        """Evaluate output and return a fail-closed public response."""
        try:
            return self._evaluate(text, set(valid_citations), retrieved_context)
        except Exception:
            decision = GuardrailDecision(
                code="output_guardrail_failure",
                action=GuardrailAction.BLOCK,
                message="Output safety validation could not be completed.",
            )
            return OutputGuardrailResult(
                action=GuardrailAction.BLOCK,
                text=SAFE_BLOCKED_ANSWER,
                decisions=[decision],
            )

    def _evaluate(
        self,
        text: str,
        valid_citations: set[int],
        retrieved_context: str | Iterable[str],
    ) -> OutputGuardrailResult:
        if not isinstance(text, str):
            raise TypeError("output must be a string")

        decisions: list[GuardrailDecision] = []
        sanitized = text
        if _SYSTEM_LEAK_RE.search(sanitized):
            decision = GuardrailDecision(
                code="internal_configuration_leak",
                action=GuardrailAction.BLOCK,
                message="Output appears to expose a system prompt or internal configuration.",
                field="text",
            )
            return OutputGuardrailResult(
                action=GuardrailAction.BLOCK,
                text=SAFE_BLOCKED_ANSWER,
                decisions=[decision],
            )

        for pattern in _SECRET_PATTERNS:
            sanitized, count = pattern.subn("[REDACTED]", sanitized)
            if count:
                decisions.append(
                    GuardrailDecision(
                        code="secret_redacted",
                        action=GuardrailAction.REDACT,
                        message=f"Sensitive credential material was redacted ({count} occurrence(s)).",
                        field="text",
                    )
                )

        cited_numbers = {int(match) for match in _CITATION_RE.findall(sanitized)}
        invalid_citations = cited_numbers - valid_citations
        if invalid_citations:
            sanitized = _CITATION_RE.sub(
                lambda match: "" if int(match.group(1)) in invalid_citations else match.group(0),
                sanitized,
            )
            decisions.append(
                GuardrailDecision(
                    code="invalid_citation_redacted",
                    action=GuardrailAction.REDACT,
                    message="Citation tags not present in retrieved context were removed.",
                    field="citations",
                )
            )

        valid_used = {int(match) for match in _CITATION_RE.findall(sanitized)} & valid_citations
        financial_claims = self._uncited_financial_claims(sanitized, valid_citations)
        if financial_claims:
            decisions.append(
                GuardrailDecision(
                    code="uncited_financial_claim",
                    action=GuardrailAction.BLOCK,
                    message="Definitive financial claims without a valid citation were blocked.",
                    field="text",
                )
            )
            return OutputGuardrailResult(
                action=GuardrailAction.BLOCK,
                text=SAFE_BLOCKED_ANSWER,
                citations=sorted(valid_used),
                decisions=decisions,
            )

        context = retrieved_context if isinstance(retrieved_context, str) else "\n".join(retrieved_context)
        if context.strip():
            ungrounded = self._find_ungrounded_claims(sanitized, context)
            if ungrounded:
                for claim in ungrounded:
                    sanitized = sanitized.replace(
                        claim,
                        f"[UYARI: Retrieved context ile doğrulanamadı] {claim}",
                        1,
                    )
                decisions.append(
                    GuardrailDecision(
                        code="outside_retrieved_context",
                        action=GuardrailAction.WARN,
                        message=f"{len(ungrounded)} claim(s) could not be lexically grounded in retrieved context.",
                        field="text",
                    )
                )

        return OutputGuardrailResult(
            action=aggregate_action(decisions),
            text=sanitized,
            citations=sorted(valid_used),
            decisions=decisions,
        )

    @staticmethod
    def _uncited_financial_claims(text: str, valid_citations: set[int]) -> list[str]:
        claims: list[str] = []
        normalized = re.sub(r"[ \t\r\f\v]+", " ", text)
        for match in re.finditer(r"(?:^|(?<=[.!?])\s+)([^.!?]+[.!?]?)", normalized):
            stripped = match.group(1).strip()
            if not stripped or stripped.startswith(("#", "**[Source", "- Dosya:", "- Alıntı:")):
                continue
            if not (_FINANCIAL_TERM_RE.search(stripped) and _NUMBER_RE.search(stripped)):
                continue
            sentence_citations = {int(value) for value in _CITATION_RE.findall(stripped)}
            # Citations at the end of a wrapped source paragraph can follow a short
            # snippet after the financial sentence. Keep the scope deliberately tight.
            trailing_scope = normalized[match.end() : match.end() + 240]
            trailing_citations = {int(value) for value in _CITATION_RE.findall(trailing_scope)}
            if not (sentence_citations | trailing_citations).intersection(valid_citations):
                claims.append(stripped)
        return claims

    @staticmethod
    def _find_ungrounded_claims(text: str, context: str) -> list[str]:
        context_tokens = {token.casefold() for token in _WORD_RE.findall(context)} - _GROUNDING_STOPWORDS
        if not context_tokens:
            return []
        results: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            stripped = sentence.strip()
            if (
                len(stripped) < 40
                or stripped.startswith(("#", "**[Source", "- Dosya:", "- Yöntem:", "- Alıntı:"))
                or _CITATION_RE.search(stripped)
            ):
                continue
            tokens = {token.casefold() for token in _WORD_RE.findall(stripped)} - _GROUNDING_STOPWORDS
            meaningful = {token for token in tokens if len(token) > 3}
            if len(meaningful) >= 4 and len(meaningful & context_tokens) / len(meaningful) < 0.2:
                results.append(stripped)
        return results

    @staticmethod
    def safe_error(error_id: str | None = None) -> dict[str, object]:
        """Return a public error payload that never includes raw exception text."""
        return safe_error_payload(error_id)
