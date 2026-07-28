"""Low-cardinality Prometheus metrics for API and AI operations."""

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter("company_graphrag_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("company_graphrag_http_request_duration_seconds", "HTTP latency", ["method", "route"])
ACTIVE_RESEARCH = Gauge("company_graphrag_active_research_tasks", "Active research workflows")
DEPENDENCY_LATENCY = Histogram(
    "company_graphrag_dependency_duration_seconds",
    "Dependency latency",
    ["dependency", "operation"],
)
MODEL_CALLS = Counter("company_graphrag_model_calls_total", "Model calls", ["provider", "model", "status"])
TOKENS = Counter("company_graphrag_tokens_total", "Model tokens", ["provider", "model", "direction"])
RETRIES = Counter("company_graphrag_retries_total", "Retries", ["dependency", "reason"])
CITATION_COVERAGE = Histogram("company_graphrag_citation_coverage_ratio", "Citation coverage ratio")
