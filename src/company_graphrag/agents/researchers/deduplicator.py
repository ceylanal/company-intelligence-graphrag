"""Evidence Deduplication component for merging evidence records without duplicates."""

from company_graphrag.agents.schema import EvidenceItem
from company_graphrag.agents.tools.base import sort_evidence_deterministically


class EvidenceDeduplicator:
    """Deduplicates EvidenceItem lists based on chunk_id or graph_path ID."""

    @staticmethod
    def deduplicate(evidence_list: list[EvidenceItem]) -> list[EvidenceItem]:
        """Deduplicate evidence items by chunk_id and path_id, preserving highest relevance score."""
        seen: dict[str, EvidenceItem] = {}

        for item in evidence_list:
            # Build unique key
            key = item.chunk_id
            if item.graph_path and isinstance(item.graph_path, dict) and item.graph_path.get("path_id"):
                key = f"graph_{item.graph_path.get('path_id')}"

            if key not in seen:
                seen[key] = item
            else:
                existing = seen[key]
                # Keep item with higher relevance score
                if item.relevance_score > existing.relevance_score:
                    seen[key] = item

        deduped = list(seen.values())
        return sort_evidence_deterministically(deduped)
