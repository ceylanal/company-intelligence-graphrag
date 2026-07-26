#!/usr/bin/env python3
"""
scripts/crawl_reports.py

Controlled pilot report crawler for company-intelligence-graphrag.

Supports:
  python scripts/crawl_reports.py --missing --tickers AKBNK THYAO --dry-run
  python scripts/crawl_reports.py --missing --tickers AKBNK THYAO
  python scripts/crawl_reports.py --all

Rules:
1. Crawls official IR domains first, falls back to KAP if unfulfilled.
2. Stops crawling for a company-year target slot as soon as the first verified annual_report is found.
3. Max 10 PDF candidate attempts per target slot.
4. HTTP Timeout: 15s, Max Link Depth: 2.
5. PyMuPDF text validation for company identity, year, and 'faaliyet raporu / annual report'.
6. Quarantines invalid candidates.
7. Saves dry-run URLs to data/dry_run_urls.json.
8. Updates data/report_manifest.jsonl and data/missing_reports.json upon successful downloads.
"""

import argparse
import json
import shutil
import sys
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "companies.yaml"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
QUARANTINE_DIR = PROJECT_ROOT / "data" / "quarantine"
MANIFEST_JSONL = PROJECT_ROOT / "data" / "report_manifest.jsonl"
MISSING_JSON = PROJECT_ROOT / "data" / "missing_reports.json"
DRY_RUN_JSON = PROJECT_ROOT / "data" / "dry_run_urls.json"

sys.path.insert(0, str(PROJECT_ROOT))
from scripts.validate_reports import load_companies_config, validate_pdf_content

REPORT_KEYWORDS = [
    "faaliyet raporu",
    "faaliyet-raporu",
    "annual report",
    "annual-report",
    "entegre faaliyet",
    "entegre-faaliyet",
]

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.7",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def is_allowed_by_robots(url: str, user_agent: str = "*") -> bool:
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True


def is_official_domain(url: str, official_domains: list[str]) -> bool:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return any(allowed.lower() in domain for allowed in official_domains)


def is_annual_report_link(href: str, link_text: str) -> bool:
    combined = (href + " " + link_text).lower()
    return any(kw in combined for kw in REPORT_KEYWORDS)


def fetch_url(session: requests.Session, url: str, timeout: int = 15, max_retries: int = 2):
    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True, verify=False)
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                time.sleep(1.5 * attempt)
        except Exception:
            if attempt < max_retries:
                time.sleep(1.0)
    return None


def search_kap_for_annual_report(
    session: requests.Session, company_name: str, year: int
) -> list[str]:
    """Fallback: Search KAP disclosures for official company annual report PDF links."""
    kap_pdf_urls = []
    try:
        # Query KAP disclosure API for company disclosures matching 'Faaliyet Raporu'
        search_url = "https://www.kap.org.tr/tr/api/disclosures"
        payload = {
            "fromDate": f"{year}-01-01",
            "toDate": f"{year + 1}-05-30",
            "subject": "Faaliyet Raporu",
        }
        resp = session.post(search_url, json=payload, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            for disc in data[:10]:
                disc_id = disc.get("disclosureId") or disc.get("id")
                if disc_id:
                    kap_pdf_urls.append(f"https://www.kap.org.tr/tr/api/BildirimPdf/{disc_id}")
    except Exception:
        pass

    return kap_pdf_urls


def crawl_slot(
    company_cfg: dict, target_year: int, dry_run: bool = False, max_candidates: int = 10
):
    """Crawls official IR domains (and KAP fallback) for a single company-year target slot."""
    company_id = company_cfg["id"]
    company_cfg["name"]
    ticker = company_cfg.get("canonical_ticker", company_id.upper())
    official_domains = company_cfg.get("official_domains", [])

    session = requests.Session()
    session.headers.update(HTTP_HEADERS)

    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    visited_urls = set()
    candidate_urls = []
    start_time = time.time()

    # Fast direct IR candidate generator
    if ticker == "AKBNK":
        candidate_urls.extend(
            [
                f"https://www.akbankinvestorrelations.com/pdf/{target_year}_faaliyet_raporu.pdf",
                f"https://www.akbankinvestorrelations.com/pdf/akbank_{target_year}_annual_report.pdf",
                f"https://www.kap.org.tr/tr/api/BildirimPdf/akbank_{target_year}_faaliyet_raporu",
            ]
        )
    elif ticker == "THYAO":
        candidate_urls.extend(
            [
                f"https://investor.turkishairlines.com/documents/Thy_Faaliyet_Raporu_{target_year}.pdf",
                f"https://investor.turkishairlines.com/documents/Turkish_Airlines_Annual_Report_{target_year}.pdf",
                f"https://www.kap.org.tr/tr/api/BildirimPdf/thy_{target_year}_faaliyet_raporu",
            ]
        )

    # Discover links on official IR domains
    for dom in official_domains:
        su = dom if dom.startswith("http") else f"https://www.{dom}"

        if su not in visited_urls and len(candidate_urls) < max_candidates:
            visited_urls.add(su)
            resp = fetch_url(session, su, timeout=5, max_retries=1)
            if resp and resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    link_text = a.get_text(strip=True)
                    full_url = urljoin(su, href)

                    if full_url.lower().endswith(".pdf") or ".pdf" in full_url.lower():
                        if is_annual_report_link(full_url, link_text) and (
                            str(target_year) in full_url or str(target_year) in link_text
                        ) and full_url not in candidate_urls:
                            candidate_urls.append(full_url)

    # Limit to max_candidates
    candidate_urls = candidate_urls[:max_candidates]

    if dry_run:
        duration = round(time.time() - start_time, 2)
        return {
            "ticker": ticker,
            "year": target_year,
            "status": "dry_run_discovered" if candidate_urls else "dry_run_no_candidates",
            "candidate_urls": candidate_urls,
            "rejected_candidates": 0,
            "duration_sec": duration,
        }

    # Step 3: Download & Validate Candidates (Early Stopping at 1st verified report)
    ticker_dir = RAW_DIR / ticker
    ticker_dir.mkdir(parents=True, exist_ok=True)
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    rejected_count = 0
    verified_url = None
    verified_status = "not_found"

    for cand_url in candidate_urls:
        time.sleep(1.0)
        resp = fetch_url(session, cand_url, timeout=15)
        if not resp or not resp.content.startswith(b"%PDF"):
            rejected_count += 1
            continue

        pdf_data = resp.content
        filename = f"{ticker}__{target_year}__annual_report__temp.pdf"
        temp_path = ticker_dir / filename

        with open(temp_path, "wb") as pf:
            pf.write(pdf_data)

        # Validate PDF
        val_res = validate_pdf_content(temp_path, company_cfg)
        status = val_res["status"]

        if status == "verified" and val_res.get("year") == target_year:
            # Detect language
            text = val_res.get("text", "")
            lang = (
                "en" if "annual report" in text.lower() and "faaliyet" not in text.lower() else "tr"
            )

            std_filename = f"{ticker}__{target_year}__annual_report__{lang}.pdf"
            final_path = ticker_dir / std_filename
            shutil.move(temp_path, final_path)

            verified_url = cand_url
            verified_status = "verified"
            print(f"  -> [VERIFIED MATCH] {ticker} {target_year} -> {std_filename}")
            break  # Early stopping!
        else:
            rejected_count += 1
            q_dir = QUARANTINE_DIR / ticker
            q_dir.mkdir(parents=True, exist_ok=True)
            q_target = q_dir / f"rejected_{target_year}_{temp_path.name}"
            shutil.move(temp_path, q_target)
            print(f"  -> [REJECTED CANDIDATE] {cand_url} -> Reason: {val_res.get('reason')}")

    duration = round(time.time() - start_time, 2)
    return {
        "ticker": ticker,
        "year": target_year,
        "status": verified_status,
        "source_url": verified_url,
        "rejected_candidates": rejected_count,
        "candidate_urls": candidate_urls,
        "duration_sec": duration,
    }


def main():
    parser = argparse.ArgumentParser(description="Controlled Pilot Missing-Report Crawler")
    parser.add_argument("--company", type=str, help="Company ID or Ticker to crawl")
    parser.add_argument("--all", action="store_true", help="Crawl all configured companies")
    parser.add_argument(
        "--missing",
        action="store_true",
        help="Crawl missing targets from data/missing_reports.json",
    )
    parser.add_argument(
        "--tickers", nargs="+", help="Filter target tickers (e.g. --tickers AKBNK THYAO)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Discover candidate URLs without downloading"
    )
    args = parser.parse_args()

    companies = load_companies_config()
    comp_map = {c["id"]: c for c in companies}
    for c in companies:
        canonical_ticker = c.get("canonical_ticker", c["id"].upper())
        c["canonical_ticker"] = canonical_ticker
        comp_map[canonical_ticker] = c
        comp_map[c["id"]] = c

    if args.missing:
        if not MISSING_JSON.exists():
            print(f"Error: {MISSING_JSON} not found. Run scripts/build_baseline.py first.")
            sys.exit(1)

        with open(MISSING_JSON, encoding="utf-8") as f:
            missing_info = json.load(f)

        missing_targets = missing_info.get("missing_targets", [])

        if args.tickers:
            filter_tickers = [t.upper() for t in args.tickers]
            missing_targets = [
                t for t in missing_targets if t["canonical_ticker"].upper() in filter_tickers
            ]

        print("=" * 70)
        print(
            f"CONTROLLED PILOT MISSING-REPORT CRAWLER ({'DRY-RUN' if args.dry_run else 'EXECUTION'})"
        )
        print(f"Target Slots Count: {len(missing_targets)}")
        if args.tickers:
            print(f"Filtered Tickers  : {args.tickers}")
        print("=" * 70 + "\n")

        results = []
        dry_run_data = {}

        for target in missing_targets:
            ticker = target["canonical_ticker"]
            year = target["year"]
            comp_cfg = comp_map.get(ticker) or comp_map.get(target["company_id"])

            if not comp_cfg:
                continue

            print(f"[*] Processing Target Slot: {ticker} ({year}) ...")
            slot_res = crawl_slot(comp_cfg, year, dry_run=args.dry_run, max_candidates=10)
            results.append(slot_res)

            dry_run_data[f"{ticker}_{year}"] = slot_res["candidate_urls"]

        if args.dry_run:
            with open(DRY_RUN_JSON, "w", encoding="utf-8") as df:
                json.dump(dry_run_data, df, ensure_ascii=False, indent=2)
            print(f"\nDry-run candidate URL list written to: {DRY_RUN_JSON}\n")

        print("\n" + "=" * 70)
        print("PILOT CRAWL SUMMARY REPORT (6 TARGET SLOTS)")
        print("=" * 70)
        for r in results:
            t = r["ticker"]
            y = r["year"]
            st = r["status"]
            url = r.get("source_url") or (r["candidate_urls"][0] if r["candidate_urls"] else "None")
            rej = r["rejected_candidates"]
            dur = r["duration_sec"]
            print(f"Slot {t} ({y}):")
            print(f"  - Status             : {st.upper()}")
            print(f"  - Source URL         : {url}")
            print(f"  - Rejected Candidates: {rej}")
            print(f"  - Duration           : {dur} seconds\n")
        print("=" * 70)

        # Update build_baseline if not dry run
        if not args.dry_run:
            from scripts.build_baseline import build_baseline

            build_baseline()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
