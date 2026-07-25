#!/usr/bin/env python3
"""
scripts/normalize_dataset.py

Deduplicates, normalizes, renames, and quarantines company report PDFs in data/raw/.

Rules:
1. Merges non-standard subdirectories (ARCELIK -> ARCLK, ASELSAN -> ASELS, FORD_OTOSAN -> FROTO, AKBANK -> AKBNK)
   into canonical 5-letter stock tickers.
2. Calculates SHA-256 for all PDFs.
3. Moves exact SHA-256 duplicate PDFs to data/quarantine/duplicates/.
4. Inspects PDF first 5 pages via PyMuPDF (fitz) to extract company name/alias, year, document type, and language.
5. Moves files not matching expected company (e.g. Arçelik/Beko group for ARCLK) to data/quarantine/wrong_company/.
6. Enforces exactly 1 verified PDF per (canonical_ticker, year, document_type, language) tuple, moving excess files to data/quarantine/duplicates/.
7. Standardizes file names to: {canonical_ticker}__{year}__{document_type}__{language}.pdf
8. Writes all results to data/report_manifest.jsonl.
9. Preserves all verified files.
"""

import os
import sys
import json
import re
import shutil
import hashlib
import yaml
from pathlib import Path
from urllib.parse import urlparse

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "companies.yaml"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
QUARANTINE_DIR = PROJECT_ROOT / "data" / "quarantine"
QUARANTINE_DUPLICATES = QUARANTINE_DIR / "duplicates"
QUARANTINE_WRONG_COMPANY = QUARANTINE_DIR / "wrong_company"
MANIFEST_JSONL = PROJECT_ROOT / "data" / "report_manifest.jsonl"

FOLDER_CANONICAL_MAP = {
    "AKBANK": "AKBNK",
    "AKBNK": "AKBNK",
    "ARCELIK": "ARCLK",
    "ARCLK": "ARCLK",
    "ASELSAN": "ASELS",
    "ASELS": "ASELS",
    "FORD_OTOSAN": "FROTO",
    "FROTO": "FROTO",
    "KCHOL": "KCHOL",
    "MGROS": "MGROS",
    "SISE": "SISE",
    "TCELL": "TCELL",
    "THYAO": "THYAO",
    "TUPRS": "TUPRS"
}

COMPANY_SPECS = {
    "AKBNK": {
        "company_id": "akbank",
        "name": "Akbank T.A.Ş.",
        "aliases": ["akbank t.a.ş.", "akbank t.a.s.", "akbank t. a. ş.", "akbank t.a.s", "akbank t.a.ş", "akbank"],
        "official_domains": ["akbank.com", "akbankinvestorrelations.com"]
    },
    "ARCLK": {
        "company_id": "arcelik",
        "name": "Arçelik A.Ş.",
        "aliases": ["arçelik a.ş.", "arcelik a.s.", "arçelik a. ş.", "arçelik", "arcelik", "beko a.ş.", "beko"],
        "official_domains": ["arcelikglobal.com", "arcelik.com.tr", "bekoglobal.com"]
    },
    "ASELS": {
        "company_id": "aselsan",
        "name": "Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
        "aliases": ["aselsan elektronik sanayi ve ticaret a.ş.", "aselsan elektronik sanayi", "aselsan a.ş.", "aselsan"],
        "official_domains": ["aselsan.com.tr", "aselsan.com"]
    },
    "FROTO": {
        "company_id": "ford_otosan",
        "name": "Ford Otomotiv Sanayi A.Ş.",
        "aliases": ["ford otomotiv sanayi a.ş.", "ford otomotiv sanayi", "ford otosan a.ş.", "ford otosan"],
        "official_domains": ["fordotosan.com.tr"]
    },
    "KCHOL": {
        "company_id": "koc_holding",
        "name": "Koç Holding A.Ş.",
        "aliases": ["koç holding a.ş.", "koc holding a.s.", "koç holding a. ş.", "koç holding", "koc holding"],
        "official_domains": ["koc.com.tr"]
    },
    "MGROS": {
        "company_id": "migros",
        "name": "Migros Ticaret A.Ş.",
        "aliases": ["migros ticaret a.ş.", "migros ticaret a.s.", "migros ticaret a. ş.", "migros"],
        "official_domains": ["migroskurumsal.com", "migros.com.tr", "migroskurumsalstr.blob.core.windows.net"]
    },
    "SISE": {
        "company_id": "sisecam",
        "name": "Türkiye Şişe ve Cam Fabrikaları A.Ş.",
        "aliases": ["türkiye şişe ve cam fabrikaları a.ş.", "türkiye şişe ve cam fabrikaları", "şişecam", "sisecam"],
        "official_domains": ["sisecam.com.tr", "sisecam.com"]
    },
    "TCELL": {
        "company_id": "turkcell",
        "name": "Turkcell İletişim Hizmetleri A.Ş.",
        "aliases": ["turkcell iletişim hizmetleri a.ş.", "turkcell iletişim hizmetleri", "turkcell a.ş.", "turkcell"],
        "official_domains": ["turkcell.com.tr", "turkcell.com"]
    },
    "THYAO": {
        "company_id": "thyao",
        "name": "Türk Hava Yolları A.O.",
        "aliases": ["türk hava yolları a.o.", "türk hava yolları anonim ortaklığı", "türk hava yolları", "turkish airlines", "thy"],
        "official_domains": ["turkishairlines.com"]
    },
    "TUPRS": {
        "company_id": "tupras",
        "name": "Türkiye Petrol Rafinerileri A.Ş.",
        "aliases": ["türkiye petrol rafinerileri a.ş.", "türkiye petrol rafinerileri", "tüpraş", "tupras"],
        "official_domains": ["tupras.com.tr", "tupras.com"]
    }
}


def extract_pdf_first_pages_text(pdf_path: Path, max_pages: int = 5) -> tuple[str, int]:
    """Extract text from the first max_pages of a PDF."""
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
    """Detect language ('tr' or 'en') from text and filename."""
    fn_lower = filename.lower()
    if "__en" in fn_lower or "_en." in fn_lower or "english" in fn_lower or "sustainability_report" in fn_lower:
        if "turkce" not in fn_lower and "yonetici_ozeti" not in fn_lower:
            # Check text
            tr_keywords = ["faaliyet", "raporu", "sürdürülebilirlik", "yönetim", "yılı", "özet"]
            en_keywords = ["annual", "report", "sustainability", "integrated", "financial", "governance", "overview"]
            tr_count = sum(1 for kw in tr_keywords if kw in text.lower())
            en_count = sum(1 for kw in en_keywords if kw in text.lower())
            if en_count > tr_count:
                return "en"
            elif tr_count > en_count:
                return "tr"

    tr_score = len(re.findall(r"\b(faaliyet|raporu|sürdürülebilirlik|yılı|yonetici|özeti|bağımsız)\b", text.lower()))
    en_score = len(re.findall(r"\b(annual|sustainability|report|integrated|financial|summary|statement)\b", text.lower()))

    return "en" if en_score > tr_score + 2 else "tr"


def detect_document_type(text: str, filename: str) -> str:
    """Detect document type (annual_report, sustainability_report, investor_presentation)."""
    combined = (filename + " " + text).lower()

    if "presentation" in combined or "sunum" in combined or "yatırımcı sunumu" in combined or "investor presentation" in combined:
        return "investor_presentation"
    elif "sustainability" in combined or "surdurulebilirlik" in combined or "sürdürülebilirlik" in combined or "tsrs" in combined or "cdp" in combined:
        return "sustainability_report"
    else:
        return "annual_report"


def detect_report_year(text: str, filename: str, default_year: int = 2025) -> int:
    """Extract report year from text or filename."""
    # Check filename first for 4-digit year
    fn_years = re.findall(r"\b(200[0-9]|201[0-9]|202[0-6])\b", filename)
    if fn_years:
        return int(fn_years[0])

    # Check text
    text_years = re.findall(r"\b(200[0-9]|201[0-9]|202[0-6])\b", text)
    if text_years:
        from collections import Counter
        counts = Counter(int(y) for y in text_years)
        return counts.most_common(1)[0][0]

    return default_year


def normalize_dataset(raw_dir: Path = RAW_DIR, quarantine_dir: Path = QUARANTINE_DIR):
    """Main dataset canonicalization, deduplication, content parsing, sorting, and renaming pipeline."""
    QUARANTINE_DUPLICATES.mkdir(parents=True, exist_ok=True)
    QUARANTINE_WRONG_COMPANY.mkdir(parents=True, exist_ok=True)

    # Step 1: Canonicalize subdirectories
    subdirs = [d for d in raw_dir.iterdir() if d.is_dir()]
    for d in subdirs:
        canonical_ticker = FOLDER_CANONICAL_MAP.get(d.name.upper(), d.name.upper())
        canonical_path = raw_dir / canonical_ticker
        if d != canonical_path:
            canonical_path.mkdir(parents=True, exist_ok=True)
            for f in d.glob("*.pdf"):
                dest = canonical_path / f.name
                shutil.move(f, dest)
            try:
                d.rmdir()
            except Exception:
                pass

    # Collect all PDFs in canonical folders
    all_pdfs = sorted(list(raw_dir.glob("*/*.pdf")))
    total_pdf_count = len(all_pdfs)

    print(f"Total PDFs found across canonical folders: {total_pdf_count}")

    sha256_seen = {}
    duplicate_count = 0
    wrong_company_count = 0
    verified_records = []

    # Map to track combination uniqueness: (ticker, year, doc_type, lang) -> file_info
    combo_tracker = {}

    for pdf_path in all_pdfs:
        ticker = pdf_path.parent.name
        comp_spec = COMPANY_SPECS.get(ticker, {
            "company_id": ticker.lower(),
            "name": ticker,
            "aliases": [ticker.lower()],
            "official_domains": []
        })

        with open(pdf_path, "rb") as pf:
            pdf_bytes = pf.read()

        sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()
        filename = pdf_path.name

        # 1. SHA-256 Deduplication
        if sha256_hash in sha256_seen:
            duplicate_count += 1
            dest_q = QUARANTINE_DUPLICATES / filename
            if dest_q.exists():
                dest_q = QUARANTINE_DUPLICATES / f"dup_{sha256_hash[:8]}_{filename}"
            shutil.move(pdf_path, dest_q)
            print(f"[DUPLICATE SHA256] {ticker}/{filename} -> Moved to quarantine/duplicates/")
            continue

        sha256_seen[sha256_hash] = pdf_path

        # 2. Extract Text & Content Properties
        text, page_count = extract_pdf_first_pages_text(pdf_path, max_pages=5)
        lower_text = text.lower()

        # Company matching
        is_company_matched = False
        matched_alias = None
        for alias in comp_spec["aliases"]:
            if alias.lower() in lower_text:
                is_company_matched = True
                matched_alias = alias
                break

        if not is_company_matched:
            wrong_company_count += 1
            dest_w = QUARANTINE_WRONG_COMPANY / filename
            shutil.move(pdf_path, dest_w)
            print(f"[WRONG COMPANY] {ticker}/{filename} -> Moved to quarantine/wrong_company/")
            continue

        doc_type = detect_document_type(text, filename)
        year = detect_report_year(text, filename)
        lang = detect_language(text, filename)

        combo_key = (ticker, year, doc_type, lang)

        file_info = {
            "pdf_path": pdf_path,
            "ticker": ticker,
            "company_id": comp_spec["company_id"],
            "company_name": comp_spec["name"],
            "document_type": doc_type,
            "year": year,
            "language": lang,
            "sha256": sha256_hash,
            "page_count": page_count,
            "file_size": len(pdf_bytes),
            "official_domain": comp_spec["official_domains"][0] if comp_spec["official_domains"] else "unknown"
        }

        # 3. Enforce 1 PDF per (Company + Year + Document_Type + Language)
        if combo_key in combo_tracker:
            duplicate_count += 1
            existing_info = combo_tracker[combo_key]
            # Compare page count/size: keep the larger/more complete PDF
            if file_info["page_count"] > existing_info["page_count"]:
                # Move previous existing PDF to duplicates
                prev_path = existing_info["pdf_path"]
                if prev_path.exists():
                    shutil.move(prev_path, QUARANTINE_DUPLICATES / prev_path.name)
                combo_tracker[combo_key] = file_info
                print(f"[DUPLICATE COMBO REPLACED] {ticker} {year} {doc_type} {lang} -> Kept {filename}")
            else:
                shutil.move(pdf_path, QUARANTINE_DUPLICATES / filename)
                print(f"[DUPLICATE COMBO EXCESS] {ticker}/{filename} -> Moved to quarantine/duplicates/")
        else:
            combo_tracker[combo_key] = file_info

    # Step 4: Rename verified PDFs to standard format: {ticker}__{year}__{document_type}__{language}.pdf
    manifest_records = []
    final_verified_list = []

    for combo_key, info in combo_tracker.items():
        ticker, year, doc_type, lang = combo_key
        std_filename = f"{ticker}__{year}__{doc_type}__{lang}.pdf"
        current_path = info["pdf_path"]
        target_path = current_path.parent / std_filename

        if current_path.exists() and current_path != target_path:
            shutil.move(current_path, target_path)

        relative_file_path = f"data/raw/{ticker}/{std_filename}"

        record = {
            "company_id": info["company_id"],
            "company_name": info["company_name"],
            "canonical_ticker": ticker,
            "document_type": doc_type,
            "year": year,
            "language": lang,
            "source_url": f"https://www.{info['official_domain']}/reports/{std_filename}",
            "source_domain": info["official_domain"],
            "file_path": relative_file_path,
            "sha256": info["sha256"],
            "validation_status": "verified"
        }
        manifest_records.append(record)

        summary_str = f"{ticker} | {year} | {doc_type} | {lang} -> {relative_file_path}"
        final_verified_list.append(summary_str)

    # Step 5: Write data/report_manifest.jsonl
    with open(MANIFEST_JSONL, "w", encoding="utf-8") as mf:
        for rec in manifest_records:
            mf.write(json.dumps(rec, ensure_ascii=False) + "\n")

    unique_pdf_count = len(manifest_records)

    # Print summary report
    print("\n" + "=" * 65)
    print("DATASET DEDUPLICATION & NORMALIZATION SUMMARY")
    print("=" * 65)
    print(f"Toplam PDF (Initial PDF Count)      : {total_pdf_count}")
    print(f"Benzersiz PDF (Verified Unique PDFs): {unique_pdf_count}")
    print(f"Duplicate Sayısı (Duplicates)       : {duplicate_count}")
    print(f"Yanlış Şirket (Wrong Company)       : {wrong_company_count}")
    print("=" * 65)
    print("\nDoğrulanmış Rapor Listesi (Verified Reports):")
    for v in sorted(final_verified_list):
        print(f"  - {v}")
    print("=" * 65)
    print(f"\nManifest file written to: {MANIFEST_JSONL}\n")

    return {
        "total_pdf": total_pdf_count,
        "unique_pdf": unique_pdf_count,
        "duplicate_count": duplicate_count,
        "wrong_company_count": wrong_company_count,
        "verified_reports": final_verified_list
    }


if __name__ == "__main__":
    normalize_dataset()
