#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

# Test Google search for AKBNK 2024 annual report PDF
q = 'site:akbankinvestorrelations.com filetype:pdf "faaliyet raporu" 2024'
url = f"https://www.google.com/search?q={requests.utils.quote(q)}"

try:
    resp = requests.get(url, headers=headers, timeout=5)
    print("Google status:", resp.status_code)
    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/url?q=" in href:
            actual = href.split("/url?q=")[1].split("&")[0]
            if ".pdf" in actual.lower():
                print("  Google PDF URL:", actual)
except Exception as e:
    print("Google error:", e)

# Test Bing search
url_bing = f"https://www.bing.com/search?q={requests.utils.quote(q)}"
try:
    resp = requests.get(url_bing, headers=headers, timeout=5)
    print("Bing status:", resp.status_code)
    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower():
            print("  Bing PDF URL:", href)
except Exception as e:
    print("Bing error:", e)
