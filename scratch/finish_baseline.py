#!/usr/bin/env python3
import shutil
import sys
from pathlib import Path

import fitz
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.build_baseline import build_baseline
from scripts.validate_reports import load_companies_config, validate_pdf_content

companies = load_companies_config()
comp_map = {c["id"]: c for c in companies}
ticker_map = {
    "FROTO": comp_map["ford_otosan"],
    "KCHOL": comp_map["koc_holding"],
    "SISE": comp_map["sisecam"],
}

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

# 1. Save FROTO 2025, KCHOL 2023, KCHOL 2025
confirmed = [
    ("FROTO", 2025, "https://companiesmarketcap.com/annual-reports/63930.ar.en.2025.pdf"),
    ("KCHOL", 2023, "https://companiesmarketcap.com/annual-reports/16500.ar.en.2023.pdf"),
    ("KCHOL", 2025, "https://companiesmarketcap.com/annual-reports/16500.ar.en.2025.pdf"),
]

for ticker, year, url in confirmed:
    print(f"Downloading {ticker} {year} from {url}...")
    cfg = ticker_map[ticker]
    r = requests.get(url, headers=headers, verify=False, timeout=30)
    if r.status_code == 200 and r.content.startswith(b"%PDF"):
        raw = Path(f"data/raw/{ticker}")
        raw.mkdir(parents=True, exist_ok=True)
        temp = raw / f"temp_{year}.pdf"
        temp.write_bytes(r.content)
        val = validate_pdf_content(temp, cfg)
        print(f"  Validation: {val['status']}")
        if val["status"] == "verified":
            final = raw / f"{ticker}__{year}__annual_report__en.pdf"
            shutil.move(temp, final)
            print(f"  ✓ VERIFIED & SAVED: {final.name}")
        else:
            temp.unlink(missing_ok=True)

# 2. Find SISE (Şişecam) reports page on companiesmarketcap or sisecam.com.tr
print("\nSearching for Şişecam annual reports...")
try:
    r_cmc = requests.get(
        "https://companiesmarketcap.com/sisecam/annual-reports/", headers=headers, timeout=10
    )
    if r_cmc.status_code == 200:
        soup = BeautifulSoup(r_cmc.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower():
                full_url = requests.compat.urljoin(
                    "https://companiesmarketcap.com/sisecam/annual-reports/", href
                )
                print("  Found Sisecam CMC PDF link:", full_url)
                # Try downloading
                r_pdf = requests.get(full_url, headers=headers, verify=False, timeout=20)
                if r_pdf.status_code == 200 and r_pdf.content.startswith(b"%PDF"):
                    raw_sise = Path("data/raw/SISE")
                    raw_sise.mkdir(parents=True, exist_ok=True)
                    temp_sise = raw_sise / "temp_sise.pdf"
                    temp_sise.write_bytes(r_pdf.content)

                    # Extract year
                    doc = fitz.open(temp_sise)
                    text = ""
                    for i in range(min(5, len(doc))):
                        text += doc[i].get_text("text") + "\n"
                    doc.close()

                    val_sise = validate_pdf_content(temp_sise, ticker_map["SISE"])
                    if val_sise["status"] == "verified":
                        sise_year = val_sise["year"]
                        sise_lang = (
                            "en"
                            if "annual report" in text.lower() and "faaliyet" not in text.lower()
                            else "tr"
                        )
                        sise_final = raw_sise / f"SISE__{sise_year}__annual_report__{sise_lang}.pdf"
                        shutil.move(temp_sise, sise_final)
                        print(f"  ✓ VERIFIED & SAVED SISE {sise_year}: {sise_final.name}")
                    else:
                        temp_sise.unlink(missing_ok=True)
except Exception as e:
    print("  SISE search error:", e)

build_baseline()
