#!/usr/bin/env python3
"""
scripts/harvest_via_yahoo.py

Harvests annual report PDFs using Yahoo Search endpoint, which reliably returns
direct media URLs and exact IR page paths for Turkish corporate disclosures.
"""

import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import quote, unquote

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()

try:
    import fitz
except ImportError:
    fitz = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
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


def search_yahoo_urls(query: str) -> list[str]:
    """Extract destination URLs from Yahoo Search results."""
    urls = []
    try:
        y_url = f"https://search.yahoo.com/search?p={quote(query)}"
        resp = SESSION.get(y_url, timeout=8)
        if resp.status_code == 200:
            for match in re.findall(r"/RU=([^/]+)/", resp.text):
                target = unquote(match)
                if target.startswith("http") and ("yahoo.com" not in target):
                    urls.append(target)
    except Exception as e:
        print(f"    [Yahoo Error]: {e}", flush=True)

    return urls


def crawl_ir_html_page(url: str) -> list[str]:
    """If search gives an IR html page, crawl it for PDF links."""
    pdf_links = []
    try:
        resp = SESSION.get(url, timeout=8, verify=False)
        if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if ".pdf" in href.lower():
                    full_url = requests.compat.urljoin(url, href)
                    pdf_links.append(full_url)
    except Exception:
        pass
    return pdf_links


def test_and_save_pdf(url: str, ticker: str, target_year: int, comp_cfg: dict) -> dict:
    """Download candidate PDF and run validation."""
    try:
        resp = SESSION.get(url, timeout=20, verify=False, stream=True)
        if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
            return {"status": "failed", "reason": f"HTTP {resp.status_code} or non-PDF"}

        content = resp.content
        if len(content) < 200_000:
            return {"status": "failed", "reason": f"File too small ({len(content)} bytes)"}

        ticker_dir = RAW_DIR / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)
        temp_path = ticker_dir / f"temp_yahoo_{hashlib.md5(url.encode()).hexdigest()[:6]}.pdf"
        temp_path.write_bytes(content)

        val = validate_pdf_content(temp_path, comp_cfg)

        if val["status"] == "verified":
            detected_year = val.get("year")
            if detected_year != target_year:
                temp_path.unlink(missing_ok=True)
                return {
                    "status": "failed",
                    "reason": f"Year mismatch: expected {target_year}, got {detected_year}",
                }

            text = ""
            if fitz:
                try:
                    doc = fitz.open(temp_path)
                    for i in range(min(5, len(doc))):
                        text += doc[i].get_text("text") + "\n"
                    doc.close()
                except Exception:
                    pass

            lang = "en" if "annual report" in text.lower() and "faaliyet" not in text.lower() else "tr"
            final_name = f"{ticker}__{target_year}__annual_report__{lang}.pdf"
            final_path = ticker_dir / final_name

            shutil.move(temp_path, final_path)
            return {
                "status": "success",
                "final_path": str(final_path),
                "url": url,
                "pages": val.get("page_count", 0),
            }
        else:
            temp_path.unlink(missing_ok=True)
            return {"status": "failed", "reason": val.get("reason", "Validation failed")}
    except Exception as e:
        return {"status": "failed", "reason": str(e)}


def process_target_slot(ticker: str, year: int, comp_cfg: dict) -> bool:
    print(f"\n[YAHOO TARGET] {ticker} {year} ...", flush=True)

    # Check if already present
    ticker_dir = RAW_DIR / ticker
    if ticker_dir.exists():
        for p in ticker_dir.glob(f"{ticker}__{year}__annual_report__*.pdf"):
            if p.stat().st_size > 200_000:
                print(f"  ✓ Already verified: {p.name}", flush=True)
                return True

    aliases = comp_cfg.get("aliases", [comp_cfg["name"]])
    name = aliases[0]
    domain = comp_cfg.get("official_domains", [""])[0].replace("https://", "").replace("http://", "").split("/")[0]

    queries = [
        f'site:{domain} "faaliyet raporu" {year} pdf',
        f'site:{domain} "annual report" {year} pdf',
        f'site:{domain} "entegre" {year} pdf',
        f'"{name}" "faaliyet raporu" {year} pdf',
        f'"{name}" "annual report" {year} pdf',
        f'"{ticker}" "faaliyet raporu" {year} pdf',
    ]

    candidate_urls = set()

    for q in queries:
        urls = search_yahoo_urls(q)
        for u in urls:
            u_lower = u.lower()
            if ".pdf" in u_lower:
                if "sustainability" not in u_lower or "faaliyet" in u_lower or "entegre" in u_lower:
                    if "sunum" not in u_lower and "presentation" not in u_lower:
                        candidate_urls.add(u)
            else:
                # Crawl IR html pages returned by search
                crawled_pdfs = crawl_ir_html_page(u)
                for cp in crawled_pdfs:
                    cp_lower = cp.lower()
                    if str(year) in cp_lower or "faaliyet" in cp_lower or "annual" in cp_lower:
                        candidate_urls.add(cp)

    print(f"  Collected {len(candidate_urls)} candidate URLs.", flush=True)

    for cand_url in list(candidate_urls)[:15]:
        print(f"    Testing: {cand_url[:85]} ...", flush=True)
        res = test_and_save_pdf(cand_url, ticker, year, comp_cfg)
        if res["status"] == "success":
            print(
                f"    ✓ SUCCESS! Verified {ticker} {year} -> {Path(res['final_path']).name} ({res['pages']} pages)",
                flush=True,
            )
            return True
        else:
            print(f"      ✗ Rejected ({res['reason']})", flush=True)

    print(f"  ✗ Target slot unfulfilled: {ticker} {year}", flush=True)
    return False


def main():
    companies = load_companies_config()
    comp_map = {c["id"]: c for c in companies}

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
    print("=" * 70, flush=True)
    print(f"STARTING YAHOO DISCOVERY HARVESTER FOR {len(missing_targets)} MISSING SLOTS", flush=True)
    print("=" * 70 + "\n", flush=True)

    solved = 0
    for target in missing_targets:
        ticker = target["canonical_ticker"]
        year = target["year"]
        cfg = ticker_map.get(ticker) or comp_map.get(target["company_id"])

        if not cfg:
            continue

        success = process_target_slot(ticker, year, cfg)
        if success:
            solved += 1
        time.sleep(0.5)

    print("\n" + "=" * 70, flush=True)
    print(f"Harvester completed. Newly solved slots: {solved}", flush=True)
    print("Running build_baseline.py ...", flush=True)
    print("=" * 70, flush=True)
    build_baseline()


if __name__ == "__main__":
    main()
