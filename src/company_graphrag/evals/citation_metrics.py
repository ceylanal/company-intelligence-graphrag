"""Citation quality metrics module: Citation Precision, Recall, Coverage, Page Accuracy."""

from company_graphrag.evals.models import CitationMetricsResult


def calculate_citation_precision(cited_sources: list[str], relevant_sources: list[str]) -> float:
    """Calculate Citation Precision: fraction of cited sources that are truly relevant."""
    if not cited_sources:
        return 1.0 if not relevant_sources else 0.0
    rel_set = {s.lower() for s in relevant_sources}
    hits = sum(1 for c in cited_sources if c.lower() in rel_set)
    return round(hits / len(cited_sources), 4)


def calculate_citation_recall(cited_sources: list[str], relevant_sources: list[str]) -> float:
    """Calculate Citation Recall: fraction of relevant ground truth sources cited."""
    if not relevant_sources:
        return 1.0
    if not cited_sources:
        return 0.0
    cited_set = {c.lower() for c in cited_sources}
    rel_set = {s.lower() for s in relevant_sources}
    hits = cited_set & rel_set
    return round(len(hits) / len(rel_set), 4)


def calculate_citation_coverage(cited_sources: list[str], claim_count: int = 1) -> float:
    """Calculate Citation Coverage: ratio of cited sources to total factual claims."""
    if claim_count <= 0:
        return 1.0
    return round(min(1.0, len(cited_sources) / claim_count), 4)


def calculate_cited_page_accuracy(cited_pages: list[int], expected_pages: list[int]) -> float:
    """Calculate Cited Page Accuracy: fraction of cited page numbers matching expected pages."""
    if not expected_pages:
        return 1.0
    if not cited_pages:
        return 0.0
    exp_set = set(expected_pages)
    hits = sum(1 for p in cited_pages if p in exp_set)
    return round(hits / len(cited_pages), 4)


def evaluate_citations(
    cited_sources: list[str],
    relevant_sources: list[str],
    cited_pages: list[int] | None = None,
    expected_pages: list[int] | None = None,
    claim_count: int = 1,
) -> CitationMetricsResult:
    """Aggregate citation metrics into CitationMetricsResult."""
    cited_pages = cited_pages or []
    expected_pages = expected_pages or []

    return CitationMetricsResult(
        citation_precision=calculate_citation_precision(cited_sources, relevant_sources),
        citation_recall=calculate_citation_recall(cited_sources, relevant_sources),
        citation_coverage=calculate_citation_coverage(cited_sources, claim_count),
        cited_page_accuracy=calculate_cited_page_accuracy(cited_pages, expected_pages),
    )
