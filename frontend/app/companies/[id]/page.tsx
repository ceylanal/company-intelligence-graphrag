"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, CalendarRange, ExternalLink, FileText, Search } from "lucide-react";
import { useEffect, useState } from "react";

import { getCompanies } from "@/lib/api/client";
import type { Company } from "@/lib/types/api";

export default function CompanyProfilePage() {
  const params = useParams<{ id: string }>();
  const [company, setCompany] = useState<Company | null | undefined>(undefined);

  useEffect(() => {
    const controller = new AbortController();
    getCompanies(controller.signal)
      .then((items) => setCompany(items.find((item) => item.id === params.id) ?? null))
      .catch(() => setCompany(null));
    return () => controller.abort();
  }, [params.id]);

  return (
    <main className="profile-page">
      <div className="profile-shell">
        <Link className="back-link" href="/">
          <ArrowLeft size={16} /> Research workspace
        </Link>
        {company === undefined ? (
          <div className="profile-loading">Loading repository metadata…</div>
        ) : company === null ? (
          <section className="profile-hero">
            <p className="eyebrow">Company profile</p>
            <h1>Company unavailable</h1>
            <p>The backend did not return this company from its configured catalog.</p>
          </section>
        ) : (
          <>
            <section className="profile-hero">
              <span className="profile-mark">{company.name.slice(0, 2).toLocaleUpperCase("tr-TR")}</span>
              <div>
                <p className="eyebrow">Repository company profile</p>
                <h1>{company.name}</h1>
                <p>
                  Static identity and report coverage from the backend catalog. No live price, market cap,
                  valuation multiple, or dividend data is available.
                </p>
              </div>
            </section>
            <div className="profile-grid">
              <section className="card profile-card">
                <div className="card-heading">
                  <div>
                    <p className="eyebrow">Coverage</p>
                    <h2>Available report years</h2>
                  </div>
                  <CalendarRange size={20} />
                </div>
                <div className="year-list">
                  {company.years.map((year) => (
                    <span key={year}>{year}</span>
                  ))}
                </div>
                <p>Financial values are shown only inside citation-backed research answers.</p>
              </section>
              <section className="card profile-card">
                <div className="card-heading">
                  <div>
                    <p className="eyebrow">Identity</p>
                    <h2>Known aliases</h2>
                  </div>
                  <FileText size={20} />
                </div>
                <ul>
                  {company.aliases.map((alias) => <li key={alias}>{alias}</li>)}
                </ul>
              </section>
              <section className="card profile-card domains">
                <div className="card-heading">
                  <div>
                    <p className="eyebrow">Configured sources</p>
                    <h2>Official domains</h2>
                  </div>
                  <ExternalLink size={20} />
                </div>
                <ul>
                  {company.official_domains.map((domain) => <li key={domain}>{domain}</li>)}
                </ul>
              </section>
            </div>
            <Link
              className="profile-research-link"
              href={`/?company=${encodeURIComponent(company.id)}`}
            >
              <Search size={17} /> Research {company.name}
            </Link>
          </>
        )}
      </div>
    </main>
  );
}
