#!/usr/bin/env python3
"""
scripts/auto_discover_reports.py

Fast multi-threaded PDF auto-discovery, download, and validation script.
Searches DuckDuckGo HTML endpoint for official PDF reports and tests direct candidates in parallel.
"""

import hashlib
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
QUARANTINE_DIR = PROJECT_ROOT / "data" / "quarantine"
MISSING_JSON = PROJECT_ROOT / "data" / "missing_reports.json"

sys.path.insert(0, str(PROJECT_ROOT))
from scripts.build_baseline import build_baseline
from scripts.validate_reports import load_companies_config, validate_pdf_content

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.7",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def search_ddg_for_pdfs(query: str, max_results: int = 15) -> list[str]:
    """Search DuckDuckGo HTML endpoint for candidate PDF links."""
    pdf_urls = []
    try:
        url = "https://html.duckduckgo.com/html/"
        data = {"q": query}
        resp = SESSION.post(url, data=data, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", class_="result__url"):
                href = a.get("href", "")
                if "uddg=" in href:
                    parsed = parse_qs(urlparse(href).query)
                    actual_url = parsed.get("uddg", [""])[0]
                else:
                    actual_url = href

                if actual_url and (".pdf" in actual_url.lower() or "pdf" in actual_url.lower()):
                    pdf_urls.append(actual_url)
    except Exception as e:
        print(f"    [DDG Search Warning]: {e}", flush=True)

    return pdf_urls[:max_results]


def get_search_queries(ticker: str, year: int, comp_cfg: dict) -> list[str]:
    """Build targeted search queries for a company and year."""
    comp_name = comp_cfg["name"]
    domains = comp_cfg.get("official_domains", [])
    aliases = comp_cfg.get("aliases", [comp_name])
    primary_alias = aliases[0] if aliases else comp_name

    queries = []

    # 1. Official domain searches
    for domain in domains:
        clean_domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
        queries.append(f'site:{clean_domain} filetype:pdf "faaliyet" {year}')
        queries.append(f'site:{clean_domain} filetype:pdf "annual report" {year}')

    # 2. General company + year searches
    queries.append(f'"{primary_alias}" "faaliyet raporu" {year} filetype:pdf')
    queries.append(f'"{primary_alias}" "entegre faaliyet raporu" {year} filetype:pdf')
    queries.append(f'"{primary_alias}" "annual report" {year} filetype:pdf')

    return queries


def is_valid_pdf_url(url: str) -> bool:
    """Pre-filter URLs to skip non-PDF or non-report links."""
    u_lower = url.lower()
    if "sustainability" in u_lower and "faaliyet" not in u_lower and "entegre" not in u_lower:
        return False
    if "sunum" in u_lower or "presentation" in u_lower:
        return False
    return not ("ek-bilgiler" in u_lower or "ek_bilgiler" in u_lower)


def download_and_validate(url: str, ticker: str, target_year: int, comp_cfg: dict) -> dict:
    """Downloads candidate PDF and runs validate_pdf_content."""
    try:
        resp = SESSION.get(url, timeout=10, verify=False, allow_redirects=True, stream=True)
        if resp.status_code != 200:
            return {"status": "failed", "url": url, "reason": f"HTTP {resp.status_code}"}

        content = resp.content
        if not content.startswith(b"%PDF"):
            return {
                "status": "failed",
                "url": url,
                "reason": "Not a PDF file (missing %PDF header)",
            }

        if len(content) < 100_000:  # Must be at least 100 KB for annual reports
            return {
                "status": "failed",
                "url": url,
                "reason": f"File too small ({len(content)} bytes)",
            }

        ticker_dir = RAW_DIR / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)
        temp_filename = (
            f"{ticker}__{target_year}__temp_{hashlib.md5(url.encode()).hexdigest()[:6]}.pdf"
        )
        temp_path = ticker_dir / temp_filename
        temp_path.write_bytes(content)

        val_res = validate_pdf_content(temp_path, comp_cfg)

        if val_res["status"] == "verified":
            detected_year = val_res.get("year")
            if detected_year != target_year:
                temp_path.unlink(missing_ok=True)
                return {
                    "status": "failed",
                    "url": url,
                    "reason": f"Year mismatch: expected {target_year}, detected {detected_year}",
                }

            # Language detection
            text = ""
            if fitz:
                try:
                    doc = fitz.open(temp_path)
                    for i in range(min(5, len(doc))):
                        text += doc[i].get_text("text") + "\n"
                    doc.close()
                except Exception:
                    pass

            lang = (
                "en" if "annual report" in text.lower() and "faaliyet" not in text.lower() else "tr"
            )
            final_filename = f"{ticker}__{target_year}__annual_report__{lang}.pdf"
            final_path = ticker_dir / final_filename

            shutil.move(temp_path, final_path)
            return {
                "status": "success",
                "final_path": str(final_path),
                "url": url,
                "year": target_year,
                "language": lang,
                "page_count": val_res.get("page_count", 0),
                "sha256": val_res.get("sha256"),
            }
        else:
            temp_path.unlink(missing_ok=True)
            return {
                "status": "failed",
                "url": url,
                "reason": val_res.get("reason", "Validation failed"),
            }

    except Exception as e:
        return {"status": "failed", "url": url, "reason": str(e)}


def discover_for_target(ticker: str, target_year: int, comp_cfg: dict) -> bool:
    """Attempts to find and download a verified annual report for target slot."""
    print(f"\n[TARGET] {ticker} {target_year} ...", flush=True)

    # Check if already present in RAW_DIR
    ticker_dir = RAW_DIR / ticker
    if ticker_dir.exists():
        for p in ticker_dir.glob(f"{ticker}__{target_year}__annual_report__*.pdf"):
            if p.stat().st_size > 100_000:
                print(f"  ✓ Already exists: {p.name}", flush=True)
                return True

    queries = get_search_queries(ticker, target_year, comp_cfg)
    seen_urls = set()
    candidate_urls = []

    # Gather candidates from DDG queries
    for q in queries:
        urls = search_ddg_for_pdfs(q)
        for u in urls:
            if u not in seen_urls and is_valid_pdf_url(u):
                seen_urls.add(u)
                candidate_urls.append(u)

    print(f"  Found {len(candidate_urls)} candidate URLs to test.", flush=True)
    if not candidate_urls:
        print(f"  ✗ No candidate URLs found for {ticker} {target_year}", flush=True)
        return False

    # Parallel download and test candidates
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(download_and_validate, url, ticker, target_year, comp_cfg): url
            for url in candidate_urls[:12]
        }

        for future in as_completed(futures):
            res = future.result()
            if res["status"] == "success":
                print(
                    f"  ✓ SUCCESS! Verified {ticker} {target_year} -> {Path(res['final_path']).name} (URL: {res['url'][:80]})",
                    flush=True,
                )
                # Cancel other pending futures if possible
                executor.shutdown(wait=False, cancel_futures=True)
                return True
            else:
                print(
                    f"    ✗ Candidate rejected: {res['url'][:70]}... Reason: {res['reason']}",
                    flush=True,
                )

    print(f"  ✗ Could not locate verified report for {ticker} {target_year}", flush=True)
    return False


def main():
    companies = load_companies_config()
    comp_map = {}
    for c in companies:
        canonical_ticker = c.get("canonical_ticker", c["id"].upper())
        c["canonical_ticker"] = canonical_ticker
        comp_map[canonical_ticker] = c
        comp_map[c["id"]] = c

    ticker_map = {
        "AKBNK": comp_map.get("akbank"),
        "ARCLK": comp_map.get("arcelik"),
        "ASELS": comp_map.get("aselsan"),
        "FROTO": comp_map.get("ford_otosan"),
        "KCHOL": comp_map.get("koc_holding"),
        "MGROS": comp_map.get("migros"),
        "SISE": comp_map.get("sisecam"),
        "TCELL": comp_map.get("turkcell"),
        "THYAO": comp_map.get("thyao"),
        "TUPRS": comp_map.get("tupras"),
    }

    if not MISSING_JSON.exists():
        build_baseline()

    with open(MISSING_JSON, encoding="utf-8") as f:
        missing_data = json.load(f)

    missing_targets = missing_data.get("missing_targets", [])
    print(
        f"Starting Multi-Threaded Auto-Discovery for {len(missing_targets)} missing targets...\n",
        flush=True,
    )

    success_count = 0
    for target in missing_targets:
        ticker = target["canonical_ticker"]
        year = target["year"]
        comp_cfg = ticker_map.get(ticker) or comp_map.get(target["company_id"])

        if not comp_cfg:
            print(f"Warning: No config for {ticker}", flush=True)
            continue

        found = discover_for_target(ticker, year, comp_cfg)
        if found:
            success_count += 1

    print("\n" + "=" * 70, flush=True)
    print(
        f"Auto-Discovery phase finished ({success_count} slots solved). Running build_baseline.py...",
        flush=True,
    )
    print("=" * 70, flush=True)
    build_baseline()


if __name__ == "__main__":
    main()
