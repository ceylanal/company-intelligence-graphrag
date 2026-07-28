"""Graph reasoning metrics module: Entity Recall, Relation Recall, Graph Path Recall."""

from company_graphrag.evals.models import GraphMetricsResult


def calculate_entity_recall(retrieved_entities: list[str], expected_entities: list[str]) -> float:
    """Calculate Entity Recall: fraction of expected ground truth entities retrieved."""
    if not expected_entities:
        return 1.0
    if not retrieved_entities:
        return 0.0
    r_set = {e.lower() for e in retrieved_entities}
    e_set = {e.lower() for e in expected_entities}
    hits = r_set & e_set
    return round(len(hits) / len(e_set), 4)


def calculate_relation_recall(retrieved_relations: list[str], expected_relations: list[str]) -> float:
    """Calculate Relation Recall: fraction of expected relationship types retrieved."""
    if not expected_relations:
        return 1.0
    if not retrieved_relations:
        return 0.0
    r_set = {r.upper() for r in retrieved_relations}
    e_set = {r.upper() for r in expected_relations}
    hits = r_set & e_set
    return round(len(hits) / len(e_set), 4)


def calculate_graph_path_recall(retrieved_paths: list[str], expected_paths: list[str]) -> float:
    """Calculate Graph Path Recall: fraction of expected graph paths retrieved."""
    if not expected_paths:
        return 1.0
    if not retrieved_paths:
        return 0.0

    retrieved_text = " ".join([p.lower() for p in retrieved_paths])
    hits = 0
    for exp_p in expected_paths:
        exp_clean = exp_p.lower()
        if exp_clean in retrieved_text or any(exp_clean in p.lower() for p in retrieved_paths):
            hits += 1

    return round(hits / len(expected_paths), 4)


def evaluate_graph_reasoning(
    retrieved_entities: list[str],
    expected_entities: list[str],
    retrieved_relations: list[str],
    expected_relations: list[str],
    retrieved_paths: list[str] | None = None,
    expected_paths: list[str] | None = None,
) -> GraphMetricsResult:
    """Aggregate graph metrics into GraphMetricsResult."""
    retrieved_paths = retrieved_paths or []
    expected_paths = expected_paths or []

    return GraphMetricsResult(
        entity_recall=calculate_entity_recall(retrieved_entities, expected_entities),
        relation_recall=calculate_relation_recall(retrieved_relations, expected_relations),
        graph_path_recall=calculate_graph_path_recall(retrieved_paths, expected_paths),
    )
