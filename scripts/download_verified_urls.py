#!/usr/bin/env python3
"""
Downloads and validates confirmed annual report URLs.
"""

import shutil
import sys
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.build_baseline import build_baseline
from scripts.validate_reports import load_companies_config, validate_pdf_content

companies = load_companies_config()
comp_map = {}
for c in companies:
    canonical = c.get("canonical_ticker", c["id"].upper())
    comp_map[canonical] = c

# Confirmed working URLs
CONFIRMED_URLS = [
    # FROTO
    (
        "FROTO",
        2023,
        "https://www.fordotosan.com.tr/assets/uploads/raporlar/ford-otosan-2023-entegre-faaliyet-raporu.pdf",
    ),
    (
        "FROTO",
        2024,
        "https://www.fordotosan.com.tr/assets/uploads/raporlar/ford-otosan-2024-entegre-faaliyet-raporu.pdf",
    ),
    (
        "FROTO",
        2025,
        "https://www.fordotosan.com.tr/assets/uploads/raporlar/ford-otosan-2025-entegre-faaliyet-raporu.pdf",
    ),
    # THYAO
    (
        "THYAO",
        2023,
        "https://investor.turkishairlines.com/documents/ThyInvestorRelations/2023-faaliyet-raporu.pdf",
    ),
    (
        "THYAO",
        2024,
        "https://investor.turkishairlines.com/documents/ThyInvestorRelations/2024-faaliyet-raporu.pdf",
    ),
    (
        "THYAO",
        2025,
        "https://investor.turkishairlines.com/documents/ThyInvestorRelations/2025-faaliyet-raporu.pdf",
    ),
    # MGROS 2025
    (
        "MGROS",
        2025,
        "https://migroskurumsalstr.blob.core.windows.net/migroskurumsalstr/-migros-tr2025-interaktif-639088646656876356.pdf",
    ),
]

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

ticker_to_cfg = {
    "FROTO": comp_map.get("ford_otosan"),
    "THYAO": comp_map.get("thyao"),
    "MGROS": comp_map.get("migros"),
}

print("=" * 70)
print("DOWNLOADING CONFIRMED ANNUAL REPORTS")
print("=" * 70)

success_count = 0
for ticker, year, url in CONFIRMED_URLS:
    print(f"\n[DOWNLOADING] {ticker} {year} from {url}...")
    cfg = ticker_to_cfg[ticker]
    try:
        r = requests.get(url, headers=headers, verify=False, timeout=30)
        if r.status_code == 200 and r.content.startswith(b"%PDF"):
            raw_target_dir = RAW_DIR / ticker
            raw_target_dir.mkdir(parents=True, exist_ok=True)
            temp = raw_target_dir / f"{ticker}__{year}__temp.pdf"
            temp.write_bytes(r.content)

            val = validate_pdf_content(temp, cfg)
            print(f"  Validation result: {val}")

            if val["status"] == "verified":
                # Check text for language
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

                final = raw_target_dir / f"{ticker}__{year}__annual_report__{lang}.pdf"
                shutil.move(temp, final)
                print(f"  ✓ VERIFIED & SAVED: {final.name}")
                success_count += 1
            else:
                print(f"  ✗ Validation failed: {val.get('reason')}")
                temp.unlink(missing_ok=True)
        else:
            print(f"  ✗ Download failed (HTTP {r.status_code})")
    except Exception as e:
        print(f"  ✗ Exception: {e}")

print("\n" + "=" * 70)
print(f"Downloaded {success_count} PDFs. Running build_baseline.py...")
print("=" * 70)
build_baseline()
