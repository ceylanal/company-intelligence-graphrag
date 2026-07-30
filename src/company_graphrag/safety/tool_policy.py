"""Fail-closed authorization and input validation for agent tool calls."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ValidationError

from company_graphrag.agents.contracts import AGENT_CONTRACTS, AgentRole
from company_graphrag.agents.tools.models import (
    FetchChunkInput,
    FetchSourceContextInput,
    GraphSearchInput,
    HybridSearchInput,
    InspectCompanyInput,
    InspectReportInput,
    ValidateCitationInput,
    VectorSearchInput,
)
from company_graphrag.safety.prompt_injection import PromptInjectionDetector


class ToolPolicyError(ValueError):
    """Raised before a prohibited tool call reaches a backend."""


@dataclass(frozen=True)
class ToolExecutionContext:
    """Caller authority and bounded company scope for one tool invocation."""

    agent_role: str | None = None
    allowed_tickers: frozenset[str] = field(default_factory=frozenset)
    allowed_companies: frozenset[str] = field(default_factory=frozenset)
    tenant_id: str | None = None


_TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "vector_search": VectorSearchInput,
    "graph_search": GraphSearchInput,
    "hybrid_search": HybridSearchInput,
    "fetch_chunk": FetchChunkInput,
    "fetch_source_context": FetchSourceContextInput,
    "validate_citation": ValidateCitationInput,
    "inspect_company": InspectCompanyInput,
    "inspect_report": InspectReportInput,
}
_READ_ONLY_TOOLS = frozenset(_TOOL_SCHEMAS)
_SHELL_PAYLOAD = re.compile(r"(?:;|&&|\|\||`|\$\(|\$\{|\n)\s*(?:curl|wget|bash|sh|zsh|python|rm|cat|nc|chmod)\b", re.I)
_PATH_TRAVERSAL = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)")
_METADATA_HOSTS = {"169.254.169.254", "metadata.google.internal", "metadata"}
_CYPHER_MUTATION = re.compile(r"\b(?:CREATE|MERGE|SET|DELETE|DETACH|DROP|REMOVE|ALTER|GRANT|REVOKE)\b", re.I)


class ToolPolicy:
    """Allow only typed read-only research tools and safe, scoped parameters."""

    def validate_call(
        self,
        tool_name: str,
        payload: BaseModel | Mapping[str, Any],
        *,
        context: ToolExecutionContext | None = None,
    ) -> BaseModel:
        """Validate tool name, schema, caller authority, and untrusted parameters."""
        if tool_name not in _READ_ONLY_TOOLS:
            raise ToolPolicyError("Tool is not allowlisted for research execution.")
        if tool_name not in _TOOL_SCHEMAS:
            raise ToolPolicyError("Write and destructive tools are denied by default.")

        payload_dict = payload.model_dump() if isinstance(payload, BaseModel) else dict(payload)
        schema = _TOOL_SCHEMAS[tool_name]
        unknown = set(payload_dict) - set(schema.model_fields)
        if unknown:
            raise ToolPolicyError("Tool payload contains unsupported parameters.")
        try:
            parsed = schema.model_validate(payload_dict)
        except ValidationError as exc:
            raise ToolPolicyError("Tool payload does not satisfy the allowed parameter schema.") from exc

        self._validate_role(tool_name, context)
        self._validate_values(payload_dict)
        if tool_name == "graph_search" and payload_dict.get("raw_query") and _CYPHER_MUTATION.search(
            str(payload_dict["raw_query"])
        ):
            raise ToolPolicyError("READ_ONLY_VIOLATION: Graph tool accepts retrieval intent only.")
        self._validate_company_scope(payload_dict, context)
        return parsed

    def validate_tool_output(self, text: str) -> bool:
        """Return False when a tool result contains second-stage injection instructions."""
        return not PromptInjectionDetector().detect(text, source="retrieved").suspicious

    @staticmethod
    def _validate_role(tool_name: str, context: ToolExecutionContext | None) -> None:
        if context is None or context.agent_role is None:
            return
        try:
            contract = AGENT_CONTRACTS[AgentRole(context.agent_role)]
        except (KeyError, ValueError) as exc:
            raise ToolPolicyError("Agent role is not authorized for tool execution.") from exc
        if tool_name not in contract.allowed_tools:
            raise ToolPolicyError("Agent role is not allowlisted for this tool.")

    def _validate_values(self, value: Any) -> None:
        if isinstance(value, Mapping):
            for nested in value.values():
                self._validate_values(nested)
        elif isinstance(value, list):
            for nested in value:
                self._validate_values(nested)
        elif isinstance(value, str):
            if _PATH_TRAVERSAL.search(value):
                raise ToolPolicyError("Path traversal is not permitted in tool parameters.")
            if _SHELL_PAYLOAD.search(value):
                raise ToolPolicyError("Shell or command injection syntax is not permitted.")
            self._validate_url(value)

    @staticmethod
    def _validate_url(value: str) -> None:
        for candidate in re.findall(r"https?://[^\s]+", value, flags=re.I):
            parsed = urlparse(candidate)
            host = (parsed.hostname or "").rstrip(".").lower()
            if not host:
                continue
            if host in _METADATA_HOSTS or host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
                raise ToolPolicyError("Internal and metadata endpoint access is prohibited.")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                continue
            if address.is_loopback or address.is_link_local or address.is_private or address.is_reserved:
                raise ToolPolicyError("Internal and metadata endpoint access is prohibited.")

    @staticmethod
    def _validate_company_scope(payload: Mapping[str, Any], context: ToolExecutionContext | None) -> None:
        if context is None:
            return
        allowed_tickers = {ticker.upper() for ticker in context.allowed_tickers}
        for key in ("ticker", "starting_ticker"):
            value = payload.get(key)
            if value and allowed_tickers and str(value).upper() not in allowed_tickers:
                raise ToolPolicyError("Tool request attempts to leave the authorized company scope.")
        company = payload.get("company") or payload.get("company_name")
        if company and context.allowed_companies:
            normalized = str(company).casefold()
            allowed = {item.casefold() for item in context.allowed_companies}
            if normalized not in allowed:
                raise ToolPolicyError("Tool request attempts to leave the authorized company scope.")
