#!/usr/bin/env python3
"""
scripts/validate_pdfs.py

Validates downloaded PDF files in data/raw/ referenced in data/manifest.csv.
Checks:
1. PDF Magic Header signature (%PDF-)
2. File size threshold (> 10 KB)
3. Page count validity (> 0 pages)
4. Duplicate SHA-256 detection across the dataset

Prints summary report for downloaded, failed, and duplicate documents.
"""

import csv
import hashlib
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifest.csv"
MIN_FILE_SIZE = 10 * 1024  # 10 KB threshold


def validate():
    if not MANIFEST_PATH.exists():
        print(f"Error: Manifest file not found at {MANIFEST_PATH}")
        sys.exit(1)

    records = []
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    total_records = len(records)
    valid_count = 0
    failed_count = 0

    hashes = {}
    duplicates = []
    issues = []

    print(f"Validating {total_records} documents from manifest...\n")

    for rec in records:
        ticker = rec["ticker"]
        doc_type = rec["document_type"]
        local_rel_path = rec["local_path"]
        expected_status = rec.get("download_status", "")
        file_path = PROJECT_ROOT / local_rel_path

        doc_id = f"{ticker}__{doc_type}"

        if expected_status != "success":
            issues.append(f"[{doc_id}] Download status is '{expected_status}' in manifest.")
            failed_count += 1
            continue

        if not file_path.exists():
            issues.append(f"[{doc_id}] Local file does not exist at {file_path}")
            failed_count += 1
            continue

        with open(file_path, "rb") as pf:
            content = pf.read()

        file_size = len(content)

        # 1. Magic Header Check
        if not content.startswith(b"%PDF"):
            issues.append(f"[{doc_id}] Invalid magic bytes header (does not start with %PDF-).")
            failed_count += 1
            continue

        # 2. File Size Check
        if file_size < MIN_FILE_SIZE:
            issues.append(f"[{doc_id}] File size too small ({file_size} bytes < {MIN_FILE_SIZE} bytes threshold).")
            failed_count += 1
            continue

        # 3. Page Count Check
        page_count = 0
        if fitz is not None:
            try:
                pdf_doc = fitz.open(stream=content, filetype="pdf")
                page_count = len(pdf_doc)
                pdf_doc.close()
            except Exception as e:
                issues.append(f"[{doc_id}] PyMuPDF parse error: {e}")
                failed_count += 1
                continue
        else:
            page_count = int(rec.get("page_count", 0))

        if page_count <= 0:
            issues.append(f"[{doc_id}] Invalid page count ({page_count}).")
            failed_count += 1
            continue

        # 4. SHA-256 Hash Duplicate Check
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash in hashes:
            existing_doc = hashes[actual_hash]
            duplicates.append((doc_id, existing_doc, actual_hash))
            issues.append(f"[{doc_id}] DUPLICATE SHA-256 matches {existing_doc} (hash: {actual_hash[:12]}...)")
        else:
            hashes[actual_hash] = doc_id

        valid_count += 1
        print(f"[OK] {doc_id} -> Size: {file_size:,} bytes | Pages: {page_count} | SHA256: {actual_hash[:12]}...")

    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Total Target Documents : {total_records}")
    print(f"Successfully Validated : {valid_count}")
    print(f"Failed / Invalid       : {failed_count}")
    print(f"Duplicates Detected    : {len(duplicates)}")
    print("=" * 60)

    if duplicates:
        print("\nDuplicate Documents Breakdown:")
        for dup, orig, h in duplicates:
            print(f"  - {dup} is identical to {orig} (hash: {h})")

    if issues:
        print("\nValidation Issues / Warnings:")
        for iss in issues:
            print(f"  - {iss}")

    if failed_count > 0 or len(duplicates) > 0:
        print("\nResult: VALIDATION FAILED with errors or duplicates.")
        sys.exit(1)
    else:
        print("\nResult: ALL DOCUMENTS VALIDATED SUCCESSFULLY WITH ZERO DUPLICATES.")
        sys.exit(0)


if __name__ == "__main__":
    validate()
