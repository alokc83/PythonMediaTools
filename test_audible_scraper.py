#!/usr/bin/env python3
"""Test Audible scraper to verify rating extraction"""

import sys
sys.path.insert(0, '/Users/alok/Documents/github/alokc83/PythonMediaTools')

from src.core.audio_shelf.tagger import provider_audible_scrape, make_session

# Test URL
url = "https://www.audible.com/pd/How-to-Speak-Money-Audiobook/B00MTZBJHC"

print(f"Testing Audible scraper on: {url}\n")

session = make_session()
meta = provider_audible_scrape(session, url)

if meta:
    print("✅ Scraper returned metadata:")
    print(f"  Title: {meta.title}")
    print(f"  Authors: {meta.authors}")
    print(f"  Rating: {meta.rating}")
    print(f"  Rating Count: {meta.rating_count}")
    print(f"  Source: {meta.source}")
else:
    print("❌ Scraper returned None")
