"use client";

import { useCallback, useRef, useState } from "react";

import { ApiError, streamResearch } from "@/lib/api/client";
import type { ConversationTurn, ResearchState, StreamEvent } from "@/lib/types/api";

export const initialResearchState: ResearchState = {
  phase: "idle",
  query: "",
  answer: "",
  runId: null,
  requestId: null,
  stage: null,
  stages: [],
  plan: null,
  evidence: [],
  citations: [],
  metrics: null,
  safetyAction: null,
  safetyCodes: [],
  warnings: [],
  unansweredQuestions: [],
  error: null,
  protocolWarnings: [],
};

function reduceEvent(state: ResearchState, event: StreamEvent): ResearchState {
  switch (event.type) {
    case "accepted":
      return {
        ...state,
        phase: "streaming",
        runId: event.run_id,
        requestId: event.request_id,
        safetyAction: event.safety_action,
      };
    case "safety":
      return {
        ...state,
        safetyAction: event.action,
        safetyCodes: [...new Set([...state.safetyCodes, ...event.decision_codes])],
      };
    case "stage":
      return {
        ...state,
        stage: event.stage,
        stages: state.stages.includes(event.stage) ? state.stages : [...state.stages, event.stage],
      };
    case "plan":
      return { ...state, plan: event.plan };
    case "evidence":
      return { ...state, evidence: event.items };
    case "citations":
      return { ...state, citations: event.items };
    case "metrics":
      return { ...state, metrics: event.metrics };
    case "answer_delta":
      return { ...state, answer: state.answer + event.delta };
    case "complete":
      return {
        ...state,
        phase: "complete",
        answer: event.answer,
        runId: event.run_id,
        requestId: event.request_id,
        stage: event.stage,
        plan: event.plan,
        evidence: event.evidence,
        citations: event.citations,
        metrics: event.metrics,
        warnings: event.warnings,
        unansweredQuestions: event.unanswered_questions,
      };
    case "error":
      return { ...state, phase: "error", error: event.message };
    default:
      return state;
  }
}

export function useResearch() {
  const [state, setState] = useState<ResearchState>(initialResearchState);
  const controllerRef = useRef<AbortController | null>(null);
  const cancelledByUser = useRef(false);

  const submit = useCallback(async (query: string, history: ConversationTurn[] = []) => {
    const trimmed = query.trim();
    if (!trimmed || controllerRef.current) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    cancelledByUser.current = false;
    setState({ ...initialResearchState, phase: "connecting", query: trimmed });
    const timeout = window.setTimeout(() => controller.abort("timeout"), 305_000);
    try {
      await streamResearch(
        {
          query: trimmed,
          history,
          idempotencyKey: crypto.randomUUID(),
        },
        {
          onEvent: (event) => setState((current) => reduceEvent(current, event)),
          onMalformedLine: () =>
            setState((current) => ({
              ...current,
              protocolWarnings: [
                ...current.protocolWarnings,
                "One malformed stream event was ignored.",
              ],
            })),
        },
        controller.signal,
      );
    } catch (error) {
      if (controller.signal.aborted) {
        setState((current) => ({
          ...current,
          phase: cancelledByUser.current ? "cancelled" : "error",
          error: cancelledByUser.current ? null : "The research request timed out.",
        }));
      } else {
        const message =
          error instanceof ApiError
            ? `${error.message}${error.requestId ? ` Request ID: ${error.requestId}` : ""}`
            : "Could not connect to the research service.";
        setState((current) => ({ ...current, phase: "error", error: message }));
      }
    } finally {
      window.clearTimeout(timeout);
      controllerRef.current = null;
    }
  }, []);

  const cancel = useCallback(() => {
    cancelledByUser.current = true;
    controllerRef.current?.abort("user");
  }, []);

  const reset = useCallback(() => {
    cancel();
    setState(initialResearchState);
  }, [cancel]);

  return { state, submit, cancel, reset, isActive: state.phase === "connecting" || state.phase === "streaming" };
}
