#!/usr/bin/env python3
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

targets = [
    ("ARCLK", "arcelikglobal.com"),
    ("ASELS", "aselsan.com.tr"),
    ("FROTO", "fordotosan.com.tr"),
    ("KCHOL", "koc.com.tr"),
    ("MGROS", "migroskurumsal.com"),
    ("SISE", "sisecam.com.tr"),
    ("TCELL", "turkcell.com.tr"),
    ("THYAO", "turkishairlines.com"),
    ("TUPRS", "tupras.com.tr"),
]

for ticker, domain in targets:
    print(f"\n==================== {ticker} ({domain}) ====================")
    queries = [
        f"site:{domain} filetype:pdf faaliyet",
        f"site:{domain} filetype:pdf annual",
        f"site:{domain} filetype:pdf entegre",
        f"site:{domain} faaliyet raporu pdf",
    ]
    found_urls = set()
    for q in queries:
        try:
            r = requests.post(
                "https://html.duckduckgo.com/html/", data={"q": q}, headers=headers, timeout=6
            )
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", class_="result__url"):
                    href = a.get("href", "")
                    if "uddg=" in href:
                        actual = parse_qs(urlparse(href).query).get("uddg", [""])[0]
                    else:
                        actual = href

                    if actual and actual not in found_urls:
                        found_urls.add(actual)
                        if ".pdf" in actual.lower() or "pdf" in actual.lower():
                            print("  PDF Link:", actual)
        except Exception as e:
            print(f"  Error for query '{q}': {e}")
