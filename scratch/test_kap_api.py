#!/usr/bin/env python3
import json

import requests

url = "https://www.kap.org.tr/tr/api/disclosures"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
}

# Test querying for AKBNK disclosures in 2024
payload = {"fromDate": "2024-01-01", "toDate": "2024-12-31", "subject": "Faaliyet Raporu"}

try:
    r = requests.post(url, json=payload, headers=headers, timeout=10)
    print("Status:", r.status_code)
    print("Response len:", len(r.text))
    if r.status_code == 200:
        data = r.json()
        print("Count:", len(data))
        if data:
            print("Sample item:", json.dumps(data[0], indent=2, ensure_ascii=False)[:500])
except Exception as e:
    print("Error:", e)
