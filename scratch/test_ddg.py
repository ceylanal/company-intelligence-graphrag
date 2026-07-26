#!/usr/bin/env python3
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

url = "https://html.duckduckgo.com/html/"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
data = {"q": "site:akbankinvestorrelations.com filetype:pdf faaliyet raporu"}

resp = requests.post(url, data=data, headers=headers, timeout=10)
print("Status:", resp.status_code)
soup = BeautifulSoup(resp.text, "html.parser")
links = []
for a in soup.find_all("a", class_="result__url"):
    href = a.get("href", "")
    if "uddg=" in href:
        parsed = parse_qs(urlparse(href).query)
        actual_url = parsed.get("uddg", [""])[0]
        links.append(actual_url)
    else:
        links.append(href)

print("Found links:")
for l in links:
    print(" -", l)
