"""Researcher Agents package for Company Intelligence Multi-Agent System."""

from company_graphrag.agents.researchers.deduplicator import EvidenceDeduplicator
from company_graphrag.agents.researchers.graph_researcher import GraphResearcherAgent
from company_graphrag.agents.researchers.models import ResearcherExecutionResult
from company_graphrag.agents.researchers.vector_researcher import VectorResearcherAgent

__all__ = [
    "EvidenceDeduplicator",
    "GraphResearcherAgent",
    "ResearcherExecutionResult",
    "VectorResearcherAgent",
]
