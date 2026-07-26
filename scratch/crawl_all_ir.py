#!/usr/bin/env python3
import hashlib
import shutil
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.build_baseline import build_baseline
from scripts.validate_reports import load_companies_config, validate_pdf_content

RAW_DIR = PROJECT_ROOT / "data" / "raw"
companies = load_companies_config()

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

ir_pages = {
    "AKBNK": ["https://www.akbankinvestorrelations.com/tr/faaliyet-raporlari.aspx"],
    "ARCLK": [
        "https://www.arcelikglobal.com/tr/yatirimci-iliskileri/",
        "https://www.arcelikglobal.com/en/investor-relations/",
    ],
    "ASELS": [
        "https://www.aselsan.com.tr/tr/yatirimci-iliskileri/faaliyet-raporlari",
        "https://www.aselsan.com/tr/yatirimci-iliskileri/faaliyet-raporlari",
    ],
    "FROTO": [
        "https://www.fordotosan.com.tr/tr/yatirimci-iliskileri/",
        "https://www.fordotosan.com.tr/en/investor-relations/",
    ],
    "KCHOL": [
        "https://www.koc.com.tr/yatirimci-iliskileri/",
        "https://www.koc.com.tr/en/investor-relations/",
    ],
    "MGROS": [
        "https://www.migroskurumsal.com/yatirimci-iliskileri/raporlarimiz",
        "https://www.migroskurumsal.com/tr/raporlarimiz",
    ],
    "SISE": [
        "https://www.sisecam.com.tr/tr/yatirimci-iliskileri/",
        "https://www.sisecam.com.tr/en/investor-relations/",
    ],
    "TCELL": [
        "https://www.turkcell.com.tr/hakkimizda/yatirimci-iliskileri/",
        "https://www.turkcell.com.tr/en/aboutus/investor-relations",
    ],
    "THYAO": [
        "https://investor.turkishairlines.com/tr/",
        "https://investor.turkishairlines.com/en/",
    ],
    "TUPRS": [
        "https://www.tupras.com.tr/raporlar",
        "https://www.tupras.com.tr/yatirimci-iliskileri",
    ],
}

comp_id_map = {
    "AKBNK": "akbank",
    "ARCLK": "arcelik",
    "ASELS": "aselsan",
    "FROTO": "ford_otosan",
    "KCHOL": "koc_holding",
    "MGROS": "migros",
    "SISE": "sisecam",
    "TCELL": "turkcell",
    "THYAO": "thyao",
    "TUPRS": "tupras",
}

print("=" * 70, flush=True)
print("CRAWLING OFFICIAL IR PAGES FOR PDF DOWNLOAD LINKS", flush=True)
print("=" * 70, flush=True)

solved_count = 0

for ticker, urls in ir_pages.items():
    comp_id = comp_id_map[ticker]
    comp_cfg = [c for c in companies if c["id"] == comp_id][0]
    print(f"\n--- {ticker} ({comp_cfg['name']}) ---", flush=True)

    pdf_candidates = set()
    for page_url in urls:
        print(f"  Fetching: {page_url} ...", flush=True)
        try:
            r = requests.get(page_url, headers=headers, verify=False, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    full = urljoin(page_url, href)
                    if ".pdf" in full.lower():
                        # Filter to likely annual report pdfs
                        full_lower = full.lower()
                        text_lower = a.get_text(strip=True).lower()
                        if any(
                            kw in full_lower or kw in text_lower
                            for kw in ["faaliyet", "annual", "entegre", "2023", "2024", "2025"]
                        ):
                            pdf_candidates.add(full)
                for tag in soup.find_all(attrs={"data-href": True}):
                    pdf_candidates.add(urljoin(page_url, tag["data-href"]))
                for tag in soup.find_all(attrs={"data-url": True}):
                    pdf_candidates.add(urljoin(page_url, tag["data-url"]))
            else:
                print(f"    HTTP {r.status_code}", flush=True)
        except Exception as e:
            print(f"    Error: {e}", flush=True)

    print(f"  Found {len(pdf_candidates)} filtered PDF candidate links.", flush=True)

    for cand_url in list(pdf_candidates):
        print(f"    Testing: {cand_url[:90]} ...", flush=True)
        try:
            resp = requests.get(cand_url, headers=headers, verify=False, timeout=15)
            if (
                resp.status_code == 200
                and resp.content.startswith(b"%PDF")
                and len(resp.content) > 100_000
            ):
                ticker_dir = RAW_DIR / ticker
                ticker_dir.mkdir(parents=True, exist_ok=True)
                temp = (
                    ticker_dir / f"temp_crawl_{hashlib.md5(cand_url.encode()).hexdigest()[:6]}.pdf"
                )
                temp.write_bytes(resp.content)

                val = validate_pdf_content(temp, comp_cfg)
                if val["status"] == "verified":
                    year = val["year"]
                    lang = "tr"
                    try:
                        import fitz

                        doc = fitz.open(temp)
                        text = ""
                        for i in range(min(5, len(doc))):
                            text += doc[i].get_text("text") + "\n"
                        doc.close()
                        if "annual report" in text.lower() and "faaliyet" not in text.lower():
                            lang = "en"
                    except Exception:
                        pass

                    final = ticker_dir / f"{ticker}__{year}__annual_report__{lang}.pdf"
                    if not final.exists():
                        shutil.move(temp, final)
                        print(
                            f"    ✓ VERIFIED MATCH: {final.name} ({val.get('page_count')} pages)",
                            flush=True,
                        )
                        solved_count += 1
                    else:
                        print(f"    ✓ Verified duplicate for year {year}: {final.name}", flush=True)
                        temp.unlink(missing_ok=True)
                else:
                    print(f"      ✗ Validation failed: {val.get('reason')}", flush=True)
                    temp.unlink(missing_ok=True)
            else:
                print(
                    f"      ✗ Not a valid PDF (HTTP {resp.status_code}, len={len(resp.content)})",
                    flush=True,
                )
        except Exception as e:
            print(f"      ✗ Request error: {e}", flush=True)

print("\n" + "=" * 70, flush=True)
print(f"Crawl completed. Newly solved slots: {solved_count}", flush=True)
print("Running build_baseline.py ...", flush=True)
print("=" * 70, flush=True)
build_baseline()
