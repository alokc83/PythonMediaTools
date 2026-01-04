#!/usr/bin/env python3
"""Look for rating in all possible locations"""

import sys
sys.path.insert(0, '/Users/alok/Documents/github/alokc83/PythonMediaTools')

import requests
from bs4 import BeautifulSoup
from src.core.audio_shelf.tagger import make_session
import re

url = "https://www.audible.com/pd/How-to-Speak-Money-Audiobook/B00MTZBJHC"

session = make_session()
r = session.get(url, timeout=10)

if r.status_code == 200:
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Search for any text containing rating patterns
    print("Searching page text for rating patterns...")
    print("="*60)
    
    # Look for "3.8 out of 5" or "3.8" followed by "stars" or "ratings"
   
    all_text = soup.get_text()
    
    # Pattern 1: X.X out of 5
    matches = re.findall(r'(\d\.\d+)\s*out of\s*5', all_text, re.IGNORECASE)
    if matches:
        print(f"✅ Found 'X out of 5' pattern: {matches}")
    
    # Pattern 2: X.X stars
    matches = re.findall(r'(\d\.\d+)\s*stars?', all_text, re.IGNORECASE)
    if matches:
        print(f"✅ Found 'X stars' pattern: {matches}")
    
    # Pattern 3: Numbers followed by "ratings" or "reviews"
    matches = re.findall(r'([\d,]+)\s*(ratings?|reviews?)', all_text, re.IGNORECASE)
    if matches:
        print(f"✅ Found rating count patterns: {matches[:5]}")
    
    # Check meta tags
    print("\n" + "="*60)
    print("Checking meta tags...")
    print("="*60)
    
    for meta in soup.find_all("meta"):
        content = meta.get("content", "")
        if content and (re.search(r'\d\.\d', content) or "rating" in content.lower()):
            print(f"  {meta.get('name') or meta.get('property')}: {content[:100]}")
    
    # Check for any element with "rating" in class or id
    print("\n" + "="*60)
    print("Elements with 'rating' in class/id...")
    print("="*60)
    
    for elem in soup.find_all(class_=re.compile("rating", re.I)):
        print(f"  Tag: {elem.name}, Class: {elem.get('class')}, Text: {elem.get_text().strip()[:100]}")
    
    for elem in soup.find_all(id=re.compile("rating", re.I)):
        print(f"  Tag: {elem.name}, ID: {elem.get('id')}, Text: {elem.get_text().strip()[:100]}")

else:
    print(f"Failed: {r.status_code}")
