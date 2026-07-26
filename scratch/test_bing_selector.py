#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

q = 'site:arcelikglobal.com filetype:pdf "faaliyet"'
url = f"https://www.bing.com/search?q={requests.utils.quote(q)}"

r = requests.get(url, headers=headers, timeout=5)
print("Bing Status:", r.status_code)
soup = BeautifulSoup(r.text, "html.parser")

for li in soup.find_all("li", class_="b_algo"):
    a = li.find("a", href=True)
    if a:
        print("  Bing Result:", a["href"])
