#!/usr/bin/env python3
import re
import sys
from pathlib import Path

import fitz

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = PROJECT_ROOT / "data" / "archive"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
MISSING_JSON = PROJECT_ROOT / "data" / "missing_reports.json"

sys.path.insert(0, str(PROJECT_ROOT))
from scripts.validate_reports import load_companies_config

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

print("=" * 70)
print("INSPECTING ARCHIVED PDFS FOR MISSING TARGETS")
print("=" * 70)

archive_pdfs = list(ARCHIVE_DIR.glob("**/*.pdf"))
print(f"Found {len(archive_pdfs)} archived PDFs.\n")

for p in archive_pdfs:
    ticker = p.parent.name.upper()
    cfg = ticker_map.get(ticker)
    if not cfg:
        continue

    doc = fitz.open(p)
    page_count = len(doc)
    text = ""
    for i in range(min(5, page_count)):
        text += doc[i].get_text("text") + "\n"
    doc.close()

    # Find years mentioned
    years = re.findall(r"\b(202[0-6])\b", text)
    from collections import Counter

    year_counts = Counter(int(y) for y in years)

    fn_years = re.findall(r"\b(202[0-6])\b", p.name)

    print(f"File: {p.relative_to(PROJECT_ROOT)}")
    print(
        f"  Pages: {page_count}, Filename years: {fn_years}, Text years top: {year_counts.most_common(3)}"
    )
    print(f"  First line: {text.splitlines()[0] if text.splitlines() else 'Empty'}")
    print("-" * 50)
