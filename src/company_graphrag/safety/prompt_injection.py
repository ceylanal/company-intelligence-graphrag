"""Deterministic detection of direct and retrieved prompt-injection attempts."""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum


class InjectionAction(StrEnum):
    """Actions used by the red-team corpus and context-isolation boundary."""

    ALLOW = "allow"
    BLOCK = "block"
    SANITIZE = "sanitize"
    EXCLUDE_CONTEXT = "exclude_context"
    SAFE_REFUSAL = "safe_refusal"


@dataclass(frozen=True)
class InjectionFinding:
    """One matched prompt-injection signal without retaining a payload copy."""

    code: str
    severity: str


@dataclass(frozen=True)
class InjectionDetection:
    """Normalized assessment of untrusted text."""

    action: InjectionAction
    findings: list[InjectionFinding] = field(default_factory=list)
    normalized_text: str = ""

    @property
    def suspicious(self) -> bool:
        """Return whether the text contains an instruction-like adversarial signal."""
        return bool(self.findings)


_DIRECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("instruction_override", re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b", re.I)),
    ("instruction_override_tr", re.compile(r"\bönceki\s+(?:tüm\s+)?talimatları\s+(?:yok\s+say|unut)\b", re.I)),
    ("system_prompt_exfiltration", re.compile(r"\b(?:reveal|print|show|dump|explain)\s+(?:the\s+)?system\s+prompt\b", re.I)),
    ("system_prompt_exfiltration_tr", re.compile(r"\bsistem\s+promptunu\s+(?:göster|yazdır|açıkla)\b", re.I)),
    ("role_override", re.compile(r"\b(?:developer|system)\s+message\s*:", re.I)),
    ("instruction_disregard", re.compile(r"\bdisregard\s+(?:all\s+)?(?:rules|constraints|instructions)\b", re.I)),
    ("tool_invocation", re.compile(r"\b(?:call|invoke|execute|run)\s+(?:the\s+)?(?:tool|function|cypher)\b", re.I)),
    ("tool_invocation", re.compile(r"\btool\b.{0,30}\b(?:call|invoke|execute|run|çağır|çalıştır)\b", re.I)),
    ("cypher_mutation_instruction", re.compile(r"\b(?:cypher|neo4j)\b.{0,40}\b(?:delete|detach|drop|set|create)\b", re.I)),
    ("tool_invocation_tr", re.compile(r"\b(?:aracı|tool'u|fonksiyonu)\s+(?:çağır|çalıştır|kullan)\b", re.I)),
    ("citation_fabrication", re.compile(r"\b(?:fake|invent|replace)\b.{0,50}\b(?:citation|source|url)\b", re.I)),
    ("citation_fabrication_tr", re.compile(r"\b(?:sahte|uydurma)\b.{0,50}\b(?:atıf|kaynak|url)\b", re.I)),
    ("citation_fabrication_replace", re.compile(r"\b(?:citation|atıf|kaynak)\s+yerine\b.{0,80}\b(?:url|https?)\b", re.I)),
    ("cross_company_override", re.compile(r"\b(?:use|replace with)\b.{0,60}\b(?:another|other)\s+company", re.I)),
    ("cross_company_override", re.compile(r"\b(?:another|başka)\s+(?:company|şirket)\b.{0,60}\b(?:use|kullan)\b", re.I)),
    ("financial_tampering", re.compile(r"\b(?:change|alter|inflate|replace)\b.{0,60}\b(?:revenue|profit|financial|ciro|gelir|kâr)\b", re.I)),
)
_COMPACT_SIGNALS = (
    ("instruction_override_compact", "ignorepreviousinstructions"),
    ("instruction_override_tr_compact", "oncekitalimatlariyoksay"),
    ("system_prompt_compact", "showsystemprompt"),
    ("system_prompt_tr_compact", "sistempromptunugoster"),
)
_BASE64_TOKEN = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/])")


class PromptInjectionDetector:
    """Detect encoded, Unicode-obfuscated, and plain-text instruction attempts.

    The detector is intentionally conservative: it flags imperative control
    language, not ordinary mentions of a financial report or a citation.
    Retrieved text is always assessed as untrusted data and never as authority.
    """

    def detect(self, text: str, *, source: str = "retrieved") -> InjectionDetection:
        """Assess text and select a source-aware containment action."""
        if not isinstance(text, str):
            return InjectionDetection(
                action=self._action_for_source(source, has_system_prompt_request=False),
                findings=[InjectionFinding(code="invalid_text_type", severity="high")],
            )

        normalized = self.normalize(text)
        findings = self._find(normalized)
        decoded_findings = self._find_base64_payloads(normalized)
        findings.extend(decoded_findings)
        if not findings:
            return InjectionDetection(action=InjectionAction.ALLOW, normalized_text=normalized)

        has_system_prompt_request = any("system_prompt" in finding.code for finding in findings)
        return InjectionDetection(
            action=self._action_for_source(source, has_system_prompt_request=has_system_prompt_request),
            findings=self._deduplicate(findings),
            normalized_text=normalized,
        )

    @staticmethod
    def normalize(text: str) -> str:
        """Normalize Unicode and remove invisible separators used for obfuscation."""
        normalized = unicodedata.normalize("NFKC", text)
        return "".join(char for char in normalized if unicodedata.category(char) != "Cf")

    def _find(self, text: str) -> list[InjectionFinding]:
        findings = [InjectionFinding(code=code, severity="high") for code, pattern in _DIRECT_PATTERNS if pattern.search(text)]
        compact = re.sub(r"[^\w]", "", text.casefold())
        for code, signal in _COMPACT_SIGNALS:
            if signal in compact:
                findings.append(InjectionFinding(code=code, severity="high"))
        return findings

    def _find_base64_payloads(self, text: str) -> list[InjectionFinding]:
        findings: list[InjectionFinding] = []
        for token in _BASE64_TOKEN.findall(text):
            try:
                decoded = base64.b64decode(token, validate=True).decode("utf-8")
            except (UnicodeDecodeError, binascii.Error):
                continue
            if self._find(self.normalize(decoded)):
                findings.append(InjectionFinding(code="base64_encoded_injection", severity="high"))
        return findings

    @staticmethod
    def _action_for_source(source: str, *, has_system_prompt_request: bool) -> InjectionAction:
        if source == "retrieved":
            return InjectionAction.EXCLUDE_CONTEXT
        if source == "user":
            return InjectionAction.SAFE_REFUSAL if has_system_prompt_request else InjectionAction.BLOCK
        return InjectionAction.SANITIZE

    @staticmethod
    def _deduplicate(findings: list[InjectionFinding]) -> list[InjectionFinding]:
        seen: set[str] = set()
        unique: list[InjectionFinding] = []
        for finding in findings:
            if finding.code not in seen:
                seen.add(finding.code)
                unique.append(finding)
        return unique
