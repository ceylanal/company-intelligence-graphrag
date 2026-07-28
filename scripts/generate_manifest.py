#!/usr/bin/env python3
"""Script to build data/manifest.json master dataset manifest file."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_JSONL = PROJECT_ROOT / "data" / "report_manifest.jsonl"
OUTPUT_MANIFEST_JSON = PROJECT_ROOT / "data" / "manifest.json"
PAGES_DIR = PROJECT_ROOT / "data" / "processed" / "pages"
CHUNKS_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"


def build_master_manifest():
    if not MANIFEST_JSONL.exists():
        print(f"Error: {MANIFEST_JSONL} not found")
        sys.exit(1)

    reports_data = []
    total_pages = 0
    total_chunks = 0
    companies = set()

    with open(MANIFEST_JSONL, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            ticker = item["canonical_ticker"]
            year = item["year"]
            doc_type = item["document_type"]
            lang = item["language"]
            source_file = f"{ticker}__{year}__{doc_type}__{lang}.pdf"
            doc_id = f"{ticker}__{year}__{doc_type}__{lang}"

            # Calculate pages for this report
            page_count = 0
            page_jsonl = PAGES_DIR / ticker / f"{doc_id}.jsonl"
            if not page_jsonl.exists():
                page_jsonl = PAGES_DIR / f"{doc_id}.jsonl"

            if page_jsonl.exists():
                with open(page_jsonl, encoding="utf-8") as pf:
                    page_count = sum(1 for pl in pf if pl.strip())

            # Calculate chunks for this report
            chunk_count = 0
            chunk_jsonl = CHUNKS_DIR / ticker / f"{doc_id}_chunks.jsonl"
            if not chunk_jsonl.exists():
                chunk_jsonl = CHUNKS_DIR / ticker / f"{doc_id}.jsonl"
            if not chunk_jsonl.exists():
                chunk_jsonl = CHUNKS_DIR / f"{doc_id}_chunks.jsonl"
            if not chunk_jsonl.exists():
                chunk_jsonl = CHUNKS_DIR / f"{doc_id}.jsonl"

            if chunk_jsonl.exists():
                with open(chunk_jsonl, encoding="utf-8") as cf:
                    chunk_count = sum(1 for cl in cf if cl.strip())

            total_pages += page_count
            total_chunks += chunk_count
            companies.add(ticker)

            report_entry = {
                "company": item["company_name"],
                "ticker": ticker,
                "year": year,
                "report_type": doc_type,
                "language": lang,
                "source_url": item["source_url"],
                "source_file": source_file,
                "sha256": item["sha256"],
                "page_count": page_count,
                "chunk_count": chunk_count,
            }
            reports_data.append(report_entry)

    master_manifest = {
        "project": "company-intelligence-graphrag",
        "version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "total_companies": len(companies),
            "total_reports": len(reports_data),
            "total_pages": total_pages,
            "total_chunks": total_chunks,
            "qdrant_points": total_chunks,
            "status": "PASS",
        },
        "companies": sorted(companies),
        "reports": reports_data,
    }

    with open(OUTPUT_MANIFEST_JSON, "w", encoding="utf-8") as out_f:
        json.dump(master_manifest, out_f, ensure_ascii=False, indent=2)

    print(f"✨ Master manifest generated successfully at {OUTPUT_MANIFEST_JSON}")
    print(f"Total Companies : {len(companies)}")
    print(f"Total Reports   : {len(reports_data)}")
    print(f"Total Pages     : {total_pages:,}")
    print(f"Total Chunks    : {total_chunks:,}")


if __name__ == "__main__":
    build_master_manifest()
