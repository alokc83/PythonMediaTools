#!/usr/bin/env python3
"""Debug Audible page HTML to find rating selectors"""

import sys
sys.path.insert(0, '/Users/alok/Documents/github/alokc83/PythonMediaTools')

import requests
from bs4 import BeautifulSoup
from src.core.audio_shelf.tagger import make_session

url = "https://www.audible.com/pd/How-to-Speak-Money-Audiobook/B00MTZBJHC"

print(f"Fetching: {url}\n")

session = make_session()
r = session.get(url, timeout=10)

if r.status_code == 200:
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Check for JSON script
    json_script = soup.select_one("adbl-product-metadata script[type='application/json']")
    if json_script:
        print("✅ Found JSON script")
        import json
        try:
            data = json.loads(json_script.get_text())
            agg_rating = data.get("aggregateRating", {})
            print(f"  aggregateRating: {agg_rating}")
        except Exception as e:
            print(f"  Error parsing: {e}")
    else:
        print("❌ No JSON script found")
    
    print("\n" + "="*60)
    print("Looking for rating in HTML spans...")
    print("="*60)
    
    # Try different selectors
    spans = soup.select("span")
    print(f"\nTotal spans found: {len(spans)}")
    
    # Show first 20 spans with text containing numbers or "rating"
    count = 0
    for span in spans:
        text = span.get_text().strip()
        if text and (any(char.isdigit() for char in text) or "rating" in text.lower()):
            classes = span.get("class", [])
            print(f"\n  Classes: {classes}")
            print(f"  Text: {text[:100]}")
            count += 1
            if count >= 15:
                break
else:
    print(f"❌ Failed to fetch page: {r.status_code}")
