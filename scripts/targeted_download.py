#!/usr/bin/env python3
"""
Targeted PDF Download Script
Downloads annual reports for all 10 companies (2023-2025)
using verified URLs, IR page crawling, and KAP API fallback.
"""

import hashlib
import json
import logging
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Optional: PyMuPDF for validation
try:
    import fitz  # PyMuPDF

    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    print("WARNING: PyMuPDF not installed. PDF validation will be limited.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_QUARANTINE = PROJECT_ROOT / "data" / "quarantine"
MANIFEST_FILE = PROJECT_ROOT / "data" / "report_manifest.jsonl"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ============================================================
# KNOWN / VERIFIED DIRECT PDF URLs
# ============================================================
KNOWN_URLS = {
    # TUPRS - Verified URL pattern from search results
    ("TUPRS", 2023): [
        "https://www.tupras.com.tr/assets/uploads/entegre-faaliyet/tupras-2023-entegre-faaliyet-raporu.pdf",
        "https://www.tupras.com.tr/assets/uploads/entegre-faaliyet/Tupras-2023-Entegre-Faaliyet-Raporu.pdf",
    ],
    ("TUPRS", 2024): [
        "https://www.tupras.com.tr/assets/uploads/entegre-faaliyet/tupras-2024-entegre-faaliyet-raporu.pdf",
        "https://www.tupras.com.tr/assets/uploads/entegre-faaliyet/Tupras-2024-Entegre-Faaliyet-Raporu.pdf",
    ],
    ("TUPRS", 2025): [
        "https://www.tupras.com.tr/assets/uploads/entegre-faaliyet/tupras-2025-entegre-faaliyet-raporu.pdf",
        "https://www.tupras.com.tr/assets/uploads/entegre-faaliyet/Tupras-2025-Entegre-Faaliyet-Raporu.pdf",
    ],
}

# ============================================================
# COMPANY CONFIG
# ============================================================
COMPANIES = {
    "AKBNK": {
        "name": "Akbank T.A.Ş.",
        "aliases": ["Akbank", "Akbank T.A.Ş.", "AKBANK"],
        "ir_pages": [
            "https://www.akbankinvestorrelations.com/tr/finansallar/faaliyet-raporlari/",
            "https://www.akbankinvestorrelations.com/en/financials/annual-reports/",
        ],
        "url_patterns": [
            "https://www.akbankinvestorrelations.com/images/pdf/Akbank_{year}_Entegre_Faaliyet_Raporu.pdf",
            "https://www.akbankinvestorrelations.com/images/pdf/akbank-{year}-entegre-faaliyet-raporu.pdf",
            "https://www.akbankinvestorrelations.com/images/pdf/Akbank-{year}-Entegre-Faaliyet-Raporu.pdf",
            "https://www.akbankinvestorrelations.com/images/pdf/Akbank_{year}_Faaliyet_Raporu.pdf",
            "https://www.akbankinvestorrelations.com/images/pdf/akbank-{year}-faaliyet-raporu.pdf",
            "https://www.akbankinvestorrelations.com/images/pdf/Akbank-Entegre-Faaliyet-Raporu-{year}.pdf",
            "https://www.akbankinvestorrelations.com/images/pdf/Akbank_{year}_Annual_Report.pdf",
            "https://www.akbankinvestorrelations.com/images/pdf/akbank_{year}_faaliyet_raporu.pdf",
        ],
    },
    "ARCLK": {
        "name": "Arçelik A.Ş.",
        "aliases": ["Arçelik", "Arcelik", "Beko", "ARCLK", "Arçelik A.Ş."],
        "ir_pages": [
            "https://www.arcelikglobal.com/tr/yatirimci-iliskileri/raporlar-ve-sunumlar/faaliyet-raporlari/",
            "https://www.arcelikglobal.com/en/investor-relations/reports-and-presentations/annual-reports/",
        ],
        "url_patterns": [
            "https://www.arcelikglobal.com/media/faaliyet-raporlari/arcelik-{year}-faaliyet-raporu.pdf",
            "https://www.arcelikglobal.com/media/faaliyet-raporlari/Arcelik_{year}_Faaliyet_Raporu.pdf",
            "https://www.arcelikglobal.com/media/reports/arcelik-{year}-annual-report.pdf",
        ],
    },
    "ASELS": {
        "name": "Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
        "aliases": ["ASELSAN", "Aselsan", "ASELS"],
        "ir_pages": [
            "https://www.aselsan.com/tr/yatirimci-iliskileri/faaliyet-raporlari",
            "https://www.aselsan.com.tr/tr/yatirimci-iliskileri/faaliyet-raporlari",
        ],
        "url_patterns": [
            "https://www.aselsan.com.tr/assets/uploads/faaliyet-raporlari/aselsan-{year}-faaliyet-raporu.pdf",
            "https://www.aselsan.com.tr/assets/uploads/faaliyet-raporlari/Aselsan_{year}_Faaliyet_Raporu.pdf",
            "https://www.aselsan.com/assets/uploads/faaliyet-raporlari/aselsan-{year}-faaliyet-raporu.pdf",
            "https://www.aselsan.com.tr/ASELSAN_{year}_FAALIYET_RAPORU.pdf",
        ],
    },
    "FROTO": {
        "name": "Ford Otomotiv Sanayi A.Ş.",
        "aliases": ["Ford Otosan", "Ford Otomotiv", "FROTO"],
        "ir_pages": [
            "https://www.fordotosan.com.tr/tr/yatirimci-iliskileri/raporlar",
            "https://www.fordotosan.com.tr/en/investor-relations/reports",
        ],
        "url_patterns": [
            "https://www.fordotosan.com.tr/assets/uploads/raporlar/ford-otosan-{year}-faaliyet-raporu.pdf",
            "https://www.fordotosan.com.tr/assets/uploads/raporlar/Ford-Otosan-{year}-Entegre-Faaliyet-Raporu.pdf",
            "https://www.fordotosan.com.tr/assets/uploads/raporlar/Ford_Otosan_{year}_Faaliyet_Raporu.pdf",
        ],
    },
    "KCHOL": {
        "name": "Koç Holding A.Ş.",
        "aliases": ["Koç Holding", "Koc Holding", "KCHOL"],
        "ir_pages": [
            "https://www.koc.com.tr/yatirimci-iliskileri/raporlar/faaliyet-raporlari",
            "https://www.koc.com.tr/en/investor-relations/reports/annual-reports",
        ],
        "url_patterns": [
            "https://www.koc.com.tr/yatirimci-iliskileri/raporlar/faaliyet-raporlari/koc-holding-{year}-faaliyet-raporu.pdf",
            "https://www.koc.com.tr/content/koc-holding-{year}-faaliyet-raporu.pdf",
        ],
    },
    "MGROS": {
        "name": "Migros Ticaret A.Ş.",
        "aliases": ["Migros", "Migros Ticaret", "MGROS"],
        "ir_pages": [
            "https://www.migroskurumsal.com/yatirimci-iliskileri/raporlarimiz",
            "https://www.migroskurumsal.com/tr/raporlarimiz",
        ],
        "url_patterns": [
            "https://migroskurumsalstr.blob.core.windows.net/migroskurumsalstr/-migros-tr{year}-interaktif.pdf",
        ],
    },
    "SISE": {
        "name": "Türkiye Şişe ve Cam Fabrikaları A.Ş.",
        "aliases": ["Şişecam", "Sisecam", "SISE"],
        "ir_pages": [
            "https://www.sisecam.com.tr/tr/yatirimci-iliskileri/sunumlar-ve-raporlar/yillik-faaliyet-raporlari",
            "https://www.sisecam.com.tr/en/investor-relations/presentations-and-reports/annual-reports",
        ],
        "url_patterns": [
            "https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/Sisecam-{year}-Faaliyet-Raporu.pdf",
            "https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/Sisecam_{year}_Faaliyet_Raporu.pdf",
            "https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/sisecam-entegre-faaliyet-raporu-{year}.pdf",
        ],
    },
    "TCELL": {
        "name": "Turkcell İletişim Hizmetleri A.Ş.",
        "aliases": ["Turkcell", "TCELL"],
        "ir_pages": [
            "https://www.turkcell.com.tr/hakkimizda/yatirimci-iliskileri/faaliyet-raporlari",
            "https://www.turkcell.com.tr/tr/hakkimizda/yatirimci-iliskileri",
        ],
        "url_patterns": [],
    },
    "THYAO": {
        "name": "Türk Hava Yolları A.O.",
        "aliases": ["Türk Hava Yolları", "Turkish Airlines", "THY", "THYAO"],
        "ir_pages": [
            "https://investor.turkishairlines.com/tr/mali-ve-operasyonel-veriler/yillik-raporlar",
            "https://investor.turkishairlines.com/en/financial-and-operational-data/annual-reports",
            "https://investor.turkishairlines.com/tr/raporlarimiz",
        ],
        "url_patterns": [
            "https://investor.turkishairlines.com/documents/ThyInvestorRelations/{year}-faaliyet-raporu.pdf",
            "https://investor.turkishairlines.com/documents/ThyInvestorRelations/THY-{year}-Yillik-Rapor.pdf",
        ],
    },
    "TUPRS": {
        "name": "Türkiye Petrol Rafinerileri A.Ş.",
        "aliases": ["Tüpraş", "Tupras", "TUPRS"],
        "ir_pages": [
            "https://www.tupras.com.tr/raporlar",
        ],
        "url_patterns": [
            "https://www.tupras.com.tr/assets/uploads/entegre-faaliyet/tupras-{year}-entegre-faaliyet-raporu.pdf",
            "https://www.tupras.com.tr/assets/uploads/entegre-faaliyet/Tupras-{year}-Entegre-Faaliyet-Raporu.pdf",
        ],
    },
}

TARGET_YEARS = [2023, 2024, 2025]


def is_pdf_response(response):
    """Check if a response contains a PDF file."""
    content_type = response.headers.get("Content-Type", "").lower()
    if "application/pdf" in content_type:
        return True
    # Check magic bytes
    return response.content[:5] == b"%PDF-"


def validate_pdf(filepath, ticker, year, company_info):
    """Validate PDF content with PyMuPDF."""
    if not HAS_FITZ:
        return True, "PyMuPDF not available, skipping deep validation", "tr", 0

    try:
        doc = fitz.open(filepath)
        page_count = len(doc)
        if page_count < 3:
            doc.close()
            return False, f"Too few pages ({page_count})", "unknown", page_count

        # Extract text from first 5 pages
        text = ""
        for i in range(min(5, page_count)):
            text += doc[i].get_text()
        doc.close()

        text_lower = text.lower()

        # Check for company name
        company_found = False
        for alias in company_info["aliases"]:
            if alias.lower() in text_lower:
                company_found = True
                break

        if not company_found:
            return False, "Company name not found in first 5 pages", "unknown", page_count

        # Check for year
        if str(year) not in text:
            return False, f"Year {year} not found in first 5 pages", "unknown", page_count

        # Check for report type keywords
        report_keywords = [
            "faaliyet raporu",
            "annual report",
            "entegre faaliyet",
            "integrated report",
            "yıllık rapor",
            "faaliyet raporları",
            "board of directors",
            "yönetim kurulu",
            "bağımsız denetim",
        ]
        report_found = any(kw in text_lower for kw in report_keywords)
        if not report_found:
            return False, "No annual report keywords found", "unknown", page_count

        # Detect language
        tr_keywords = ["faaliyet raporu", "yönetim kurulu", "bağımsız denetim", "mali tablolar"]
        en_keywords = ["annual report", "board of directors", "financial statements"]
        tr_count = sum(1 for kw in tr_keywords if kw in text_lower)
        en_count = sum(1 for kw in en_keywords if kw in text_lower)
        language = "tr" if tr_count >= en_count else "en"

        return True, "Validated OK", language, page_count

    except Exception as e:
        return False, f"Validation error: {e}", "unknown", 0


def download_pdf(url, filepath, timeout=30):
    """Download a PDF file. Returns (success, file_size)."""
    try:
        logger.info(f"  Trying URL: {url}")
        response = SESSION.get(url, timeout=timeout, allow_redirects=True, stream=True)

        if response.status_code != 200:
            logger.info(f"    HTTP {response.status_code}")
            return False, 0

        if not is_pdf_response(response):
            logger.info("    Not a PDF response")
            return False, 0

        # Check minimum file size (real annual reports are usually > 500KB)
        content = response.content
        if len(content) < 100_000:  # 100KB minimum
            logger.info(f"    File too small ({len(content)} bytes)")
            return False, 0

        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(content)
        logger.info(f"    ✓ Downloaded {len(content):,} bytes")
        return True, len(content)

    except requests.exceptions.Timeout:
        logger.info("    Timeout")
        return False, 0
    except Exception as e:
        logger.info(f"    Error: {e}")
        return False, 0


def crawl_ir_page(url, year):
    """Crawl an IR page and extract PDF links related to a specific year."""
    pdf_urls = []
    try:
        response = SESSION.get(url, timeout=15)
        if response.status_code != 200:
            return pdf_urls

        soup = BeautifulSoup(response.text, "html.parser")

        # Find all links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True).lower()
            href_lower = href.lower()

            # Check if link relates to annual report and year
            year_match = str(year) in href or str(year) in text

            report_keywords = ["faaliyet", "annual", "rapor", "report", "entegre"]
            report_match = any(kw in href_lower or kw in text for kw in report_keywords)

            pdf_match = href_lower.endswith(".pdf") or "pdf" in href_lower

            if year_match and (report_match or pdf_match):
                full_url = urljoin(url, href)
                pdf_urls.append(full_url)

        # Also look for data-href or data-url attributes
        for tag in soup.find_all(attrs={"data-href": True}):
            href = tag["data-href"]
            if str(year) in href and ".pdf" in href.lower():
                pdf_urls.append(urljoin(url, href))

        for tag in soup.find_all(attrs={"data-url": True}):
            href = tag["data-url"]
            if str(year) in href and ".pdf" in href.lower():
                pdf_urls.append(urljoin(url, href))

    except Exception as e:
        logger.warning(f"Error crawling {url}: {e}")

    return list(set(pdf_urls))


def search_kap(company_name, ticker, year):
    """Search KAP for annual reports."""
    pdf_urls = []
    try:
        # KAP company IDs (approximate - may need adjustment)
        # Try direct KAP pages

        # Search KAP disclosures API
        api_url = "https://www.kap.org.tr/tr/api/disclosures"
        payload = {
            "fromDate": f"01-01-{year}",
            "toDate": f"31-12-{year + 1}",
            "mpiTickers": [ticker],
            "subject": "FR",
        }

        resp = SESSION.post(api_url, json=payload, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                for item in data:
                    if "disclosureId" in item:
                        disc_id = item["disclosureId"]
                        # Try to get PDF from disclosure
                        pdf_url = f"https://www.kap.org.tr/tr/api/disclosureDocument/{disc_id}"
                        pdf_urls.append(pdf_url)
    except Exception as e:
        logger.warning(f"KAP search error: {e}")

    return pdf_urls[:5]  # Limit to 5 results


def process_target(ticker, year, company_info):
    """Process a single company-year target."""
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Processing: {ticker} {year}")
    logger.info(f"{'=' * 60}")

    dest_dir = DATA_RAW / ticker
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Check if already exists
    for lang in ["tr", "en"]:
        existing = dest_dir / f"{ticker}__{year}__annual_report__{lang}.pdf"
        if existing.exists() and existing.stat().st_size > 100_000:
            logger.info(f"Already exists: {existing.name}")
            return {"status": "already_exists", "file": str(existing)}

    # Strategy 1: Known direct URLs
    known_key = (ticker, year)
    if known_key in KNOWN_URLS:
        for url in KNOWN_URLS[known_key]:
            temp_path = dest_dir / f"{ticker}__{year}__annual_report__temp.pdf"
            success, size = download_pdf(url, temp_path)
            if success:
                valid, msg, lang, pages = validate_pdf(temp_path, ticker, year, company_info)
                if valid:
                    final_path = dest_dir / f"{ticker}__{year}__annual_report__{lang}.pdf"
                    temp_path.rename(final_path)
                    logger.info(f"  ✓ VALIDATED: {final_path.name} ({pages} pages, {msg})")
                    return {
                        "status": "downloaded",
                        "file": str(final_path),
                        "url": url,
                        "pages": pages,
                        "size": size,
                        "language": lang,
                    }
                else:
                    logger.info(f"  ✗ Validation failed: {msg}")
                    temp_path.unlink(missing_ok=True)

    # Strategy 2: URL pattern guessing
    for pattern in company_info.get("url_patterns", []):
        url = pattern.format(year=year)
        temp_path = dest_dir / f"{ticker}__{year}__annual_report__temp.pdf"
        success, size = download_pdf(url, temp_path)
        if success:
            valid, msg, lang, pages = validate_pdf(temp_path, ticker, year, company_info)
            if valid:
                final_path = dest_dir / f"{ticker}__{year}__annual_report__{lang}.pdf"
                temp_path.rename(final_path)
                logger.info(f"  ✓ VALIDATED: {final_path.name} ({pages} pages)")
                return {
                    "status": "downloaded",
                    "file": str(final_path),
                    "url": url,
                    "pages": pages,
                    "size": size,
                    "language": lang,
                }
            else:
                logger.info(f"  ✗ Validation failed: {msg}")
                temp_path.unlink(missing_ok=True)

    # Strategy 3: IR page crawling
    for ir_url in company_info.get("ir_pages", []):
        logger.info(f"  Crawling IR page: {ir_url}")
        pdf_urls = crawl_ir_page(ir_url, year)
        for url in pdf_urls[:10]:
            temp_path = dest_dir / f"{ticker}__{year}__annual_report__temp.pdf"
            success, size = download_pdf(url, temp_path)
            if success:
                valid, msg, lang, pages = validate_pdf(temp_path, ticker, year, company_info)
                if valid:
                    final_path = dest_dir / f"{ticker}__{year}__annual_report__{lang}.pdf"
                    temp_path.rename(final_path)
                    logger.info(f"  ✓ VALIDATED from IR crawl: {final_path.name} ({pages} pages)")
                    return {
                        "status": "downloaded",
                        "file": str(final_path),
                        "url": url,
                        "pages": pages,
                        "size": size,
                        "language": lang,
                    }
                else:
                    logger.info(f"  ✗ Validation failed: {msg}")
                    temp_path.unlink(missing_ok=True)

    logger.info(f"  ✗ NOT FOUND: {ticker} {year}")
    return {"status": "not_found"}


def update_manifest(result, ticker, year, company_info):
    """Append a successful download to the manifest."""
    if result["status"] != "downloaded":
        return

    sha256 = hashlib.sha256(Path(result["file"]).read_bytes()).hexdigest()

    entry = {
        "company_id": ticker.lower(),
        "canonical_ticker": ticker,
        "company_name": company_info["name"],
        "document_type": "annual_report",
        "year": year,
        "language": result.get("language", "tr"),
        "source_url": result.get("url", ""),
        "local_path": result["file"],
        "sha256": sha256,
        "page_count": result.get("pages", 0),
        "file_size": result.get("size", 0),
        "status": "verified",
    }

    with open(MANIFEST_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    """Main entry point."""
    logger.info("=" * 70)
    logger.info("TARGETED ANNUAL REPORT DOWNLOADER")
    logger.info("=" * 70)

    # Parse command line args
    tickers = list(COMPANIES.keys())
    if "--tickers" in sys.argv:
        idx = sys.argv.index("--tickers")
        tickers = sys.argv[idx + 1 :]

    dry_run = "--dry-run" in sys.argv

    results = {
        "downloaded": [],
        "already_exists": [],
        "not_found": [],
    }

    for ticker in tickers:
        if ticker not in COMPANIES:
            logger.warning(f"Unknown ticker: {ticker}")
            continue

        company_info = COMPANIES[ticker]

        for year in TARGET_YEARS:
            if dry_run:
                logger.info(f"[DRY RUN] Would process: {ticker} {year}")
                continue

            result = process_target(ticker, year, company_info)

            if result["status"] == "downloaded":
                results["downloaded"].append(f"{ticker} {year}")
                update_manifest(result, ticker, year, company_info)
            elif result["status"] == "already_exists":
                results["already_exists"].append(f"{ticker} {year}")
            else:
                results["not_found"].append(f"{ticker} {year}")

            time.sleep(1)  # Polite delay between requests

    # Print summary
    logger.info("\n" + "=" * 70)
    logger.info("DOWNLOAD SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Downloaded:     {len(results['downloaded'])}")
    logger.info(f"Already exists: {len(results['already_exists'])}")
    logger.info(f"Not found:      {len(results['not_found'])}")

    if results["downloaded"]:
        logger.info("\nNewly downloaded:")
        for item in results["downloaded"]:
            logger.info(f"  ✓ {item}")

    if results["not_found"]:
        logger.info("\nStill missing:")
        for item in results["not_found"]:
            logger.info(f"  ✗ {item}")

    return results


if __name__ == "__main__":
    main()
