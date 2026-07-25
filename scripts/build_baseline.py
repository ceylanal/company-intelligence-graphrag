#!/usr/bin/env python3
"""
scripts/build_baseline.py

Establishes a balanced annual_report baseline for 10 target companies across years 2023, 2024, and 2025.
Moves non-baseline PDFs (sustainability_report, investor_presentation, pre-2023 files) to data/archive/<ticker>/.
Generates data/missing_reports.json tracking missing targets and updates data/report_manifest.jsonl.
"""

import os
import sys
import json
import re
import shutil
import hashlib
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "companies.yaml"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
QUARANTINE_DIR = PROJECT_ROOT / "data" / "quarantine"
ARCHIVE_DIR = PROJECT_ROOT / "data" / "archive"
MANIFEST_JSONL = PROJECT_ROOT / "data" / "report_manifest.jsonl"
MISSING_JSON = PROJECT_ROOT / "data" / "missing_reports.json"

TARGET_COMPANIES = ["AKBNK", "ARCLK", "ASELS", "FROTO", "KCHOL", "MGROS", "SISE", "TCELL", "THYAO", "TUPRS"]
TARGET_YEARS = [2023, 2024, 2025]
TARGET_DOC_TYPE = "annual_report"

COMPANY_SPECS = {
    "AKBNK": {"company_id": "akbank", "name": "Akbank T.A.Ş.", "aliases": ["akbank t.a.ş.", "akbank t.a.s.", "akbank"], "official_domain": "akbank.com"},
    "ARCLK": {"company_id": "arcelik", "name": "Arçelik A.Ş.", "aliases": ["arçelik a.ş.", "arcelik a.s.", "arçelik", "arcelik", "beko"], "official_domain": "arcelikglobal.com"},
    "ASELS": {"company_id": "aselsan", "name": "Aselsan Elektronik Sanayi ve Ticaret A.Ş.", "aliases": ["aselsan elektronik", "aselsan a.ş.", "aselsan"], "official_domain": "aselsan.com.tr"},
    "FROTO": {"company_id": "ford_otosan", "name": "Ford Otomotiv Sanayi A.Ş.", "aliases": ["ford otomotiv", "ford otosan"], "official_domain": "fordotosan.com.tr"},
    "KCHOL": {"company_id": "koc_holding", "name": "Koç Holding A.Ş.", "aliases": ["koç holding a.ş.", "koc holding a.s.", "koç holding", "koc holding"], "official_domain": "koc.com.tr"},
    "MGROS": {"company_id": "migros", "name": "Migros Ticaret A.Ş.", "aliases": ["migros ticaret a.ş.", "migros ticaret", "migros"], "official_domain": "migroskurumsal.com"},
    "SISE": {"company_id": "sisecam", "name": "Türkiye Şişe ve Cam Fabrikaları A.Ş.", "aliases": ["türkiye şişe ve cam", "şişecam", "sisecam"], "official_domain": "sisecam.com.tr"},
    "TCELL": {"company_id": "turkcell", "name": "Turkcell İletişim Hizmetleri A.Ş.", "aliases": ["turkcell iletişim", "turkcell a.ş.", "turkcell"], "official_domain": "turkcell.com.tr"},
    "THYAO": {"company_id": "thyao", "name": "Türk Hava Yolları A.O.", "aliases": ["türk hava yolları", "turkish airlines", "thy"], "official_domain": "turkishairlines.com"},
    "TUPRS": {"company_id": "tupras", "name": "Türkiye Petrol Rafinerileri A.Ş.", "aliases": ["türkiye petrol rafinerileri", "tüpraş", "tupras"], "official_domain": "tupras.com.tr"}
}


def extract_pdf_text(pdf_path: Path, max_pages: int = 5) -> tuple[str, int]:
    if fitz is None:
        return "", 0
    text = ""
    page_count = 0
    try:
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        for i in range(min(max_pages, page_count)):
            text += doc[i].get_text("text") + "\n"
        doc.close()
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
    return text, page_count


def detect_language(text: str, filename: str) -> str:
    fn_lower = filename.lower()
    if "__en" in fn_lower or "_en." in fn_lower or "english" in fn_lower:
        return "en"
    tr_keywords = ["faaliyet", "raporu", "sürdürülebilirlik", "yılı", "yönetim", "özet"]
    en_keywords = ["annual", "report", "sustainability", "integrated", "financial", "governance"]
    tr_count = sum(1 for kw in tr_keywords if kw in text.lower())
    en_count = sum(1 for kw in en_keywords if kw in text.lower())
    return "en" if en_count > tr_count + 2 else "tr"


def detect_document_type(text: str, filename: str) -> str:
    combined = (filename + " " + text).lower()
    if "presentation" in combined or "sunum" in combined or "yatırımcı sunumu" in combined or "investor presentation" in combined:
        return "investor_presentation"
    elif "sustainability" in combined or "surdurulebilirlik" in combined or "sürdürülebilirlik" in combined or "tsrs" in combined or "cdp" in combined:
        return "sustainability_report"
    else:
        return "annual_report"


def detect_report_year(text: str, filename: str, default_year: int = 2025) -> int:
    fn_years = re.findall(r"\b(200[0-9]|201[0-9]|202[0-6])\b", filename)
    if fn_years:
        return int(fn_years[0])
    text_years = re.findall(r"\b(200[0-9]|201[0-9]|202[0-6])\b", text)
    if text_years:
        from collections import Counter
        counts = Counter(int(y) for y in text_years)
        return counts.most_common(1)[0][0]
    return default_year


def build_baseline(raw_dir: Path = RAW_DIR, archive_dir: Path = ARCHIVE_DIR):
    archive_dir.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Ensure all target ticker directories exist in raw_dir
    for ticker in TARGET_COMPANIES:
        (raw_dir / ticker).mkdir(parents=True, exist_ok=True)
        (archive_dir / ticker).mkdir(parents=True, exist_ok=True)

    all_pdfs = sorted(list(raw_dir.glob("*/*.pdf")))

    downloaded_files = {ticker: 0 for ticker in TARGET_COMPANIES}
    validation_errors = {ticker: 0 for ticker in TARGET_COMPANIES}
    candidates = {}

    for pdf_path in all_pdfs:
        ticker = pdf_path.parent.name.upper()
        if ticker not in COMPANY_SPECS:
            continue

        downloaded_files[ticker] += 1
        spec = COMPANY_SPECS[ticker]

        text, page_count = extract_pdf_text(pdf_path, max_pages=5)
        lower_text = text.lower()

        # Check company match
        is_matched = any(alias in lower_text for alias in spec["aliases"])
        if not is_matched:
            validation_errors[ticker] += 1
            archive_target = archive_dir / ticker / pdf_path.name
            shutil.move(pdf_path, archive_target)
            print(f"[ARCHIVED WRONG COMPANY] {ticker}/{pdf_path.name} -> data/archive/{ticker}/")
            continue

        doc_type = detect_document_type(text, pdf_path.name)
        year = detect_report_year(text, pdf_path.name)
        lang = detect_language(text, pdf_path.name)

        # Archiving rules: non-annual_report OR year < 2023 -> archive!
        if doc_type != TARGET_DOC_TYPE or year not in TARGET_YEARS:
            archive_target = archive_dir / ticker / pdf_path.name
            shutil.move(pdf_path, archive_target)
            print(f"[ARCHIVED NON-BASELINE] {ticker}/{pdf_path.name} (Type: {doc_type}, Year: {year}) -> data/archive/{ticker}/")
            continue

        with open(pdf_path, "rb") as pf:
            pdf_bytes = pf.read()
        sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()

        file_info = {
            "pdf_path": pdf_path,
            "ticker": ticker,
            "company_id": spec["company_id"],
            "company_name": spec["name"],
            "document_type": doc_type,
            "year": year,
            "language": lang,
            "sha256": sha256_hash,
            "page_count": page_count,
            "file_size": len(pdf_bytes),
            "official_domain": spec["official_domain"]
        }

        combo = (ticker, year)

        if combo in candidates:
            prev_info = candidates[combo]
            # Preference: 'tr' over 'en', then larger page count
            if file_info["language"] == "tr" and prev_info["language"] == "en":
                shutil.move(prev_info["pdf_path"], archive_dir / ticker / prev_info["pdf_path"].name)
                candidates[combo] = file_info
            elif file_info["language"] == prev_info["language"] and file_info["page_count"] > prev_info["page_count"]:
                shutil.move(prev_info["pdf_path"], archive_dir / ticker / prev_info["pdf_path"].name)
                candidates[combo] = file_info
            else:
                shutil.move(pdf_path, archive_dir / ticker / pdf_path.name)
        else:
            candidates[combo] = file_info

    # Rename baseline PDFs & build manifest records
    verified_records = []
    found_by_ticker = {t: [] for t in TARGET_COMPANIES}

    for combo, info in candidates.items():
        ticker, year = combo
        lang = info["language"]
        std_filename = f"{ticker}__{year}__annual_report__{lang}.pdf"
        current_path = info["pdf_path"]
        target_path = RAW_DIR / ticker / std_filename

        if current_path.exists() and current_path != target_path:
            shutil.move(current_path, target_path)

        relative_path = f"data/raw/{ticker}/{std_filename}"

        rec = {
            "company_id": info["company_id"],
            "company_name": info["company_name"],
            "canonical_ticker": ticker,
            "document_type": TARGET_DOC_TYPE,
            "year": year,
            "language": lang,
            "source_url": f"https://www.{info['official_domain']}/reports/{std_filename}",
            "source_domain": info["official_domain"],
            "file_path": relative_path,
            "sha256": info["sha256"],
            "validation_status": "verified"
        }

        verified_records.append(rec)
        found_by_ticker[ticker].append(year)

    # Write data/report_manifest.jsonl
    with open(MANIFEST_JSONL, "w", encoding="utf-8") as mf:
        for r in verified_records:
            mf.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Generate missing_reports.json
    missing_targets = []
    missing_by_ticker = {t: [] for t in TARGET_COMPANIES}

    for ticker in TARGET_COMPANIES:
        found_years = sorted(found_by_ticker[ticker])
        for y in TARGET_YEARS:
            if y not in found_years:
                missing_by_ticker[ticker].append(y)
                missing_targets.append({
                    "company_id": COMPANY_SPECS[ticker]["company_id"],
                    "canonical_ticker": ticker,
                    "company_name": COMPANY_SPECS[ticker]["name"],
                    "year": y,
                    "document_type": TARGET_DOC_TYPE
                })

    missing_data = {
        "target_years": TARGET_YEARS,
        "target_document_type": TARGET_DOC_TYPE,
        "total_target_count": len(TARGET_COMPANIES) * len(TARGET_YEARS),
        "total_found_count": len(verified_records),
        "total_missing_count": len(missing_targets),
        "missing_targets": missing_targets
    }

    with open(MISSING_JSON, "w", encoding="utf-8") as mf:
        json.dump(missing_data, mf, ensure_ascii=False, indent=2)

    # Print baseline matrix status
    print("\n" + "=" * 70)
    print("ANNUAL REPORT BASELINE BUILDING REPORT")
    print("=" * 70)
    print(f"Total Target PDFs Baseline: {missing_data['total_target_count']} (10 companies x 3 years)")
    print(f"Total Verified Found     : {missing_data['total_found_count']}")
    print(f"Total Missing Targets    : {missing_data['total_missing_count']}")
    print("=" * 70)
    print("\nCOMPANY BREAKDOWN:")
    for ticker in TARGET_COMPANIES:
        fy = sorted(found_by_ticker[ticker])
        my = sorted(missing_by_ticker[ticker])
        print(f"\n  [{ticker}] {COMPANY_SPECS[ticker]['name']}")
        print(f"    - Bulunan Yıllar (Found Years)    : {fy if fy else 'Yok'}")
        print(f"    - Eksik Yıllar (Missing Years)     : {my if my else 'Tamamlandı'}")
        print(f"    - İndirilen/İncelenen Dosyalar     : {downloaded_files[ticker]}")
        print(f"    - Doğrulama Hataları               : {validation_errors[ticker]}")
        print(f"    - Doğrulanmış Rapor Sayısı         : {len(fy)}")

    print("\n" + "=" * 70)
    print(f"Manifest Written : {MANIFEST_JSONL}")
    print(f"Missing Json     : {MISSING_JSON}")
    print("=" * 70 + "\n")

    return missing_data


if __name__ == "__main__":
    build_baseline()
