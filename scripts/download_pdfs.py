#!/usr/bin/env python3
"""
scripts/download_pdfs.py

Reads config/companies.yaml, downloads specified target PDF documents from official IR / KAP sources,
saves them under data/raw/<ticker>/ using standard file naming:
{ticker}__{document_type}__{period}__{language}__v1.pdf

Features:
- Smart local caching (skips redownloading existing valid PDFs).
- Handles HTTP 429 rate limiting with retry backoff.
- Updates data/manifest.csv with metadata, file size, page count, SHA-256 hash, and status.
"""

import csv
import hashlib
import sys
import time
from pathlib import Path

import requests
import yaml

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import pypdf
except ImportError:
    pypdf = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "companies.yaml"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifest.csv"
MIN_FILE_SIZE = 10 * 1024  # 10 KB

MANIFEST_FIELDNAMES = [
    "ticker",
    "company",
    "sector",
    "document_type",
    "period",
    "language",
    "source_url",
    "local_path",
    "sha256",
    "page_count",
    "file_size",
    "download_status",
]

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/pdf,application/octet-stream,*/*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def get_page_count(pdf_bytes: bytes) -> int:
    """Extract page count from raw PDF bytes using PyMuPDF or pypdf."""
    if fitz is not None:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            count = len(doc)
            doc.close()
            return count
        except Exception:
            pass

    if pypdf is not None:
        try:
            import io

            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            return len(reader.pages)
        except Exception:
            pass

    return 0


def fetch_pdf_with_retry(session: requests.Session, url: str, max_retries: int = 3, backoff: float = 1.5):
    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(url, timeout=15, allow_redirects=True)
            if response.status_code == 200 and response.content.startswith(b"%PDF"):
                return response
            elif response.status_code == 429:
                wait_time = backoff * attempt
                print(f"  [429 Rate Limit] Retrying in {wait_time:.1f}s (Attempt {attempt}/{max_retries})...")
                time.sleep(wait_time)
            else:
                if attempt < max_retries:
                    time.sleep(1.0)
                else:
                    return response
        except Exception as e:
            if attempt < max_retries:
                time.sleep(1.0)
            else:
                raise e
    return None


def download_documents():
    if not CONFIG_PATH.exists():
        print(f"Error: Config file not found at {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    companies = config.get("companies", [])
    if not companies:
        print("No companies found in config.")
        sys.exit(1)

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    manifest_records = []
    downloaded_count = 0
    cached_count = 0
    failed_count = 0

    session = requests.Session()
    session.headers.update(HTTP_HEADERS)

    for item in companies:
        ticker = item["ticker"]
        company = item["company"]
        sector = item["sector"]
        documents = item.get("documents", [])

        ticker_dir = RAW_DATA_DIR / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)

        for doc in documents:
            doc_type = doc["document_type"]
            period = doc["period"]
            language = doc.get("language", "tr")
            source_url = doc["source_url"]

            filename = f"{ticker}__{doc_type}__{period}__{language}__v1.pdf"
            local_file_path = ticker_dir / filename
            relative_local_path = f"data/raw/{ticker}/{filename}"

            status = "failed"
            sha256_hash = ""
            page_count = 0
            file_size = 0

            # Check if valid file already exists locally
            if local_file_path.exists() and local_file_path.stat().st_size >= MIN_FILE_SIZE:
                with open(local_file_path, "rb") as pf:
                    pdf_data = pf.read()

                if pdf_data.startswith(b"%PDF"):
                    file_size = len(pdf_data)
                    sha256_hash = hashlib.sha256(pdf_data).hexdigest()
                    page_count = get_page_count(pdf_data)
                    status = "success"
                    cached_count += 1
                    print(
                        f"[CACHE OK] [{ticker}] {doc_type} ({period}) -> {relative_local_path} ({file_size} bytes, {page_count} pages)"
                    )

            if status != "success":
                print(f"Downloading [{ticker}] {doc_type} ({period}) from {source_url} ...")
                try:
                    response = fetch_pdf_with_retry(session, source_url)
                    if response and response.status_code == 200 and response.content.startswith(b"%PDF"):
                        pdf_data = response.content
                        file_size = len(pdf_data)

                        with open(local_file_path, "wb") as pf:
                            pf.write(pdf_data)

                        sha256_hash = hashlib.sha256(pdf_data).hexdigest()
                        page_count = get_page_count(pdf_data)
                        status = "success"
                        downloaded_count += 1
                        print(f"  -> Saved: {relative_local_path} ({file_size} bytes, {page_count} pages)")
                    else:
                        status_code = response.status_code if response else "No response"
                        print(f"  -> Download failed (HTTP status {status_code})")
                        failed_count += 1
                except Exception as e:
                    print(f"  -> Error downloading {source_url}: {e}")
                    failed_count += 1
                time.sleep(1.0)

            record = {
                "ticker": ticker,
                "company": company,
                "sector": sector,
                "document_type": doc_type,
                "period": period,
                "language": language,
                "source_url": source_url,
                "local_path": relative_local_path,
                "sha256": sha256_hash,
                "page_count": page_count,
                "file_size": file_size,
                "download_status": status,
            }
            manifest_records.append(record)

    with open(MANIFEST_PATH, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=MANIFEST_FIELDNAMES)
        writer.writeheader()
        writer.writerows(manifest_records)

    print(f"\nDownload completed. Manifest written to {MANIFEST_PATH}")
    print(
        f"Summary: {cached_count} cached, {downloaded_count} newly downloaded, {failed_count} failed, total {len(manifest_records)} documents."
    )


if __name__ == "__main__":
    download_documents()
