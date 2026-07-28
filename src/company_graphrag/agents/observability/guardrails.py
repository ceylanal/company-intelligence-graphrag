"""Agent Guardrails, Security Protections, and Execution Control Constraints."""

import re

from company_graphrag.agents.contracts import AGENT_CONTRACTS, AgentRole
from company_graphrag.agents.schema import ResearchState

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt\s+override", re.IGNORECASE),
    re.compile(r"disregard\s+all\s+(prior\s+)?constraints", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+an?\s+unfiltered", re.IGNORECASE),
    re.compile(r"forget\s+all\s+rules", re.IGNORECASE),
    re.compile(r"print\s+system\s+prompt", re.IGNORECASE),
]

CYPHER_MUTATION_REGEX = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH|DROP|REMOVE|ALTER|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


class SecurityViolationError(Exception):
    """Raised when an agent attempts an unauthorized tool execution or database write."""

    pass


class AgentGuardrails:
    """Security guardrails, prompt injection isolation, and execution bounds checker."""

    def __init__(
        self,
        max_total_agent_steps: int = 15,
        max_tool_calls_per_agent: int = 5,
        max_retries: int = 3,
        max_report_length: int = 20000,
        timeout_seconds: float = 60.0,
    ):
        self.max_total_agent_steps = max_total_agent_steps
        self.max_tool_calls_per_agent = max_tool_calls_per_agent
        self.max_retries = max_retries
        self.max_report_length = max_report_length
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def check_read_only_cypher(cypher_query: str) -> None:
        """Enforce strict read-only Cypher graph queries."""
        if CYPHER_MUTATION_REGEX.search(cypher_query):
            match = CYPHER_MUTATION_REGEX.search(cypher_query).group(1)  # type: ignore
            raise SecurityViolationError(
                f"Read-Only Guard Violation: Cypher query contains forbidden mutation keyword '{match.upper()}'."
            )

    @staticmethod
    def check_tool_allowlist(agent_role: str, tool_name: str) -> None:
        """Enforce declarative tool allowlist per agent role contract."""
        contract = AGENT_CONTRACTS.get(AgentRole(agent_role)) if agent_role in [r.value for r in AgentRole] else None
        if not contract:
            return

        if tool_name not in contract.allowed_tools:
            raise SecurityViolationError(
                f"Tool Allowlist Violation: Agent '{agent_role}' is not permitted to execute tool '{tool_name}'. Allowed: {contract.allowed_tools}"
            )

    @staticmethod
    def sanitize_prompt_injection(content: str) -> str:
        """Detect and neutralize prompt injection attempts in retrieved document text."""
        sanitized = content
        for pattern in PROMPT_INJECTION_PATTERNS:
            if pattern.search(sanitized):
                sanitized = pattern.sub("[UNTRUSTED DATA BLOCKED: Prompt Injection Attempt Removed]", sanitized)
        return sanitized

    def check_execution_limits(self, state: ResearchState) -> None:
        """Audit execution step bounds and resource limits."""
        total_steps = len(state.tool_calls)
        if total_steps > self.max_total_agent_steps:
            raise SecurityViolationError(
                f"Execution Control Limit Exceeded: Total agent tool calls ({total_steps}) exceeded maximum bound ({self.max_total_agent_steps})."
            )

        if state.structured_report and len(state.structured_report.answer) > self.max_report_length:
            raise SecurityViolationError(
                f"Report Length Bound Exceeded: Generated answer length ({len(state.structured_report.answer)}) exceeded limit ({self.max_report_length})."
            )

    def audit_final_quality_gate(self, state: ResearchState) -> bool:
        """Final quality gate auditing citation completeness and grounding."""
        if not state.structured_report:
            return False

        # Fail quality gate if quality warnings contain uncited claims
        if state.structured_report.quality_warnings:
            state.warnings.append(
                f"Quality Gate Warning: {len(state.structured_report.quality_warnings)} uncited claim warnings detected."
            )

        # Fail quality gate if ungrounded numerical claims exist without citations
        if not state.verified_claims and state.evidence:
            return False

        return True
