"""Entity resolution and canonicalization for extracted graph entities."""

from company_graphrag.graph.resolution.models import (
    AliasRecord,
    CanonicalEntityRecord,
    EntityContext,
    MatchClass,
    ResolutionDecisionRecord,
    ResolutionMetrics,
    ResolutionRunResult,
)
from company_graphrag.graph.resolution.pipeline import EntityResolutionPipeline

__all__ = [
    "AliasRecord",
    "CanonicalEntityRecord",
    "EntityContext",
    "EntityResolutionPipeline",
    "MatchClass",
    "ResolutionDecisionRecord",
    "ResolutionMetrics",
    "ResolutionRunResult",
]
