#!/usr/bin/env python3

import requests
import urllib3

urllib3.disable_warnings()

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

patterns = {
    "AKBNK": [
        "https://www.akbankinvestorrelations.com/tr/images/pdf/akbank-{year}-entegre-faaliyet-raporu.pdf",
    ],
    "ARCLK": [
        "https://www.arcelikglobal.com/media/faaliyet-raporlari/arcelik-{year}-faaliyet-raporu.pdf",
        "https://www.arcelikglobal.com/media/reports/arcelik-{year}-annual-report.pdf",
        "https://www.arcelikglobal.com/media/arcelik-{year}-faaliyet-raporu.pdf",
        "https://www.arcelikglobal.com/media/arcelik-{year}-entegre-faaliyet-raporu.pdf",
    ],
    "ASELS": [
        "https://www.aselsan.com.tr/assets/uploads/faaliyet-raporlari/aselsan-{year}-faaliyet-raporu.pdf",
        "https://www.aselsan.com.tr/assets/uploads/faaliyet-raporlari/ASELSAN_{year}_Faaliyet_Raporu.pdf",
        "https://www.aselsan.com.tr/ASELSAN_{year}_FAALIYET_RAPORU.pdf",
        "https://www.aselsan.com/assets/uploads/faaliyet-raporlari/aselsan-{year}-faaliyet-raporu.pdf",
    ],
    "FROTO": [
        "https://www.fordotosan.com.tr/assets/uploads/raporlar/ford-otosan-{year}-entegre-faaliyet-raporu.pdf",
        "https://www.fordotosan.com.tr/assets/uploads/raporlar/Ford-Otosan-{year}-Entegre-Faaliyet-Raporu.pdf",
        "https://www.fordotosan.com.tr/assets/uploads/raporlar/ford-otosan-{year}-faaliyet-raporu.pdf",
        "https://www.fordotosan.com.tr/assets/uploads/raporlar/Ford_Otosan_{year}_Faaliyet_Raporu.pdf",
    ],
    "KCHOL": [
        "https://www.koc.com.tr/yatirimci-iliskileri/raporlar/faaliyet-raporlari/koc-holding-{year}-faaliyet-raporu.pdf",
        "https://www.koc.com.tr/content/koc-holding-{year}-faaliyet-raporu.pdf",
        "https://www.koc.com.tr/media/koc-holding-{year}-faaliyet-raporu.pdf",
    ],
    "MGROS": [
        "https://migroskurumsalstr.blob.core.windows.net/migroskurumsalstr/-migros-tr{year}-interaktif-639088646656876356.pdf",
        "https://migroskurumsalstr.blob.core.windows.net/migroskurumsalstr/migros-{year}-entegre-faaliyet-raporu.pdf",
        "https://migroskurumsalstr.blob.core.windows.net/migroskurumsalstr/migros-tr{year}-interaktif.pdf",
    ],
    "SISE": [
        "https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/Sisecam-{year}-Faaliyet-Raporu.pdf",
        "https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/sisecam-{year}-faaliyet-raporu.pdf",
        "https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/sisecam-entegre-faaliyet-raporu-{year}.pdf",
    ],
    "TCELL": [
        "https://www.turkcell.com.tr/hakkimizda/yatirimci-iliskileri/pdf/turkcell-{year}-entegre-faaliyet-raporu.pdf",
        "https://www.turkcell.com.tr/hakkimizda/yatirimci-iliskileri/pdf/Turkcell-{year}-Faaliyet-Raporu.pdf",
    ],
    "THYAO": [
        "https://investor.turkishairlines.com/documents/ThyInvestorRelations/{year}-faaliyet-raporu.pdf",
        "https://investor.turkishairlines.com/documents/ThyInvestorRelations/THY-{year}-Faaliyet-Raporu.pdf",
        "https://investor.turkishairlines.com/documents/ThyInvestorRelations/thy-{year}-yillik-rapor.pdf",
    ],
    "TUPRS": [
        "https://www.tupras.com.tr/media/2513/tupras-2023-entegre-faaliyet-raporu.pdf",
        "https://www.tupras.com.tr/assets/uploads/entegre-faaliyet/tupras-{year}-entegre-faaliyet-raporu.pdf",
    ],
}

years = [2023, 2024, 2025]

for ticker, pat_list in patterns.items():
    print(f"\n--- {ticker} ---")
    for y in years:
        found = False
        for pat in pat_list:
            url = pat.format(year=y)
            try:
                r = requests.head(url, headers=headers, verify=False, timeout=4)
                if r.status_code == 200:
                    print(f"  ✓ {y}: {url} (HEAD 200)")
                    found = True
                    break
                else:
                    # try GET stream
                    r2 = requests.get(url, headers=headers, verify=False, timeout=4, stream=True)
                    if r2.status_code == 200 and r2.content[:5] == b"%PDF-":
                        print(f"  ✓ {y}: {url} (GET 200 PDF)")
                        found = True
                        break
            except Exception:
                pass
        if not found:
            print(f"  ✗ {y}: Not found in patterns")
