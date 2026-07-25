#!/usr/bin/env python3
"""
scripts/crawl_reports.py

Automated report crawler for company-intelligence-graphrag.
Crawls official company domains up to depth 2, discovers PDF report links,
downloads them, validates company identity and report year, and updates data/report_manifest.jsonl.

Usage:
  python scripts/crawl_reports.py --company akbank
  python scripts/crawl_reports.py --all
"""

import os
import sys
import json
import time
import shutil
import argparse
import urllib.robotparser

from urllib.parse import urlparse, urljoin, unquote
from pathlib import Path
import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "companies.yaml"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
QUARANTINE_DIR = PROJECT_ROOT / "data" / "quarantine"
MANIFEST_JSONL = PROJECT_ROOT / "data" / "report_manifest.jsonl"

sys.path.insert(0, str(PROJECT_ROOT))
from scripts.validate_reports import validate_pdf_content, load_companies_config, infer_document_type

REPORT_KEYWORDS = [
    "faaliyet raporu",
    "faaliyet-raporu",
    "annual report",
    "annual-report",
    "sustainability report",
    "surdurulebilirlik",
    "sürdürülebilirlik",
    "entegre faaliyet",
    "yatırımcı sunumu",
    "investor presentation",
    "yatirimci-sunumu",
    "financial report",
    "finansal rapor"
]

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.7",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}


def is_allowed_by_robots(url: str, user_agent: str = "*") -> bool:
    """Check robots.txt compliance for given URL."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        # If robots.txt cannot be fetched or read, default to allow
        return True


def is_official_domain(url: str, official_domains: list[str]) -> bool:
    """Verify if URL netloc belongs to allowed official domains."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    for allowed in official_domains:
        if allowed.lower() in domain:
            return True
    return False


def is_report_link(href: str, link_text: str) -> bool:
    """Check if link href or text matches report keywords."""
    combined = (href + " " + link_text).lower()
    return any(kw in combined for kw in REPORT_KEYWORDS)


def fetch_url(session: requests.Session, url: str, max_retries: int = 3, backoff: float = 1.0):
    """Fetch URL with retries and timeout handling."""
    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(url, timeout=12, allow_redirects=True, verify=False)
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                time.sleep(backoff * attempt)
            else:
                time.sleep(0.5)
        except Exception:
            if attempt < max_retries:
                time.sleep(1.0)
    return None


def crawl_company_domain(company_cfg: dict, max_depth: int = 2):
    """Crawls official domains for a company up to max_depth and downloads PDFs."""
    company_id = company_cfg["id"]
    company_name = company_cfg["name"]
    official_domains = company_cfg.get("official_domains", [])

    print(f"\n============================================================", flush=True)
    print(f"Crawling Reports for: {company_name} ({company_id})", flush=True)
    print(f"Official Domains: {official_domains}", flush=True)
    print(f"============================================================", flush=True)


    session = requests.Session()
    session.headers.update(HTTP_HEADERS)

    # Disable SSL warnings for legacy IR domains
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    visited_urls = set()
    found_pdf_urls = set()
    queue = []

    for dom in official_domains:
        seed_urls = [
            f"https://www.{dom}",
            f"https://{dom}",
            f"https://www.{dom}/tr/yatirimci-iliskileri",
            f"https://www.{dom}/investor-relations"
        ]
        for su in seed_urls:
            queue.append((su, 0))

    while queue:
        url, depth = queue.pop(0)

        if url in visited_urls or depth > max_depth:
            continue

        visited_urls.add(url)

        if not is_official_domain(url, official_domains):
            continue

        if not is_allowed_by_robots(url):
            print(f"  [ROBOTS DISALLOWED] {url}")
            continue

        print(f"  [Depth {depth}] Crawling: {url} ...")
        time.sleep(1.0)  # Politeness delay

        resp = fetch_url(session, url)
        if not resp:
            continue

        content_type = resp.headers.get("Content-Type", "").lower()

        # Handle direct PDF
        if "application/pdf" in content_type or url.lower().endswith(".pdf") or resp.content.startswith(b"%PDF"):
            found_pdf_urls.add(url)
            continue

        # Parse HTML
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            link_text = a.get_text(strip=True)
            full_url = urljoin(url, href)

            if full_url.lower().endswith(".pdf") or ".pdf" in full_url.lower():
                if is_report_link(full_url, link_text):
                    found_pdf_urls.add(full_url)
            elif is_report_link(full_url, link_text) and depth < max_depth:
                if full_url not in visited_urls and is_official_domain(full_url, official_domains):
                    queue.append((full_url, depth + 1))

    print(f"\nDiscovered {len(found_pdf_urls)} candidate PDF report URLs for {company_name}.\n")

    # Download & Validate PDFs
    ticker_dir = RAW_DIR / company_id.upper()
    ticker_dir.mkdir(parents=True, exist_ok=True)
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    downloaded_count = 0
    verified_count = 0
    quarantined_count = 0

    manifest_records = []

    for pdf_url in sorted(list(found_pdf_urls)):
        print(f"Downloading candidate PDF: {pdf_url} ...")
        time.sleep(1.0)

        pdf_resp = fetch_url(session, pdf_url)
        if not pdf_resp or not pdf_resp.content.startswith(b"%PDF"):
            print(f"  -> Failed to download valid PDF bytes from {pdf_url}")
            continue

        pdf_data = pdf_resp.content
        file_size = len(pdf_data)

        # Generate filename
        url_fn = Path(urlparse(pdf_url).path).name
        if not url_fn or not url_fn.endswith(".pdf"):
            url_fn = "report.pdf"

        filename = f"{company_id.upper()}__{url_fn}"
        local_path = ticker_dir / filename

        with open(local_path, "wb") as pf:
            pf.write(pdf_data)

        downloaded_count += 1

        # Run validation
        val_res = validate_pdf_content(local_path, company_cfg)
        status = val_res["status"]
        sha256_hash = val_res["sha256"]
        doc_type = infer_document_type(filename, "")

        parsed_u = urlparse(pdf_url)

        record = {
            "company_id": company_id,
            "company_name": company_name,
            "document_type": doc_type,
            "year": val_res["year"],
            "source_url": pdf_url,
            "source_domain": parsed_u.netloc,
            "file_path": str(local_path.relative_to(PROJECT_ROOT)) if status != "quarantined" else f"data/quarantine/{company_id}/{filename}",
            "sha256": sha256_hash,
            "validation_status": status
        }

        if val_res.get("reason"):
            record["quarantine_reason"] = val_res["reason"]

        manifest_records.append(record)

        if status == "quarantined":
            q_dir = QUARANTINE_DIR / company_id
            q_dir.mkdir(parents=True, exist_ok=True)
            q_target = q_dir / filename
            shutil.move(local_path, q_target)
            quarantined_count += 1
            print(f"  -> [QUARANTINED] Reason: {val_res['reason']}")
        else:
            verified_count += 1
            print(f"  -> [{status.upper()}] Verified Year: {val_res['year']}")

    # Append to manifest.jsonl
    if manifest_records:
        with open(MANIFEST_JSONL, "a", encoding="utf-8") as mf:
            for rec in manifest_records:
                mf.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return {
        "downloaded": downloaded_count,
        "verified": verified_count,
        "quarantined": quarantined_count
    }


def main():
    parser = argparse.ArgumentParser(description="Verified Company Report Crawler")
    parser.add_argument("--company", type=str, help="Company ID or Ticker to crawl (e.g. akbank or AKBNK)")
    parser.add_argument("--all", action="store_true", help="Crawl all configured companies")
    parser.add_argument("--missing", action="store_true", help="Crawl missing annual report targets from data/missing_reports.json")
    args = parser.parse_args()

    companies = load_companies_config()
    comp_map = {c["id"]: c for c in companies}
    # Also map ticker to company config
    for c in companies:
        comp_map[c["id"].upper()] = c

    if args.missing:
        missing_json_path = PROJECT_ROOT / "data" / "missing_reports.json"
        if not missing_json_path.exists():
            print(f"Error: {missing_json_path} not found. Run scripts/build_baseline.py first.")
            sys.exit(1)

        with open(missing_json_path, "r", encoding="utf-8") as f:
            missing_info = json.load(f)

        missing_targets = missing_info.get("missing_targets", [])
        print(f"Targeting crawler at {len(missing_targets)} missing annual report slots...\n")

        cids_to_crawl = sorted(list(set(t["canonical_ticker"].lower() for t in missing_targets)))
        total_res = {"downloaded": 0, "verified": 0, "quarantined": 0}

        for cid in cids_to_crawl:
            if cid in comp_map:
                res = crawl_company_domain(comp_map[cid])
                for k in total_res:
                    total_res[k] += res[k]

        print(f"\nCompleted missing targets crawl: {total_res}")
    elif args.company:
        cid = args.company.lower()
        if cid not in comp_map:
            print(f"Error: Company '{cid}' not found in config/companies.yaml")
            sys.exit(1)
        res = crawl_company_domain(comp_map[cid])
        print(f"\nCompleted crawl for {cid}: {res}")
    elif args.all:
        total_res = {"downloaded": 0, "verified": 0, "quarantined": 0}
        for cid, comp_cfg in comp_map.items():
            if len(cid) > 5:  # filter duplicate ticker keys
                res = crawl_company_domain(comp_cfg)
                for k in total_res:
                    total_res[k] += res[k]
        print(f"\nCompleted crawl for all companies: {total_res}")
    else:
        parser.print_help()



if __name__ == "__main__":
    main()
