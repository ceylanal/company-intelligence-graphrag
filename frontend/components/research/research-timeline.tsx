import { Check, Circle, LoaderCircle } from "lucide-react";

import type { ResearchPlan } from "@/lib/types/api";

const labels: Record<string, string> = {
  QUERY_INTAKE: "Understand question",
  PLANNING: "Build research plan",
  PLAN_VALIDATION: "Validate research scope",
  RESEARCH_EXECUTION: "Retrieve vector and graph evidence",
  EVIDENCE_MERGE: "Fuse and deduplicate evidence",
  VERIFICATION: "Verify claims and citations",
  TARGETED_FOLLOWUP: "Resolve evidence gaps",
  REPORT_GENERATION: "Synthesize answer",
  FINAL_QUALITY_GATE: "Run final quality gate",
  COMPLETED: "Research complete",
};

export function ResearchTimeline({
  stages,
  currentStage,
  plan,
}: {
  stages: string[];
  currentStage: string | null;
  plan: ResearchPlan | null;
}) {
  if (!stages.length && !plan) return null;
  return (
    <section className="timeline card" aria-labelledby="timeline-heading">
      <div className="card-heading">
        <div>
          <p className="eyebrow">Live workflow</p>
          <h3 id="timeline-heading">Research steps</h3>
        </div>
        <span className="status-chip">Backend events</span>
      </div>
      <ol>
        {stages.map((stage) => {
          const active = stage === currentStage && stage !== "COMPLETED";
          return (
            <li key={stage} className={active ? "active" : ""}>
              <span className="step-icon" aria-hidden="true">
                {active ? <LoaderCircle size={15} className="spin" /> : <Check size={15} />}
              </span>
              <span>
                <strong>{labels[stage] ?? stage.replaceAll("_", " ").toLowerCase()}</strong>
                {stage === "RESEARCH_EXECUTION" && plan?.steps.length ? (
                  <small>{plan.steps.map((step) => step.question).join(" · ")}</small>
                ) : null}
              </span>
            </li>
          );
        })}
        {currentStage !== "COMPLETED" ? (
          <li className="pending">
            <span className="step-icon" aria-hidden="true">
              <Circle size={12} />
            </span>
            <span>Continuing securely…</span>
          </li>
        ) : null}
      </ol>
    </section>
  );
}
