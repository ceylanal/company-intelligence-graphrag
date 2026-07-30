"use client";

import { FormEvent, KeyboardEvent, useState } from "react";
import { ArrowUp, Square } from "lucide-react";

import type { Company } from "@/lib/types/api";

interface ComposerProps {
  companies: Company[];
  isActive: boolean;
  initialCompany?: string;
  onSubmit: (query: string) => void;
  onCancel: () => void;
}

export function Composer({
  companies,
  isActive,
  initialCompany = "",
  onSubmit,
  onCancel,
}: ComposerProps) {
  const [query, setQuery] = useState("");
  const [company, setCompany] = useState(initialCompany);
  const [mode, setMode] = useState("hybrid");

  const send = (event?: FormEvent) => {
    event?.preventDefault();
    const companyName = companies.find((item) => item.id === company)?.name;
    const scoped = companyName ? `${companyName}: ${query.trim()}` : query.trim();
    if (!isActive && scoped) {
      onSubmit(scoped);
      setQuery("");
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  };

  return (
    <form className="composer" onSubmit={send} aria-label="Research question">
      <div className="composer-controls">
        <label>
          <span className="sr-only">Company</span>
          <select value={company} onChange={(event) => setCompany(event.target.value)}>
            <option value="">All companies</option>
            {companies.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Research mode</span>
          <select value={mode} onChange={(event) => setMode(event.target.value)}>
            <option value="hybrid">Hybrid research</option>
            <option value="vector">Document focus</option>
            <option value="graph">Relationship focus</option>
          </select>
        </label>
        <span className="mode-note" aria-hidden="true">
          {mode === "hybrid" ? "Vector + GraphRAG" : mode === "vector" ? "Vector RAG" : "GraphRAG"}
        </span>
      </div>
      <div className="composer-input">
        <textarea
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          maxLength={32_000}
          disabled={isActive}
          aria-label="Ask a company research question"
          placeholder="Ask about performance, strategy, risks, or compare companies…"
        />
        {isActive ? (
          <button className="send-button stop" type="button" onClick={onCancel} aria-label="Cancel research">
            <Square size={17} fill="currentColor" />
          </button>
        ) : (
          <button className="send-button" type="submit" disabled={!query.trim()} aria-label="Send question">
            <ArrowUp size={19} />
          </button>
        )}
      </div>
      <p className="composer-caption">Answers are grounded in indexed repository documents. Verify material decisions.</p>
    </form>
  );
}
