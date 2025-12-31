
import requests
from bs4 import BeautifulSoup
import json
import re

def debug_scrape(url):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    })
    
    print(f"Fetching: {url}")
    r = session.get(url)
    print(f"Status: {r.status_code}")
    
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Check H1
    h1 = soup.select_one("h1[slot='title']")
    print(f"H1 (slot=title): {h1}")
    if not h1:
        h1 = soup.select_one("h1.bc-heading")
        print(f"H1 (bc-heading): {h1}")
        
    # Check JSON
    json_script = soup.select_one("adbl-product-metadata script[type='application/json']")
    print(f"JSON Script found: {bool(json_script)}")
    if json_script:
        print(f"JSON Content: {json_script.get_text()[:100]}...")

    # Check Description
    desc = soup.select_one("div[class*='productDescription']")
    print(f"Desc Div: {bool(desc)}")

if __name__ == "__main__":
    debug_scrape("https://www.audible.com/pd/Project-Hail-Mary-Audiobook/B08G9PRS1K")
