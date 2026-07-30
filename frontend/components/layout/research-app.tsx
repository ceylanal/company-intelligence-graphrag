"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, ChevronRight, PanelRightOpen, RefreshCw, Scale, WifiOff } from "lucide-react";

import { Composer } from "@/components/chat/composer";
import { EmptyState } from "@/components/chat/empty-state";
import { MarkdownAnswer } from "@/components/chat/markdown-answer";
import { EvidencePanel } from "@/components/evidence/evidence-panel";
import { MobileMenuButton, Sidebar, type HistoryItem } from "@/components/layout/sidebar";
import { MetricsPanel } from "@/components/research/metrics-panel";
import { ResearchTimeline } from "@/components/research/research-timeline";
import { checkHealth, getCompanies } from "@/lib/api/client";
import type { Company, ConversationTurn, HealthState } from "@/lib/types/api";
import { useResearch } from "@/hooks/use-research";

const HISTORY_KEY = "intellifin-research-history-v1";
const WATCHLIST_KEY = "intellifin-watchlist-v1";

function readStored<T>(key: string, fallback: T): T {
  try {
    const value = localStorage.getItem(key);
    return value ? (JSON.parse(value) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function ResearchApp() {
  const { state, submit, cancel, reset, isActive } = useResearch();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [health, setHealth] = useState<HealthState>("checking");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<number | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const followOutput = useRef(true);

  useEffect(() => {
    queueMicrotask(() => {
      setHistory(readStored<HistoryItem[]>(HISTORY_KEY, []));
      setWatchlist(readStored<string[]>(WATCHLIST_KEY, []));
    });
    const controller = new AbortController();
    Promise.allSettled([checkHealth(controller.signal), getCompanies(controller.signal)]).then(([healthResult, companiesResult]) => {
      setHealth(healthResult.status === "fulfilled" && healthResult.value ? "healthy" : "offline");
      if (companiesResult.status === "fulfilled") {
        setCompanies(companiesResult.value);
        setWatchlist((current) => current.length ? current : companiesResult.value.slice(0, 3).map((item) => item.id));
      }
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (state.answer && followOutput.current) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [state.answer]);

  const citationIndexes = useMemo(
    () => new Set(state.citations.map((citation) => citation.citation_index)),
    [state.citations],
  );

  const onCitation = (index: number) => {
    setSelectedCitation(index);
    setEvidenceOpen(true);
  };

  const onScroll = () => {
    const node = scrollRef.current;
    if (!node) return;
    followOutput.current = node.scrollHeight - node.scrollTop - node.clientHeight < 120;
  };

  const onSubmit = (query: string) => {
    followOutput.current = true;
    setSelectedCitation(null);
    setHistory((current) => {
      const next = [{ id: crypto.randomUUID(), query }, ...current].slice(0, 20);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
      return next;
    });
    const turns: ConversationTurn[] = history.slice(0, 3).map((item) => ({
      role: "user",
      content: item.query,
    }));
    void submit(query, turns);
  };

  const toggleWatchlist = (id: string) => {
    setWatchlist((current) => {
      const next = current.includes(id) ? current.filter((item) => item !== id) : [...current, id];
      localStorage.setItem(WATCHLIST_KEY, JSON.stringify(next));
      return next;
    });
  };

  const compareFirstTwo = () => {
    if (companies.length >= 2) {
      onSubmit(
        `Compare ${companies[0].name} and ${companies[1].name} using available report evidence. Include a citation-backed table, evidence coverage, strategic outlook, and key risks.`,
      );
    }
  };

  const hasResult = state.phase !== "idle";
  const noEvidence = state.phase === "complete" && state.citations.length === 0;
  const partialEvidence = state.phase === "complete" && (state.warnings.length > 0 || state.unansweredQuestions.length > 0);

  return (
    <div className="app-shell" id="research">
      <Sidebar
        open={sidebarOpen}
        companies={companies}
        history={history}
        watchlist={watchlist}
        onClose={() => setSidebarOpen(false)}
        onNew={reset}
        onWatchlist={toggleWatchlist}
      />
      <main className="research-main">
        <header className="topbar">
          <div className="topbar-title">
            <MobileMenuButton onClick={() => setSidebarOpen(true)} />
            <div>
              <p className="eyebrow">Company intelligence workspace</p>
              <h2>{state.query || "New research"}</h2>
            </div>
          </div>
          <div className="topbar-actions">
            <span className={`health ${health}`} role="status" aria-live="polite">
              {health === "healthy" ? <Activity size={14} /> : <WifiOff size={14} />}
              {health === "checking" ? "Checking backend" : health === "healthy" ? "Backend ready" : "Backend offline"}
            </span>
            <button className="secondary-button compare-button" onClick={compareFirstTwo} disabled={companies.length < 2 || isActive}>
              <Scale size={16} /> Compare
            </button>
            <button
              className="icon-button"
              onClick={() => setEvidenceOpen((current) => !current)}
              aria-label={evidenceOpen ? "Collapse evidence panel" : "Open evidence panel"}
              aria-expanded={evidenceOpen}
            >
              <PanelRightOpen size={20} />
            </button>
          </div>
        </header>

        <div className="company-strip" aria-label="Company profiles">
          {companies.slice(0, 7).map((company) => (
            <Link href={`/companies/${company.id}`} key={company.id}>
              {company.name}
              <ChevronRight size={13} />
            </Link>
          ))}
        </div>

        <div className="chat-scroll" ref={scrollRef} onScroll={onScroll}>
          {!hasResult ? (
            <EmptyState onPrompt={onSubmit} />
          ) : (
            <div className="conversation">
              <div className="user-message">
                <span>You</span>
                <p>{state.query}</p>
              </div>
              <div className="assistant-row">
                <div className="assistant-avatar" aria-hidden="true">AI</div>
                <div className="assistant-content">
                  <div className="answer-card">
                    <div className="answer-accent" />
                    <div className="answer-meta">
                      <span>Evidence research</span>
                      <span className={`phase ${state.phase}`}>{state.phase}</span>
                    </div>
                    {state.answer ? (
                      <MarkdownAnswer
                        answer={state.answer}
                        citationIndexes={citationIndexes}
                        onCitation={onCitation}
                      />
                    ) : isActive ? (
                      <div className="researching" role="status">
                        <span className="pulse-dot" />
                        Researching indexed documents and graph relationships…
                      </div>
                    ) : null}
                    {state.phase === "cancelled" ? (
                      <div className="notice neutral">Research cancelled. Any partial answer above has been preserved.</div>
                    ) : null}
                    {state.error ? (
                      <div className="notice error" role="alert">
                        <div>
                          <strong>Research could not be completed</strong>
                          <p>{state.error}</p>
                        </div>
                        <button className="secondary-button" onClick={() => onSubmit(state.query)}>
                          <RefreshCw size={15} /> Retry
                        </button>
                      </div>
                    ) : null}
                    {noEvidence ? (
                      <div className="notice warning">
                        <strong>Insufficient evidence</strong>
                        <p>No verified source was returned. Treat the answer as an abstention, not a factual result.</p>
                      </div>
                    ) : null}
                    {partialEvidence ? (
                      <div className="notice warning">
                        <strong>Partial evidence coverage</strong>
                        {[...state.warnings, ...state.unansweredQuestions].slice(0, 4).map((warning) => (
                          <p key={warning}>{warning}</p>
                        ))}
                      </div>
                    ) : null}
                    {state.protocolWarnings.length ? (
                      <p className="protocol-warning">{state.protocolWarnings.at(-1)}</p>
                    ) : null}
                  </div>
                  <div className="research-grid">
                    <ResearchTimeline stages={state.stages} currentStage={state.stage} plan={state.plan} />
                    <MetricsPanel metrics={state.metrics} />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
        <div className="composer-dock">
          <Composer
            companies={companies}
            isActive={isActive}
            onSubmit={onSubmit}
            onCancel={cancel}
          />
        </div>
      </main>
      <EvidencePanel
        open={evidenceOpen}
        citations={state.citations}
        evidence={state.evidence}
        selectedIndex={selectedCitation ?? state.citations[0]?.citation_index ?? null}
        onSelect={setSelectedCitation}
        onClose={() => setEvidenceOpen(false)}
      />
    </div>
  );
}
