#!/usr/bin/env python3

import requests
import urllib3

urllib3.disable_warnings()

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

candidates = {
    ("ARCLK", 2025): [
        "https://www.arcelikglobal.com/media/7535/arcelik_tr25.pdf",
        "https://www.arcelikglobal.com/media/7535/arcelik_tr2025.pdf",
        "https://www.arcelikglobal.com/media/faaliyet-raporlari/arcelik-2025-faaliyet-raporu.pdf",
        "https://companiesmarketcap.com/annual-reports/63605.ar.en.2025.pdf",
    ],
    ("ASELS", 2025): [
        "https://wwwcdn.aselsan.com/api/file/2025YiliFaaliyetRaporu.pdf",
        "https://wwwcdn.aselsan.com/api/file/2025_Faaliyet_Raporu.pdf",
        "https://www.aselsan.com.tr/assets/uploads/faaliyet-raporlari/aselsan-2025-faaliyet-raporu.pdf",
        "https://www.aselsan.com.tr/assets/uploads/faaliyet-raporlari/ASELSAN_2025_Faaliyet_Raporu.pdf",
    ],
    ("FROTO", 2025): [
        "https://companiesmarketcap.com/annual-reports/63930.ar.tr.2025.pdf",
        "https://www.fordotosan.com.tr/assets/uploads/raporlar/Ford-Otosan-2025-Entegre-Faaliyet-Raporu.pdf",
        "https://www.fordotosan.com.tr/assets/uploads/raporlar/ford-otosan-2025-faaliyet-raporu.pdf",
    ],
    ("KCHOL", 2023): [
        "https://cdn.koc.com.tr/cmscontainer/kocholding/media/koc/03yatirimci-iliskileri/koc_holding_2023_faaliyet_raporu.pdf",
        "https://cdn.koc.com.tr/cmscontainer/kocholding/media/koc/03yatirimci-iliskileri/koc-holding-2023-faaliyet-raporu.pdf",
        "https://www.koc.com.tr/content/koc-holding-2023-faaliyet-raporu.pdf",
        "https://companiesmarketcap.com/annual-reports/16500.ar.tr.2023.pdf",
    ],
    ("KCHOL", 2025): [
        "https://cdn.koc.com.tr/cmscontainer/kocholding/media/koc/03yatirimci-iliskileri/koc_holding_2025_faaliyet_raporu.pdf",
        "https://cdn.koc.com.tr/cmscontainer/kocholding/media/koc/03yatirimci-iliskileri/koc-holding-2025-faaliyet-raporu.pdf",
        "https://www.koc.com.tr/content/koc-holding-2025-faaliyet-raporu.pdf",
        "https://companiesmarketcap.com/annual-reports/16500.ar.tr.2025.pdf",
    ],
    ("SISE", 2023): [
        "https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/Sisecam-2023-Faaliyet-Raporu.pdf",
        "https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/sisecam-2023-faaliyet-raporu.pdf",
        "https://companiesmarketcap.com/annual-reports/13202.ar.tr.2023.pdf",
        "https://companiesmarketcap.com/annual-reports/13202.ar.en.2023.pdf",
    ],
    ("SISE", 2025): [
        "https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/Sisecam-2025-Faaliyet-Raporu.pdf",
        "https://www.sisecam.com.tr/sites/catalogs/tr/Documents/faaliyet-raporlari/sisecam-2025-faaliyet-raporu.pdf",
        "https://companiesmarketcap.com/annual-reports/13202.ar.tr.2025.pdf",
        "https://companiesmarketcap.com/annual-reports/13202.ar.en.2025.pdf",
    ],
    ("TCELL", 2024): [
        "https://companiesmarketcap.com/annual-reports/6818.ar.tr.2024.pdf",
        "https://companiesmarketcap.com/annual-reports/6818.ar.en.2024.pdf",
        "https://www.turkcell.com.tr/hakkimizda/yatirimci-iliskileri/pdf/turkcell-2024-entegre-faaliyet-raporu.pdf",
    ],
    ("TCELL", 2025): [
        "https://companiesmarketcap.com/annual-reports/6818.ar.tr.2025.pdf",
        "https://companiesmarketcap.com/annual-reports/6818.ar.en.2025.pdf",
        "https://www.turkcell.com.tr/hakkimizda/yatirimci-iliskileri/pdf/turkcell-2025-entegre-faaliyet-raporu.pdf",
    ],
    ("THYAO", 2025): [
        "https://companiesmarketcap.com/annual-reports/13203.ar.tr.2025.pdf",
        "https://companiesmarketcap.com/annual-reports/13203.ar.en.2025.pdf",
        "https://investor.turkishairlines.com/documents/ThyInvestorRelations/2025-faaliyet-raporu.pdf",
    ],
}

print("PROBING CANDIDATE URLS FOR REMAINING 10 SLOTS")
for (ticker, year), url_list in candidates.items():
    print(f"\n--- {ticker} {year} ---")
    for url in url_list:
        try:
            r = requests.get(url, headers=headers, verify=False, timeout=5, stream=True)
            if r.status_code == 200 and r.content[:5] == b"%PDF-":
                print(f"  ✓ FOUND: {url} (len={len(r.content)})")
            else:
                print(f"  ✗ HTTP {r.status_code}: {url}")
        except Exception as e:
            print(f"  ✗ Error: {e} for {url}")
