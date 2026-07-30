"use client";

import Link from "next/link";
import {
  Building2,
  History,
  Menu,
  MessageSquarePlus,
  Plus,
  Radar,
  Scale,
  X,
} from "lucide-react";

import type { Company } from "@/lib/types/api";

export interface HistoryItem {
  id: string;
  query: string;
}

export function Sidebar({
  open,
  companies,
  history,
  watchlist,
  onClose,
  onNew,
  onWatchlist,
}: {
  open: boolean;
  companies: Company[];
  history: HistoryItem[];
  watchlist: string[];
  onClose: () => void;
  onNew: () => void;
  onWatchlist: (id: string) => void;
}) {
  return (
    <>
      {open ? <button className="sidebar-backdrop" aria-label="Close navigation" onClick={onClose} /> : null}
      <nav className={`sidebar ${open ? "mobile-open" : ""}`} aria-label="Primary navigation">
        <div className="brand">
          <span className="brand-mark">
            <Radar size={20} />
          </span>
          <span>
            <strong>IntelliFin</strong>
            <small>Evidence research</small>
          </span>
          <button className="icon-button mobile-close" onClick={onClose} aria-label="Close navigation">
            <X size={19} />
          </button>
        </div>
        <button className="new-research" onClick={onNew}>
          <MessageSquarePlus size={17} />
          New research
        </button>
        <div className="sidebar-nav">
          <a href="#research">
            <MessageSquarePlus size={17} /> Research
          </a>
          <a href="#history">
            <History size={17} /> History
          </a>
          <a href="#companies">
            <Building2 size={17} /> Companies
          </a>
          <a href="#compare">
            <Scale size={17} /> Compare
          </a>
        </div>
        <section id="history" className="sidebar-section">
          <p className="eyebrow">Recent on this device</p>
          {history.length ? (
            <ul>
              {history.slice(0, 5).map((item) => (
                <li key={item.id} title={item.query}>
                  {item.query}
                </li>
              ))}
            </ul>
          ) : (
            <p className="sidebar-empty">No local history yet.</p>
          )}
        </section>
        <section id="companies" className="sidebar-section watchlist">
          <p className="eyebrow">Watchlist</p>
          <div>
            {watchlist.map((id) => {
              const company = companies.find((item) => item.id === id);
              return company ? (
                <Link key={id} href={`/companies/${id}`} title={company.name}>
                  {company.name.split(" ")[0]}
                </Link>
              ) : null;
            })}
            <button
              type="button"
              aria-label="Add first available company to watchlist"
              onClick={() => companies[0] && onWatchlist(companies[0].id)}
            >
              <Plus size={14} />
            </button>
          </div>
        </section>
        <p className="sidebar-disclaimer">Watchlist and history are stored only in this browser.</p>
      </nav>
    </>
  );
}

export function MobileMenuButton({ onClick }: { onClick: () => void }) {
  return (
    <button className="icon-button menu-button" onClick={onClick} aria-label="Open navigation">
      <Menu size={20} />
    </button>
  );
}
