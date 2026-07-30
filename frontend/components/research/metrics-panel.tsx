import type { ResearchMetrics } from "@/lib/types/api";

export function MetricsPanel({ metrics }: { metrics: ResearchMetrics | null }) {
  if (!metrics) return null;
  const coverage =
    metrics.citation_coverage == null ? "—" : `${Math.round(metrics.citation_coverage * 100)}%`;
  const values = [
    ["Evidence", String(metrics.evidence_count)],
    ["Citations", String(metrics.citation_count)],
    ["Coverage", coverage],
    ["Latency", `${(metrics.duration_ms / 1000).toFixed(1)}s`],
    ["Searches", String(metrics.search_calls)],
    ["Retries", String(metrics.retry_count)],
  ];
  return (
    <section className="metrics card" aria-labelledby="metrics-heading">
      <div className="card-heading">
        <div>
          <p className="eyebrow">Run diagnostics</p>
          <h3 id="metrics-heading">Answer metrics</h3>
        </div>
      </div>
      <dl>
        {values.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="metric-footnote">
        Cost estimate: ${metrics.estimated_cost_usd.toFixed(4)} · Tokens:{" "}
        {(metrics.input_tokens + metrics.output_tokens).toLocaleString()}
      </p>
    </section>
  );
}
