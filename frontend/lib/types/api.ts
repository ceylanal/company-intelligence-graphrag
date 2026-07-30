export type HealthState = "checking" | "healthy" | "degraded" | "offline";
export type RequestPhase =
  | "idle"
  | "connecting"
  | "streaming"
  | "complete"
  | "cancelled"
  | "error";

export interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
}

export interface Company {
  id: string;
  name: string;
  aliases: string[];
  official_domains: string[];
  years: number[];
}

export interface Evidence {
  evidence_id: string;
  company: string;
  ticker: string;
  year: number;
  report?: string;
  report_type?: string;
  chunk_id: string;
  page_number: number;
  source_file: string;
  retrieval_method: string;
  content?: string;
  text?: string;
  relevance_score?: number | null;
  graph_path?: Record<string, unknown> | unknown[] | string | null;
  citation_status?: string | null;
}

export interface Citation {
  citation_index: number;
  chunk_id: string;
  company: string;
  ticker: string;
  year: number;
  source_file: string;
  page_number: number;
  retrieval_method: string;
  snippet: string;
  relevance_score?: number | null;
  citation_status?: string | null;
  report_type?: string | null;
  graph_path?: Record<string, unknown> | unknown[] | string | null;
  document_available?: boolean;
  document_url?: string | null;
}

export interface PlanStep {
  task_id: string;
  question: string;
  objective: string;
  retrieval_strategy: string;
  required_tools: string[];
  status: string;
  result_summary?: string | null;
}

export interface ResearchPlan {
  plan_id: string;
  detected_companies: string[];
  detected_tickers: string[];
  detected_years: number[];
  is_comparison: boolean;
  is_multi_hop: boolean;
  steps: PlanStep[];
}

export interface ResearchMetrics {
  duration_ms: number;
  evidence_count: number;
  citation_count: number;
  citation_coverage?: number | null;
  search_calls: number;
  model_calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  retry_count: number;
}

export type StreamEvent =
  | { type: "accepted"; run_id: string; request_id: string; safety_action: string }
  | { type: "safety"; phase: "input" | "output"; action: string; decision_codes: string[] }
  | { type: "stage"; stage: string; status: string }
  | { type: "plan"; plan: ResearchPlan }
  | { type: "evidence"; items: Evidence[] }
  | { type: "citations"; items: Citation[] }
  | { type: "metrics"; metrics: ResearchMetrics }
  | { type: "answer_delta"; delta: string }
  | {
      type: "complete";
      run_id: string;
      request_id: string;
      status: string;
      stage: string;
      answer: string;
      citations: Citation[];
      evidence: Evidence[];
      plan: ResearchPlan | null;
      metrics: ResearchMetrics;
      warnings: string[];
      unanswered_questions: string[];
      metadata: Record<string, unknown>;
    }
  | { type: "error"; code: string; message: string; recoverable: boolean };

export interface ResearchState {
  phase: RequestPhase;
  query: string;
  answer: string;
  runId: string | null;
  requestId: string | null;
  stage: string | null;
  stages: string[];
  plan: ResearchPlan | null;
  evidence: Evidence[];
  citations: Citation[];
  metrics: ResearchMetrics | null;
  safetyAction: string | null;
  safetyCodes: string[];
  warnings: string[];
  unansweredQuestions: string[];
  error: string | null;
  protocolWarnings: string[];
}
