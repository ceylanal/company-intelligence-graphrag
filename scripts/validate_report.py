#!/usr/bin/env python3
"""
scripts/validate_report.py

Audits PDF company reports in data/raw/, verifies legal company title inside PDF text,
checks official source domain, quarantines mismatched or invalid PDFs to data/quarantine/<ticker>/,
and generates data/report_manifest.jsonl.
"""

import os
import sys
import json
import csv
import shutil
import hashlib
from urllib.parse import urlparse
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
QUARANTINE_DIR = PROJECT_ROOT / "data" / "quarantine"
MANIFEST_JSONL = PROJECT_ROOT / "data" / "report_manifest.jsonl"
CONFIG_PATH = PROJECT_ROOT / "config" / "companies.yaml"

COMPANY_MAP = {
    "AKBNK": {
        "company_id": "akbank",
        "expected_company": "Akbank T.A.Ş.",
        "patterns": ["akbank t.a.ş.", "akbank t.a.s.", "akbank t. a. ş.", "akbank t.a.s", "akbank t. a. s.", "akbank t.a.ş", "akbank"],
        "official_domains": ["akbank.com", "akbankinvestorrelations.com", "kap.org.tr"]
    },
    "ARCLK": {
        "company_id": "arcelik",
        "expected_company": "Arçelik A.Ş.",
        "patterns": ["arçelik a.ş.", "arcelik a.s.", "arçelik a. ş.", "arçelik", "arcelik", "beko"],
        "official_domains": ["arcelikglobal.com", "arcelik.com.tr", "kap.org.tr"]
    },
    "ASELS": {
        "company_id": "aselsan",
        "expected_company": "Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
        "patterns": ["aselsan elektronik sanayi ve ticaret a.ş.", "aselsan elektronik sanayi", "aselsan a.ş.", "aselsan"],
        "official_domains": ["aselsan.com.tr", "aselsan.com", "kap.org.tr"]
    },
    "FROTO": {
        "company_id": "ford_otosan",
        "expected_company": "Ford Otomotiv Sanayi A.Ş.",
        "patterns": ["ford otomotiv sanayi a.ş.", "ford otomotiv sanayi", "ford otosan a.ş.", "ford otosan"],
        "official_domains": ["fordotosan.com.tr", "kap.org.tr"]
    },
    "KCHOL": {
        "company_id": "koc_holding",
        "expected_company": "Koç Holding A.Ş.",
        "patterns": ["koç holding a.ş.", "koc holding a.s.", "koç holding a. ş.", "koç holding", "koc holding"],
        "official_domains": ["koc.com.tr", "kap.org.tr"]
    },
    "MGROS": {
        "company_id": "migros",
        "expected_company": "Migros Ticaret A.Ş.",
        "patterns": ["migros ticaret a.ş.", "migros ticaret a.s.", "migros ticaret a. ş.", "migros"],
        "official_domains": ["migroskurumsal.com", "migros.com.tr", "migroskurumsalstr.blob.core.windows.net", "kap.org.tr"]
    },
    "SISE": {
        "company_id": "sisecam",
        "expected_company": "Türkiye Şişe ve Cam Fabrikaları A.Ş.",
        "patterns": ["türkiye şişe ve cam fabrikaları a.ş.", "türkiye şişe ve cam fabrikaları", "şişecam", "sisecam"],
        "official_domains": ["sisecam.com.tr", "sisecam.com", "kap.org.tr"]
    },
    "TCELL": {
        "company_id": "turkcell",
        "expected_company": "Turkcell İletişim Hizmetleri A.Ş.",
        "patterns": ["turkcell iletişim hizmetleri a.ş.", "turkcell iletişim hizmetleri", "turkcell a.ş.", "turkcell"],
        "official_domains": ["turkcell.com.tr", "turkcell.com", "kap.org.tr"]
    },
    "THYAO": {
        "company_id": "thyao",
        "expected_company": "Türk Hava Yolları A.O.",
        "patterns": ["türk hava yolları a.o.", "türk hava yolları anonim ortaklığı", "türk hava yolları", "turkish airlines"],
        "official_domains": ["turkishairlines.com", "kap.org.tr"]
    },
    "TUPRS": {
        "company_id": "tupras",
        "expected_company": "Türkiye Petrol Rafinerileri A.Ş.",
        "patterns": ["türkiye petrol rafinerileri a.ş.", "türkiye petrol rafinerileri", "tüpraş", "tupras"],
        "official_domains": ["tupras.com.tr", "tupras.com", "kap.org.tr"]
    }
}


def extract_pdf_info(file_path: Path, max_pages: int = 10):
    """Extract text from the first max_pages of a PDF."""
    if fitz is None:
        return "", 0

    text_content = ""
    page_count = 0
    try:
        doc = fitz.open(file_path)
        page_count = len(doc)
        for i in range(min(max_pages, page_count)):
            text_content += doc[i].get_text("text") + "\n"
        doc.close()
    except Exception as e:
        print(f"Error reading PDF {file_path}: {e}")
    return text_content, page_count


def detect_company_in_text(text: str, ticker: str):
    """Detect if expected company or another company name is present in PDF text."""
    lower_text = text.lower()
    ticker_info = COMPANY_MAP.get(ticker, {})
    patterns = ticker_info.get("patterns", [])

    for pat in patterns:
        if pat in lower_text:
            return ticker_info.get("expected_company"), True

    # Check if a different known company or institution is detected
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:20]:
        if "A.Ş." in line or "A.O." in line or "LTD." in line or "INC." in line:
            return line, False

    return None, False


def get_source_url_map():
    """Build map of (ticker, doc_type) -> source_url from companies.yaml if available."""
    url_map = {}
    if CONFIG_PATH.exists():
        try:
            import yaml
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            for c in cfg.get("companies", []):
                t = c["ticker"]
                for d in c.get("documents", []):
                    dt = d["document_type"]
                    url_map[(t, dt)] = d.get("source_url", "")
        except Exception:
            pass
    return url_map


def validate_all_reports(raw_dir: Path = RAW_DIR, quarantine_dir: Path = QUARANTINE_DIR):
    """Audits PDFs in raw_dir, quarantines invalid ones, returns manifest items."""
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    source_url_map = get_source_url_map()

    manifest_records = []
    seen_hashes = {}

    pdf_files = sorted(list(raw_dir.glob("*/*.pdf")))
    print(f"Auditing {len(pdf_files)} PDF files in {raw_dir}...\n")

    verified_count = 0
    quarantined_count = 0
    duplicate_count = 0

    for pdf_path in pdf_files:
        ticker = pdf_path.parent.name
        filename = pdf_path.name

        # Parse filename standard: {ticker}__{document_type}__{period}__{language}__v1.pdf
        parts = filename.split("__")
        doc_type = parts[1] if len(parts) > 1 else "unknown"
        period = parts[2] if len(parts) > 2 else "2025"
        try:
            report_year = int(period.split("_")[0])
        except ValueError:
            report_year = 2025

        comp_info = COMPANY_MAP.get(ticker, {
            "company_id": ticker.lower(),
            "expected_company": ticker,
            "patterns": [ticker.lower()],
            "official_domains": []
        })

        with open(pdf_path, "rb") as pf:
            pdf_bytes = pf.read()

        sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()
        file_size = len(pdf_bytes)

        source_url = source_url_map.get((ticker, doc_type), f"https://www.kap.org.tr/tr/{ticker}")
        parsed_url = urlparse(source_url)
        source_domain = parsed_url.netloc

        official_domains = comp_info.get("official_domains", [])
        is_official_domain = any(dom in source_domain for dom in official_domains)

        text_content, page_count = extract_pdf_info(pdf_path)

        detected_comp, is_match = detect_company_in_text(text_content, ticker)

        validation_status = "verified"
        quarantine_reason = None
        evidence = []

        # Audit checks
        if not pdf_bytes.startswith(b"%PDF"):
            validation_status = "quarantined"
            quarantine_reason = "Invalid PDF magic header"
        elif file_size < 10 * 1024:
            validation_status = "quarantined"
            quarantine_reason = f"File size too small ({file_size} bytes)"
        elif not is_match:
            validation_status = "quarantined"
            quarantine_reason = f"Company mismatch. Expected '{comp_info['expected_company']}', detected '{detected_comp}'"
        else:
            evidence.append("PDF text content company match")
            if is_official_domain:
                evidence.append(f"Official domain match ({source_domain})")

        # Duplicate check
        if validation_status == "verified":
            if sha256_hash in seen_hashes:
                validation_status = "quarantined"
                orig_file = seen_hashes[sha256_hash]
                quarantine_reason = f"Duplicate SHA-256 hash matches {orig_file}"
                duplicate_count += 1
            else:
                seen_hashes[sha256_hash] = filename

        record = {
            "company_id": comp_info["company_id"],
            "expected_company": comp_info["expected_company"],
            "detected_company": detected_comp or comp_info["expected_company"] if is_match else detected_comp,
            "document_type": doc_type,
            "report_year": report_year,
            "source_url": source_url,
            "source_domain": source_domain,
            "official_source": is_official_domain,
            "validation_status": validation_status,
            "validation_evidence": evidence,
            "sha256": sha256_hash
        }

        if quarantine_reason:
            record["quarantine_reason"] = quarantine_reason

        manifest_records.append(record)

        if validation_status == "quarantined":
            target_q_dir = quarantine_dir / ticker
            target_q_dir.mkdir(parents=True, exist_ok=True)
            target_q_path = target_q_dir / filename
            shutil.move(pdf_path, target_q_path)
            quarantined_count += 1
            print(f"[QUARANTINED] {ticker}/{filename} -> Reason: {quarantine_reason}")
        else:
            verified_count += 1
            print(f"[VERIFIED] {ticker}/{filename} -> Company: '{comp_info['expected_company']}', Pages: {page_count}")

    # Write manifest.jsonl
    with open(MANIFEST_JSONL, "w", encoding="utf-8") as f:
        for r in manifest_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("\n" + "=" * 60)
    print("AUDIT SUMMARY REPORT")
    print("=" * 60)
    print(f"Total Inspected Files   : {len(pdf_files)}")
    print(f"Verified Files          : {verified_count}")
    print(f"Quarantined Files       : {quarantined_count}")
    print(f"Duplicates Quarantined  : {duplicate_count}")
    print(f"Manifest File Written   : {MANIFEST_JSONL}")
    print("=" * 60)

    return manifest_records


if __name__ == "__main__":
    validate_all_reports()
