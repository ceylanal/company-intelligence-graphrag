"use client";

import { KeyboardEvent, useEffect, useRef } from "react";
import { ExternalLink, FileSearch, Network, PanelRightClose, X } from "lucide-react";

import { apiUrl } from "@/lib/api/config";
import type { Citation, Evidence } from "@/lib/types/api";

interface EvidencePanelProps {
  open: boolean;
  citations: Citation[];
  evidence: Evidence[];
  selectedIndex: number | null;
  onSelect: (index: number) => void;
  onClose: () => void;
}

export function EvidencePanel({
  open,
  citations,
  evidence,
  selectedIndex,
  onSelect,
  onClose,
}: EvidencePanelProps) {
  const panelRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (open) panelRef.current?.focus();
  }, [open, selectedIndex]);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") onClose();
    if (event.key === "Tab") {
      const focusable = panelRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  };

  if (!open) return null;
  return (
    <>
      <button className="drawer-backdrop" aria-label="Close evidence panel" onClick={onClose} />
      <aside
        className="evidence-panel"
        aria-label="Source evidence"
        aria-modal="true"
        role="dialog"
        tabIndex={-1}
        ref={panelRef}
        onKeyDown={onKeyDown}
      >
        <header>
          <div>
            <p className="eyebrow">Grounding</p>
            <h2>Source evidence</h2>
          </div>
          <button className="icon-button desktop-close" onClick={onClose} aria-label="Collapse evidence panel">
            <PanelRightClose size={19} />
          </button>
          <button className="icon-button mobile-close" onClick={onClose} aria-label="Close evidence drawer">
            <X size={20} />
          </button>
        </header>
        <div className="evidence-content">
          {!citations.length ? (
            <div className="panel-empty">
              <FileSearch size={28} />
              <h3>No verified evidence yet</h3>
              <p>Citations returned by the research backend will appear here.</p>
            </div>
          ) : (
            citations.map((citation) => {
              const matchingEvidence = evidence.find((item) => item.chunk_id === citation.chunk_id);
              const active = citation.citation_index === selectedIndex;
              const excerpt = citation.snippet || matchingEvidence?.content || matchingEvidence?.text;
              const graphPath = citation.graph_path ?? matchingEvidence?.graph_path;
              return (
                <article
                  className={`evidence-card ${active ? "selected" : ""}`}
                  key={`${citation.citation_index}-${citation.chunk_id}`}
                >
                  <button
                    className="evidence-select"
                    type="button"
                    onClick={() => onSelect(citation.citation_index)}
                    aria-expanded={active}
                  >
                    <span className="source-number">[{citation.citation_index}]</span>
                    <span>
                      <strong>{citation.company}</strong>
                      <small>
                        {citation.report_type?.replaceAll("_", " ") || "Report"} · {citation.year}
                      </small>
                    </span>
                    <span className={`verification ${citation.citation_status === "verified" ? "verified" : ""}`}>
                      {citation.citation_status || "provided"}
                    </span>
                  </button>
                  {active ? (
                    <div className="evidence-details">
                      <dl>
                        <div>
                          <dt>Document</dt>
                          <dd>{citation.source_file}</dd>
                        </div>
                        <div>
                          <dt>Page</dt>
                          <dd>{citation.page_number}</dd>
                        </div>
                        <div>
                          <dt>Source ID</dt>
                          <dd>{citation.chunk_id}</dd>
                        </div>
                        <div>
                          <dt>Retrieval</dt>
                          <dd>{citation.retrieval_method.replaceAll("_", " ")}</dd>
                        </div>
                        {citation.relevance_score != null ? (
                          <div>
                            <dt>Relevance</dt>
                            <dd>{Math.round(citation.relevance_score * 100)}%</dd>
                          </div>
                        ) : null}
                      </dl>
                      {excerpt ? <blockquote>{excerpt}</blockquote> : <p className="missing">Excerpt unavailable.</p>}
                      {graphPath ? (
                        <details className="graph-context">
                          <summary>
                            <Network size={15} /> GraphRAG context
                          </summary>
                          <pre>{typeof graphPath === "string" ? graphPath : JSON.stringify(graphPath, null, 2)}</pre>
                        </details>
                      ) : null}
                      {citation.document_available && citation.document_url ? (
                        <a
                          className="document-link"
                          href={`${apiUrl(citation.document_url)}#page=${citation.page_number}`}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          Open source page <ExternalLink size={14} />
                        </a>
                      ) : (
                        <p className="missing">The source PDF is not available from this deployment.</p>
                      )}
                    </div>
                  ) : null}
                </article>
              );
            })
          )}
        </div>
      </aside>
    </>
  );
}
