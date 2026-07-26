#!/usr/bin/env python3
"""
scripts/solve_remaining_10.py

Targeted solver for the 10 remaining missing annual report slots:
- ARCLK 2025
- ASELS 2025
- FROTO 2025
- KCHOL 2023, 2025
- SISE 2023, 2025
- TCELL 2024, 2025
- THYAO 2025
"""

import hashlib
import re
import shutil
import sys
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
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.build_baseline import build_baseline
from scripts.validate_reports import load_companies_config, validate_pdf_content

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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.7",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

REMAINING_SLOTS = [
    ("ARCLK", 2025),
    ("ASELS", 2025),
    ("FROTO", 2025),
    ("KCHOL", 2023),
    ("KCHOL", 2025),
    ("SISE", 2023),
    ("SISE", 2025),
    ("TCELL", 2024),
    ("TCELL", 2025),
    ("THYAO", 2025),
]


def search_yahoo(query: str) -> list[str]:
    urls = []
    try:
        r = SESSION.get(f"https://search.yahoo.com/search?p={quote(query)}", timeout=8)
        if r.status_code == 200:
            for m in re.findall(r"/RU=([^/]+)/", r.text):
                target = unquote(m)
                if target.startswith("http") and "yahoo.com" not in target:
                    urls.append(target)
    except Exception:
        pass
    return urls


def crawl_page_pdfs(url: str) -> list[str]:
    links = []
    try:
        r = SESSION.get(url, timeout=8, verify=False)
        if r.status_code == 200 and "text/html" in r.headers.get("Content-Type", ""):
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if ".pdf" in href.lower():
                    links.append(requests.compat.urljoin(url, href))
    except Exception:
        pass
    return links


def test_and_save(url: str, ticker: str, target_year: int, cfg: dict) -> bool:
    try:
        r = SESSION.get(url, timeout=20, verify=False, stream=True)
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            return False

        content = r.content
        if len(content) < 150_000:
            return False

        ticker_dir = RAW_DIR / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)
        temp = ticker_dir / f"temp_solv_{hashlib.md5(url.encode()).hexdigest()[:6]}.pdf"
        temp.write_bytes(content)

        # Check page count
        page_count = 0
        text = ""
        if fitz:
            try:
                doc = fitz.open(temp)
                page_count = len(doc)
                for i in range(min(5, page_count)):
                    text += doc[i].get_text("text") + "\n"
                doc.close()
            except Exception:
                pass

        if page_count < 10:
            temp.unlink(missing_ok=True)
            return False

        val = validate_pdf_content(temp, cfg)
        if val["status"] == "verified":
            detected_year = val.get("year")
            if detected_year != target_year:
                temp.unlink(missing_ok=True)
                return False

            lang = (
                "en" if "annual report" in text.lower() and "faaliyet" not in text.lower() else "tr"
            )
            final_name = f"{ticker}__{target_year}__annual_report__{lang}.pdf"
            final_path = ticker_dir / final_name
            shutil.move(temp, final_path)
            print(
                f"  ✓ SOLVED {ticker} {target_year} -> {final_name} ({page_count} pages)",
                flush=True,
            )
            return True
        else:
            temp.unlink(missing_ok=True)
            return False
    except Exception:
        return False


def main():
    print("=" * 70)
    print("SOLVING 10 REMAINING MISSING TARGET SLOTS")
    print("=" * 70 + "\n")

    solved_count = 0

    for ticker, year in REMAINING_SLOTS:
        print(f"[SLOT] {ticker} {year} ...", flush=True)
        cfg = ticker_map[ticker]

        # Check if already present
        ticker_dir = RAW_DIR / ticker
        if ticker_dir.exists():
            existing = list(ticker_dir.glob(f"{ticker}__{year}__annual_report__*.pdf"))
            if existing and existing[0].stat().st_size > 150_000:
                print(f"  ✓ Already solved: {existing[0].name}", flush=True)
                solved_count += 1
                continue

        name = cfg["aliases"][0]
        domain = (
            cfg.get("official_domains", [""])[0]
            .replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
        )

        queries = [
            f'site:{domain} "faaliyet raporu" {year} pdf',
            f'site:{domain} "annual report" {year} pdf',
            f'site:{domain} "entegre faaliyet" {year} pdf',
            f'"{name}" "faaliyet raporu" {year} pdf',
            f'"{name}" "annual report" {year} pdf',
            f'"{ticker}" "faaliyet raporu" {year} pdf',
        ]

        cand_urls = set()
        for q in queries:
            urls = search_yahoo(q)
            for u in urls:
                u_lower = u.lower()
                if ".pdf" in u_lower:
                    if (
                        "sustainability" not in u_lower
                        or "faaliyet" in u_lower
                        or "entegre" in u_lower
                    ) and "sunum" not in u_lower and "presentation" not in u_lower:
                        cand_urls.add(u)
                else:
                    crawled = crawl_page_pdfs(u)
                    for c_url in crawled:
                        if str(year) in c_url.lower() or "faaliyet" in c_url.lower():
                            cand_urls.add(c_url)

        print(f"  Testing {len(cand_urls)} candidate URLs...", flush=True)
        success = False
        for u in list(cand_urls)[:20]:
            if test_and_save(u, ticker, year, cfg):
                solved_count += 1
                success = True
                break

        if not success:
            print(f"  ✗ Unfulfilled: {ticker} {year}", flush=True)

    print("\n" + "=" * 70)
    print(f"Finished. Total solved: {solved_count}/10. Running build_baseline.py...")
    print("=" * 70)
    build_baseline()


if __name__ == "__main__":
    main()
