"""Intent extractor for parsing questions into GraphQueryIntent parameters."""

from structlog import get_logger

from company_graphrag.graph.retrieval.models import GraphQueryIntent
from company_graphrag.retrieval.query_transformer import detect_company_entity, detect_year_entity

logger = get_logger(__name__)

ALLOWED_NODE_LABELS = {
    "Company",
    "Report",
    "Product",
    "Sector",
    "FinancialMetric",
    "Person",
    "Event",
    "TimePeriod",
    "Chunk",
}

ALLOWED_RELATION_TYPES = {
    "PUBLISHED",
    "OPERATES_IN",
    "PRODUCES",
    "EXECUTIVE_AT",
    "REPORTED",
    "CONTAINS_METRIC",
    "APPLIES_TO_PERIOD",
    "PARTICIPATED_IN",
    "HAS_CHUNK",
    "SOURCED_FROM",
    "REPORTED_METRIC",
    "FOR_DATE",
    "HOLDS_ROLE_AT",
}


class GraphIntentExtractor:
    """Extracts structured intent, starting nodes, target labels, and hop limits from natural language queries."""

    def extract_intent(
        self,
        query: str,
        max_hops: int | None = None,
        limit: int = 10,
    ) -> GraphQueryIntent:
        """Parse natural language query into validated GraphQueryIntent."""
        q_lower = query.lower()

        # 1. Company / Ticker Detection
        company_name, ticker = detect_company_entity(query)
        starting_ids = []
        if ticker:
            starting_ids.append(f"company:{ticker}")

        # 2. Year Detection
        year, _ = detect_year_entity(query)

        # 3. Target Node Labels & Allowed Relation Types Allowlist Matching
        target_labels: list[str] = []
        rel_types: list[str] = []
        metric_name: str | None = None

        if any(w in q_lower for w in ["ürün", "üretim", "hizmet", "marka", "product"]):
            target_labels.append("Product")
            rel_types.extend(["PRODUCES"])

        if any(w in q_lower for w in ["sektör", "rakip", "aynı sektör", "alan", "sector"]):
            target_labels.extend(["Sector", "Company"])
            rel_types.extend(["OPERATES_IN"])

        if any(w in q_lower for w in ["ciro", "kâr", "gelir", "favök", "ebitda", "bütçe", "metrik", "oran", "artış"]):
            target_labels.append("FinancialMetric")
            rel_types.extend(["REPORTED", "CONTAINS_METRIC", "REPORTED_METRIC"])
            if "ciro" in q_lower or "revenue" in q_lower:
                metric_name = "ciro"
            elif "kâr" in q_lower or "profit" in q_lower:
                metric_name = "net_kâr"

        if any(w in q_lower for w in ["yönetici", "ceo", "müdür", "başkana", "yönetim", "person"]):
            target_labels.append("Person")
            rel_types.extend(["EXECUTIVE_AT", "HOLDS_ROLE_AT"])

        if any(w in q_lower for w in ["rapor", "faaliyet raporu", "report"]):
            target_labels.append("Report")
            rel_types.extend(["PUBLISHED"])

        # Default fallback targets if none matched
        if not target_labels:
            target_labels = ["Product", "FinancialMetric", "Sector", "Person"]

        # Filter against allowlist
        valid_targets = [lbl for lbl in target_labels if lbl in ALLOWED_NODE_LABELS]
        valid_rels = [r for r in rel_types if r in ALLOWED_RELATION_TYPES]

        # 4. Hop Count Estimation
        estimated_hops = 2
        if "ürün" in q_lower or "yönetici" in q_lower:
            estimated_hops = 1
        elif "aynı sektör" in q_lower or "metrik" in q_lower or "artış" in q_lower:
            estimated_hops = 2
        if max_hops is not None:
            final_hops = min(3, max(1, max_hops))
        else:
            final_hops = min(3, max(1, estimated_hops))

        intent = GraphQueryIntent(
            raw_query=query,
            starting_ticker=ticker,
            starting_entity_ids=starting_ids,
            target_node_labels=valid_targets,
            allowed_rel_types=valid_rels,
            year_filter=year,
            metric_name_filter=metric_name,
            max_hops=final_hops,
            limit=min(50, max(1, limit)),
        )

        logger.info(
            "Extracted graph query intent",
            starting_ticker=ticker,
            target_labels=valid_targets,
            hops=final_hops,
        )
        return intent
