#!/usr/bin/env python3

import requests

url = "https://www.kap.org.tr/tr/api/disclosures"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
}

# Search KAP for recent disclosures
try:
    resp = requests.get("https://www.kap.org.tr/tr/api/disclosures", headers=headers, timeout=5)
    print("GET status:", resp.status_code)
    if resp.status_code == 200:
        data = resp.json()
        print("Data count:", len(data))
        if data:
            print("First item keys:", data[0].keys())
except Exception as e:
    print("GET error:", e)
