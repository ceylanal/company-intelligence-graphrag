#!/usr/bin/env python3
"""
Brute-force URL tester for Turkish company annual reports.
Tests all known and guessable URL patterns for each company.
"""

import hashlib
import json
import logging
import sys
import time
from pathlib import Path

import requests

try:
    import fitz

    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
MANIFEST_FILE = PROJECT_ROOT / "data" / "report_manifest.jsonl"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/pdf,*/*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ============================================================
# COMPANIES + ALIASES for validation
# ============================================================
COMPANY_INFO = {
    "AKBNK": {"name": "Akbank T.A.Ş.", "aliases": ["Akbank", "AKBANK", "Akbank T.A.Ş."]},
    "ARCLK": {
        "name": "Arçelik A.Ş.",
        "aliases": ["Arçelik", "Arcelik", "Beko", "ARÇELİK", "ARCELIK"],
    },
    "ASELS": {
        "name": "Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
        "aliases": ["ASELSAN", "Aselsan", "ASELS"],
    },
    "FROTO": {
        "name": "Ford Otomotiv Sanayi A.Ş.",
        "aliases": ["Ford Otosan", "Ford Otomotiv", "FORD OTOSAN", "Ford"],
    },
    "KCHOL": {
        "name": "Koç Holding A.Ş.",
        "aliases": ["Koç Holding", "Koc Holding", "KOÇ", "KCHOL", "Koç"],
    },
    "MGROS": {"name": "Migros Ticaret A.Ş.", "aliases": ["Migros", "MİGROS", "MIGROS"]},
    "SISE": {
        "name": "Türkiye Şişe ve Cam Fabrikaları A.Ş.",
        "aliases": ["Şişecam", "Sisecam", "ŞİŞECAM", "SISECAM"],
    },
    "TCELL": {"name": "Turkcell İletişim Hizmetleri A.Ş.", "aliases": ["Turkcell", "TURKCELL"]},
    "THYAO": {
        "name": "Türk Hava Yolları A.O.",
        "aliases": ["Türk Hava Yolları", "Turkish Airlines", "THY", "THYAO"],
    },
    "TUPRS": {
        "name": "Türkiye Petrol Rafinerileri A.Ş.",
        "aliases": ["Tüpraş", "Tupras", "TÜPRAŞ", "TUPRAS"],
    },
}


# ============================================================
# ALL CANDIDATE URLs - gathered from web searches
# ============================================================
def get_candidate_urls(ticker, year):
    """Return a list of candidate PDF URLs for a given ticker and year."""
    urls = []
    y = str(year)

    if ticker == "TUPRS":
        urls = [
            # Found from web search - different path pattern for 2023
            f"https://www.tupras.com.tr/media/2513/tupras-{y}-entegre-faaliyet-raporu.pdf",
            f"https://www.tupras.com.tr/media/2514/tupras-{y}-integrated-annual-report.pdf",
            f"https://www.tupras.com.tr/assets/uploads/entegre-faaliyet/tupras-{y}-entegre-faaliyet-raporu.pdf",
            f"https://www.tupras.com.tr/assets/uploads/entegre-faaliyet/Tupras-{y}-Entegre-Faaliyet-Raporu.pdf",
            f"https://www.tupras.com.tr/assets/uploads/raporlar/tupras-{y}-faaliyet-raporu.pdf",
            # Media path variations
            f"https://www.tupras.com.tr/media/tupras-{y}-entegre-faaliyet-raporu.pdf",
        ]

    elif ticker == "AKBNK":
        urls = [
            # Akbank IR site patterns
            f"https://www.akbankinvestorrelations.com/images/pdf/Akbank-{y}-Entegre-Faaliyet-Raporu.pdf",
            f"https://www.akbankinvestorrelations.com/images/pdf/akbank-{y}-entegre-faaliyet-raporu.pdf",
            f"https://www.akbankinvestorrelations.com/images/pdf/Akbank_{y}_Entegre_Faaliyet_Raporu.pdf",
            f"https://www.akbankinvestorrelations.com/images/pdf/Akbank-Entegre-Faaliyet-Raporu-{y}.pdf",
            f"https://www.akbankinvestorrelations.com/images/pdf/Akbank-{y}-Annual-Report.pdf",
            f"https://www.akbankinvestorrelations.com/images/pdf/akbank_{y}_faaliyet_raporu.pdf",
            f"https://www.akbankinvestorrelations.com/pdf/Akbank-{y}-Entegre-Faaliyet-Raporu.pdf",
            f"https://www.akbankinvestorrelations.com/pdf/akbank-{y}-entegre-faaliyet-raporu.pdf",
            # Alternative subdomain patterns
            f"https://www.akbankinvestorrelations.com/storage/faaliyet-raporlari/akbank-{y}-entegre-faaliyet-raporu.pdf",
            f"https://www.akbankinvestorrelations.com/uploads/pdf/akbank-{y}-entegre-faaliyet-raporu.pdf",
            f"https://www.akbankinvestorrelations.com/content/pdf/akbank-{y}-entegre-faaliyet-raporu.pdf",
            f"https://www.akbankinvestorrelations.com/pdf/Akbank_Entegre_Faaliyet_Raporu_{y}.pdf",
            # Main akbank.com domain
            f"https://www.akbank.com/yatirimci-iliskileri/pdf/akbank-{y}-entegre-faaliyet-raporu.pdf",
        ]

    elif ticker == "ARCLK":
        urls = [
            f"https://www.arcelikglobal.com/media/6901/arcelik-{y}-faaliyet-raporu.pdf",
            f"https://www.arcelikglobal.com/media/6801/arcelik-{y}-faaliyet-raporu.pdf",
            f"https://www.arcelikglobal.com/media/6701/arcelik-{y}-faaliyet-raporu.pdf",
            f"https://www.arcelikglobal.com/media/7001/arcelik-{y}-faaliyet-raporu.pdf",
            f"https://www.arcelikglobal.com/media/7101/arcelik-{y}-faaliyet-raporu.pdf",
            f"https://www.arcelikglobal.com/media/arcelik-{y}-faaliyet-raporu.pdf",
            f"https://www.arcelikglobal.com/media/faaliyet-raporlari/arcelik-{y}-faaliyet-raporu.pdf",
            f"https://www.arcelikglobal.com/media/faaliyet-raporlari/Arcelik-{y}-Faaliyet-Raporu.pdf",
            f"https://www.arcelikglobal.com/assets/pdf/arcelik-{y}-faaliyet-raporu.pdf",
            f"https://www.arcelikglobal.com/uploads/pdf/arcelik-{y}-faaliyet-raporu.pdf",
            # Beko domain
            f"https://www.arcelikglobal.com/media/reports/arcelik-{y}-annual-report.pdf",
            f"https://www.arcelikglobal.com/media/reports/beko-{y}-annual-report.pdf",
            # Entegre variations
            f"https://www.arcelikglobal.com/media/arcelik-{y}-entegre-faaliyet-raporu.pdf",
            f"https://www.arcelikglobal.com/media/faaliyet-raporlari/arcelik-{y}-entegre-faaliyet-raporu.pdf",
        ]

    elif ticker == "ASELS":
        urls = [
            f"https://www.aselsan.com.tr/assets/uploads/faaliyet-raporlari/aselsan-{y}-faaliyet-raporu.pdf",
            f"https://www.aselsan.com.tr/assets/uploads/faaliyet-raporlari/ASELSAN_{y}_Faaliyet_Raporu.pdf",
            f"https://www.aselsan.com/assets/uploads/faaliyet-raporlari/aselsan-{y}-faaliyet-raporu.pdf",
            f"https://www.aselsan.com.tr/ASELSAN_{y}_FAALIYET_RAPORU.pdf",
            f"https://www.aselsan.com.tr/assets/pdf/ASELSAN-{y}-Faaliyet-Raporu.pdf",
            f"https://www.aselsan.com.tr/media/faaliyet-raporlari/aselsan-{y}-faaliyet-raporu.pdf",
            f"https://www.aselsan.com/media/faaliyet-raporlari/aselsan-{y}-faaliyet-raporu.pdf",
            f"https://www.aselsan.com.tr/uploads/docs/aselsan-{y}-faaliyet-raporu.pdf",
            f"https://www.aselsan.com/tr/yatirimci-iliskileri/faaliyet-raporlari/aselsan-{y}-faaliyet-raporu.pdf",
        ]

    elif ticker == "FROTO":
        urls = [
            f"https://www.fordotosan.com.tr/assets/uploads/raporlar/ford-otosan-{y}-entegre-faaliyet-raporu.pdf",
            f"https://www.fordotosan.com.tr/assets/uploads/raporlar/Ford-Otosan-{y}-Entegre-Faaliyet-Raporu.pdf",
            f"https://www.fordotosan.com.tr/assets/uploads/raporlar/ford-otosan-{y}-faaliyet-raporu.pdf",
            f"https://www.fordotosan.com.tr/media/ford-otosan-{y}-entegre-faaliyet-raporu.pdf",
            f"https://www.fordotosan.com.tr/media/ford-otosan-{y}-faaliyet-raporu.pdf",
            f"https://www.fordotosan.com.tr/pdf/ford-otosan-{y}-faaliyet-raporu.pdf",
            f"https://www.fordotosan.com.tr/assets/pdf/ford-otosan-{y}-entegre-faaliyet-raporu.pdf",
            f"https://www.fordotosan.com.tr/uploads/raporlar/Ford_Otosan_{y}_Faaliyet_Raporu.pdf",
            f"https://www.fordotosan.com.tr/assets/uploads/Ford-Otosan-{y}-Faaliyet-Raporu.pdf",
        ]

    elif ticker == "KCHOL":
        urls = [
            f"https://www.koc.com.tr/yatirimci-iliskileri/raporlar/faaliyet-raporlari/koc-holding-{y}-faaliyet-raporu.pdf",
            f"https://www.koc.com.tr/content/koc-holding-{y}-faaliyet-raporu.pdf",
            f"https://www.koc.com.tr/media/koc-holding-{y}-faaliyet-raporu.pdf",
            f"https://www.koc.com.tr/assets/uploads/koc-holding-{y}-faaliyet-raporu.pdf",
            f"https://www.koc.com.tr/uploads/pdf/koc-holding-{y}-faaliyet-raporu.pdf",
            f"https://www.koc.com.tr/pdf/Koc-Holding-{y}-Faaliyet-Raporu.pdf",
            f"https://www.koc.com.tr/content/pdf/koc-holding-{y}-faaliyet-raporu.pdf",
            f"https://www.koc.com.tr/assets/pdf/Koc-Holding-{y}-Faaliyet-Raporu.pdf",
        ]

    elif ticker == "MGROS":
        urls = [
            f"https://migroskurumsalstr.blob.core.windows.net/migroskurumsalstr/-migros-tr{y}-interaktif.pdf",
            f"https://migroskurumsalstr.blob.core.windows.net/migroskurumsalstr/migros-{y}-entegre-faaliyet-raporu.pdf",
            f"https://migroskurumsalstr.blob.core.windows.net/migroskurumsalstr/Migros_{y}_Entegre_Faaliyet_Raporu.pdf",
            f"https://migroskurumsalstr.blob.core.windows.net/migroskurumsalstr/migros-tr-{y}-entegre-faaliyet-raporu.pdf",
            f"https://www.migroskurumsal.com/assets/pdf/migros-{y}-faaliyet-raporu.pdf",
            f"https://www.migroskurumsal.com/uploads/pdf/migros-{y}-entegre-faaliyet-raporu.pdf",
        ]

    elif ticker == "SISE":
        urls = [
            f"https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/Sisecam-{y}-Faaliyet-Raporu.pdf",
            f"https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/sisecam-{y}-faaliyet-raporu.pdf",
            f"https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/sisecam-entegre-faaliyet-raporu-{y}.pdf",
            f"https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/Sisecam-Entegre-Faaliyet-Raporu-{y}.pdf",
            f"https://www.sisecam.com.tr/media/faaliyet-raporlari/sisecam-{y}-faaliyet-raporu.pdf",
            f"https://www.sisecam.com.tr/media/faaliyet-raporlari/sisecam-entegre-faaliyet-raporu-{y}.pdf",
            f"https://www.sisecam.com.tr/assets/pdf/sisecam-{y}-faaliyet-raporu.pdf",
            f"https://www.sisecam.com.tr/uploads/pdf/sisecam-{y}-faaliyet-raporu.pdf",
        ]

    elif ticker == "TCELL":
        urls = [
            f"https://www.turkcell.com.tr/hakkimizda/yatirimci-iliskileri/pdf/turkcell-{y}-entegre-faaliyet-raporu.pdf",
            f"https://www.turkcell.com.tr/hakkimizda/yatirimci-iliskileri/pdf/Turkcell-{y}-Faaliyet-Raporu.pdf",
            f"https://www.turkcell.com.tr/assets/pdf/turkcell-{y}-faaliyet-raporu.pdf",
            f"https://www.turkcell.com.tr/uploads/pdf/turkcell-{y}-faaliyet-raporu.pdf",
            f"https://s3.turkcell.com.tr/pdf/turkcell-{y}-faaliyet-raporu.pdf",
            f"https://www.turkcell.com.tr/content/pdf/turkcell-{y}-faaliyet-raporu.pdf",
            f"https://s3.turkcell.com.tr/turkcell-{y}-entegre-faaliyet-raporu.pdf",
            # Alternative Turkcell domains
            f"https://www.ttyatirimciiliskileri.com.tr/pdf/turkcell-{y}-faaliyet-raporu.pdf",
        ]

    elif ticker == "THYAO":
        urls = [
            f"https://investor.turkishairlines.com/documents/ThyInvestorRelations/{y}-faaliyet-raporu.pdf",
            f"https://investor.turkishairlines.com/documents/ThyInvestorRelations/THY-{y}-Faaliyet-Raporu.pdf",
            f"https://investor.turkishairlines.com/documents/ThyInvestorRelations/thy-{y}-yillik-rapor.pdf",
            f"https://investor.turkishairlines.com/documents/ThyInvestorRelations/THY-{y}-Annual-Report.pdf",
            f"https://investor.turkishairlines.com/documents/ThyInvestorRelations/thy_{y}_faaliyet_raporu.pdf",
            f"https://investor.turkishairlines.com/media/pdf/thy-{y}-faaliyet-raporu.pdf",
            f"https://investor.turkishairlines.com/pdf/thy-{y}-faaliyet-raporu.pdf",
            f"https://investor.turkishairlines.com/assets/pdf/thy-{y}-faaliyet-raporu.pdf",
            # Direct domain
            f"https://www.turkishairlines.com/documents/ThyInvestorRelations/{y}-faaliyet-raporu.pdf",
        ]

    return urls


def validate_pdf(filepath, ticker, year):
    """Validate downloaded PDF."""
    if not HAS_FITZ:
        # Basic check: file starts with %PDF
        data = filepath.read_bytes()
        if data[:5] != b"%PDF-":
            return False, "Not a PDF", "unknown", 0
        return True, "Basic check passed", "tr", 0

    try:
        doc = fitz.open(str(filepath))
        page_count = len(doc)
        if page_count < 3:
            doc.close()
            return False, f"Too few pages ({page_count})", "unknown", page_count

        text = ""
        for i in range(min(5, page_count)):
            text += doc[i].get_text()
        doc.close()

        text_lower = text.lower()
        info = COMPANY_INFO[ticker]

        # Company name check
        company_found = any(alias.lower() in text_lower for alias in info["aliases"])
        if not company_found:
            return False, "Company name not found", "unknown", page_count

        # Year check
        if str(year) not in text:
            return False, f"Year {year} not found", "unknown", page_count

        # Report keyword check
        keywords = [
            "faaliyet raporu",
            "annual report",
            "entegre faaliyet",
            "integrated report",
            "yönetim kurulu",
            "board of directors",
        ]
        report_found = any(kw in text_lower for kw in keywords)
        if not report_found:
            return False, "No report keywords", "unknown", page_count

        # Language detection
        tr_kw = ["faaliyet raporu", "yönetim kurulu", "bağımsız denetim"]
        en_kw = ["annual report", "board of directors", "financial statements"]
        lang = (
            "tr"
            if sum(1 for k in tr_kw if k in text_lower) >= sum(1 for k in en_kw if k in text_lower)
            else "en"
        )

        return True, "Validated OK", lang, page_count
    except Exception as e:
        return False, f"Error: {e}", "unknown", 0


def try_download(url, timeout=20):
    """Try to download a URL and return (success, content)."""
    try:
        resp = SESSION.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            return False, None
        if resp.content[:5] != b"%PDF-":
            ct = resp.headers.get("Content-Type", "").lower()
            if "pdf" not in ct:
                return False, None
        if len(resp.content) < 100_000:  # 100KB minimum for real annual reports
            return False, None
        return True, resp.content
    except Exception:
        return False, None


def process(ticker, year):
    """Process one ticker-year combination."""
    dest_dir = DATA_RAW / ticker
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Check existing
    for lang in ["tr", "en"]:
        existing = dest_dir / f"{ticker}__{year}__annual_report__{lang}.pdf"
        if existing.exists() and existing.stat().st_size > 100_000:
            logger.info(f"  ✓ Already exists: {existing.name}")
            return "exists"

    urls = get_candidate_urls(ticker, year)
    logger.info(f"  Testing {len(urls)} candidate URLs...")

    for url in urls:
        success, content = try_download(url)
        if not success:
            continue

        logger.info(f"  ✓ Downloaded from: {url} ({len(content):,} bytes)")

        # Save temp file
        temp = dest_dir / f"{ticker}__{year}__temp.pdf"
        temp.write_bytes(content)

        # Validate
        valid, msg, lang, pages = validate_pdf(temp, ticker, year)
        if valid:
            final = dest_dir / f"{ticker}__{year}__annual_report__{lang}.pdf"
            temp.rename(final)
            logger.info(f"  ✓ VALIDATED: {final.name} ({pages}p, {msg})")

            # Update manifest
            sha256 = hashlib.sha256(content).hexdigest()
            entry = {
                "company_id": ticker.lower(),
                "canonical_ticker": ticker,
                "company_name": COMPANY_INFO[ticker]["name"],
                "document_type": "annual_report",
                "year": year,
                "language": lang,
                "source_url": url,
                "local_path": str(final),
                "sha256": sha256,
                "page_count": pages,
                "file_size": len(content),
                "status": "verified",
            }
            with open(MANIFEST_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            return "downloaded"
        else:
            logger.info(f"  ✗ Validation failed: {msg}")
            temp.unlink(missing_ok=True)

    return "not_found"


def main():
    tickers = list(COMPANY_INFO.keys())
    if "--tickers" in sys.argv:
        idx = sys.argv.index("--tickers")
        tickers = [t for t in sys.argv[idx + 1 :] if not t.startswith("-")]

    years = [2023, 2024, 2025]
    results = {"downloaded": [], "exists": [], "not_found": []}

    for ticker in tickers:
        for year in years:
            logger.info(f"\n{'=' * 50}")
            logger.info(f"Processing: {ticker} {year}")
            logger.info(f"{'=' * 50}")

            status = process(ticker, year)
            results[status].append(f"{ticker} {year}")
            time.sleep(0.5)

    # Summary
    logger.info(f"\n{'=' * 60}")
    logger.info("SUMMARY")
    logger.info(f"{'=' * 60}")
    logger.info(f"Downloaded:   {len(results['downloaded'])}")
    logger.info(f"Existing:     {len(results['exists'])}")
    logger.info(f"Not found:    {len(results['not_found'])}")

    if results["downloaded"]:
        logger.info("\n✓ Downloaded:")
        for r in results["downloaded"]:
            logger.info(f"  {r}")

    if results["not_found"]:
        logger.info("\n✗ Still missing:")
        for r in results["not_found"]:
            logger.info(f"  {r}")


if __name__ == "__main__":
    main()
