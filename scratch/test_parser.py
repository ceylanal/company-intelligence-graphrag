#!/usr/bin/env python3
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

q = 'Arçelik "faaliyet raporu" 2024 pdf'

# Bing
r_bing = requests.get(
    f"https://www.bing.com/search?q={requests.utils.quote(q)}", headers=headers, timeout=5
)
print("Bing status:", r_bing.status_code)
soup_b = BeautifulSoup(r_bing.text, "html.parser")
for a in soup_b.find_all("a", href=True):
    href = a["href"]
    if ".pdf" in href.lower() or "pdf" in href.lower():
        print("  Bing:", href)

# DuckDuckGo GET
r_ddg = requests.get(
    f"https://html.duckduckgo.com/html/?q={requests.utils.quote(q)}", headers=headers, timeout=5
)
print("DDG GET status:", r_ddg.status_code)
soup_d = BeautifulSoup(r_ddg.text, "html.parser")
for a in soup_d.find_all("a", href=True):
    href = a.get("href", "")
    if "uddg=" in href:
        actual = parse_qs(urlparse(href).query).get("uddg", [""])[0]
        if ".pdf" in actual.lower():
            print("  DDG:", actual)
    elif ".pdf" in href.lower():
        print("  DDG:", href)
