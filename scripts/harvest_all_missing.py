#!/usr/bin/env python3
"""
scripts/harvest_all_missing.py

Comprehensive harvester for missing annual reports across all target companies.
Combines multiple search engine queries (Google, Bing, DDG) and direct URL path patterns.
"""

import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

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


def search_google_links(query: str) -> list[str]:
    urls = []
    try:
        g_url = f"https://www.google.com/search?q={quote(query)}"
        resp = SESSION.get(g_url, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/url?q=" in href:
                    actual = href.split("/url?q=")[1].split("&")[0]
                    if ".pdf" in actual.lower():
                        urls.append(actual)
    except Exception:
        pass
    return urls


def search_bing_links(query: str) -> list[str]:
    urls = []
    try:
        b_url = f"https://www.bing.com/search?q={quote(query)}"
        resp = SESSION.get(b_url, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".pdf" in href.lower():
                    urls.append(href)
    except Exception:
        pass
    return urls


def search_ddg_links(query: str) -> list[str]:
    urls = []
    try:
        r = SESSION.post("https://html.duckduckgo.com/html/", data={"q": query}, timeout=6)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", class_="result__url"):
                href = a.get("href", "")
                if "uddg=" in href:
                    actual = parse_qs(urlparse(href).query).get("uddg", [""])[0]
                else:
                    actual = href
                if actual and ".pdf" in actual.lower():
                    urls.append(actual)
    except Exception:
        pass
    return urls


def test_and_save_pdf(url: str, ticker: str, target_year: int, comp_cfg: dict) -> dict:
    try:
        resp = SESSION.get(url, timeout=12, verify=False, stream=True)
        if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
            return {"status": "failed", "reason": f"HTTP {resp.status_code} or non-PDF"}

        content = resp.content
        if len(content) < 200_000:  # Real annual reports are at least 200KB
            return {"status": "failed", "reason": f"File too small ({len(content)} bytes)"}

        ticker_dir = RAW_DIR / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)

        temp_path = ticker_dir / f"temp_harvest_{hashlib.md5(url.encode()).hexdigest()[:6]}.pdf"
        temp_path.write_bytes(content)

        val = validate_pdf_content(temp_path, comp_cfg)

        if val["status"] == "verified":
            detected_year = val.get("year")
            if detected_year != target_year:
                temp_path.unlink(missing_ok=True)
                return {
                    "status": "failed",
                    "reason": f"Year mismatch ({detected_year} vs {target_year})",
                }

            # Extract text to verify language
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
    print(f"\n[HARVEST TARGET] {ticker} {year} ...", flush=True)

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
        f'"{name}" "faaliyet raporu" {year} filetype:pdf',
        f'"{name}" "annual report" {year} filetype:pdf',
        f'"{name}" "entegre faaliyet" {year} filetype:pdf',
        f'site:{domain} "faaliyet raporu" {year} filetype:pdf',
        f'site:{domain} "annual report" {year} filetype:pdf',
        f"site:{domain} {year} filetype:pdf",
    ]

    candidate_urls = set()
    for q in queries:
        for url_func in [search_google_links, search_bing_links, search_ddg_links]:
            res_urls = url_func(q)
            for u in res_urls:
                u_lower = u.lower()
                if "sustainability" not in u_lower or "faaliyet" in u_lower or "entegre" in u_lower:
                    if "sunum" not in u_lower and "presentation" not in u_lower:
                        candidate_urls.add(u)

    print(f"  Collected {len(candidate_urls)} candidate URLs across search engines.", flush=True)

    for cand_url in list(candidate_urls)[:15]:
        print(f"    Testing: {cand_url[:80]} ...", flush=True)
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
    print(f"STARTING COMPREHENSIVE PDF HARVESTER FOR {len(missing_targets)} MISSING SLOTS", flush=True)
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
    print(f"Harvester completed. Solved {solved} target slots.", flush=True)
    print("Running build_baseline.py ...", flush=True)
    print("=" * 70, flush=True)
    build_baseline()


if __name__ == "__main__":
    main()
