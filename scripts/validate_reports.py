#!/usr/bin/env python3
"""
scripts/validate_reports.py

Validates company PDF reports against company identity, alias patterns, report year,
and SHA-256 hash uniqueness. Quarantines invalid or mismatched files to data/quarantine/<company_id>/
and records metadata in data/report_manifest.jsonl.
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
MANIFEST_JSONL = PROJECT_ROOT / "data" / "report_manifest.jsonl"


def load_companies_config(config_path: Path = CONFIG_PATH):
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found at {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("companies", [])


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


def infer_document_type(filename: str, text: str) -> str:
    """Infer document type from filename and text."""
    lower_fn = filename.lower()
    lower_text = text.lower()

    if "sustainability" in lower_fn or "surdurulebilirlik" in lower_fn or "sürdürülebilirlik" in lower_text or "tsrs" in lower_text:
        return "sustainability_report"
    elif "presentation" in lower_fn or "sunum" in lower_fn or "yatırımcı sunumu" in lower_text or "investor presentation" in lower_text:
        return "investor_presentation"
    elif "annual" in lower_fn or "faaliyet" in lower_fn or "entegre" in lower_fn or "faaliyet raporu" in lower_text or "annual report" in lower_text:
        return "annual_report"
    return "annual_report"


def infer_year_from_filename_or_text(filename: str, text: str, target_years: list[int] = [2023, 2024, 2025, 2026]) -> int:
    """Extract year from filename or text."""
    # Check filename first
    for y in target_years:
        if str(y) in filename:
            return y

    # Check text
    found_years = re.findall(r"\b(202[0-6])\b", text)
    if found_years:
        # Return most frequent or latest year
        from collections import Counter
        counts = Counter(int(y) for y in found_years)
        return counts.most_common(1)[0][0]

    return 2025


def validate_pdf_content(pdf_path: Path, company_cfg: dict) -> dict:
    """Validates a single PDF against company aliases, year, and signature."""
    company_id = company_cfg["id"]
    company_name = company_cfg["name"]
    aliases = company_cfg.get("aliases", [company_name])
    official_domains = company_cfg.get("official_domains", [])
    expected_years = company_cfg.get("years", [2023, 2024, 2025, 2026])

    with open(pdf_path, "rb") as pf:
        pdf_bytes = pf.read()

    sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()
    file_size = len(pdf_bytes)

    if not pdf_bytes.startswith(b"%PDF"):
        return {
            "status": "quarantined",
            "reason": "Invalid PDF magic header",
            "sha256": sha256_hash,
            "detected_company": None,
            "year": 2025
        }

    if file_size < 10 * 1024:
        return {
            "status": "quarantined",
            "reason": f"File size too small ({file_size} bytes)",
            "sha256": sha256_hash,
            "detected_company": None,
            "year": 2025
        }

    text, page_count = extract_pdf_first_pages_text(pdf_path, max_pages=5)
    lower_text = text.lower()

    # Check for company name or alias
    is_alias_found = False
    matched_alias = None
    for alias in aliases:
        if alias.lower() in lower_text:
            is_alias_found = True
            matched_alias = alias
            break

    # Look for conflicting company names in title/header lines
    detected_other_company = None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:15]:
        line_upper = line.upper()
        if ("A.Ş." in line_upper or "A.O." in line_upper or "KATILIM BANKASI" in line_upper) and not any(a.lower() in line.lower() for a in aliases):
            detected_other_company = line
            break

    if not is_alias_found:
        reason = f"Company mismatch. Expected '{company_name}', detected '{detected_other_company or 'Unknown Company'}'"
        return {
            "status": "quarantined",
            "reason": reason,
            "sha256": sha256_hash,
            "detected_company": detected_other_company,
            "year": infer_year_from_filename_or_text(pdf_path.name, text)
        }

    # Infer year
    detected_year = infer_year_from_filename_or_text(pdf_path.name, text, target_years=expected_years)
    year_present = str(detected_year) in lower_text or str(detected_year) in pdf_path.name

    status = "verified"
    if not year_present and detected_year not in expected_years:
        status = "suspect"

    return {
        "status": status,
        "reason": None if status == "verified" else f"Expected year {detected_year} not confirmed",
        "sha256": sha256_hash,
        "detected_company": company_name,
        "year": detected_year,
        "page_count": page_count,
        "matched_alias": matched_alias
    }


def validate_reports(raw_dir: Path = RAW_DIR, quarantine_dir: Path = QUARANTINE_DIR, config_path: Path = CONFIG_PATH) -> list[dict]:
    """Audits raw PDF files, quarantines invalid ones, returns manifest records."""
    companies = load_companies_config(config_path)
    comp_map = {c["id"]: c for c in companies}
    # Also map ticker folder names (e.g. AKBNK -> akbank)
    ticker_to_id = {
        "AKBNK": "akbank",
        "ARCLK": "arcelik",
        "ASELS": "aselsan",
        "FROTO": "ford_otosan",
        "KCHOL": "koc_holding",
        "MGROS": "migros",
        "SISE": "sisecam",
        "TCELL": "turkcell",
        "THYAO": "thyao",
        "TUPRS": "tupras"
    }

    quarantine_dir.mkdir(parents=True, exist_ok=True)
    pdf_files = sorted(list(raw_dir.glob("*/*.pdf")))

    seen_hashes = {}
    manifest_records = []

    verified_count = 0
    quarantined_count = 0

    print(f"Auditing {len(pdf_files)} PDF files in {raw_dir}...\n")

    for pdf_path in pdf_files:
        folder_name = pdf_path.parent.name
        comp_id = ticker_to_id.get(folder_name, folder_name.lower())
        comp_cfg = comp_map.get(comp_id)

        if not comp_cfg:
            comp_cfg = {
                "id": comp_id,
                "name": folder_name,
                "aliases": [folder_name],
                "official_domains": [],
                "years": [2023, 2024, 2025]
            }

        res = validate_pdf_content(pdf_path, comp_cfg)

        status = res["status"]
        sha256_hash = res["sha256"]
        filename = pdf_path.name

        # Check duplicate hash
        if status in ("verified", "suspect"):
            if sha256_hash in seen_hashes:
                status = "quarantined"
                res["reason"] = f"Duplicate SHA-256 hash matches {seen_hashes[sha256_hash]}"
            else:
                seen_hashes[sha256_hash] = filename

        doc_type = infer_document_type(filename, "")
        source_domain = comp_cfg.get("official_domains", ["unknown"])[0] if comp_cfg.get("official_domains") else "unknown"

        record = {
            "company_id": comp_id,
            "company_name": comp_cfg["name"],
            "document_type": doc_type,
            "year": res["year"],
            "source_url": f"https://www.{source_domain}/reports/{filename}",
            "source_domain": source_domain,
            "file_path": str(pdf_path.relative_to(PROJECT_ROOT)) if status != "quarantined" else f"data/quarantine/{comp_id}/{filename}",
            "sha256": sha256_hash,
            "validation_status": status
        }

        if res.get("reason"):
            record["quarantine_reason"] = res["reason"]

        manifest_records.append(record)

        if status == "quarantined":
            target_q_dir = quarantine_dir / comp_id
            target_q_dir.mkdir(parents=True, exist_ok=True)
            target_q_path = target_q_dir / filename
            shutil.move(pdf_path, target_q_path)
            quarantined_count += 1
            print(f"[QUARANTINED] {folder_name}/{filename} -> Reason: {res['reason']}")
        else:
            verified_count += 1
            print(f"[{status.upper()}] {folder_name}/{filename} -> Company: '{comp_cfg['name']}', Year: {res['year']}")

    # Write manifest.jsonl
    with open(MANIFEST_JSONL, "w", encoding="utf-8") as f:
        for r in manifest_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("\n" + "=" * 60)
    print("VALIDATION REPORT SUMMARY")
    print("=" * 60)
    print(f"Total Files Inspected   : {len(pdf_files)}")
    print(f"Verified / Suspect      : {verified_count}")
    print(f"Quarantined Files       : {quarantined_count}")
    print(f"Manifest File Written   : {MANIFEST_JSONL}")
    print("=" * 60)

    return manifest_records


if __name__ == "__main__":
    validate_reports()
