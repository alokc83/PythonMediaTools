import requests
from bs4 import BeautifulSoup
import re

def search_ddg(query):
    # Using html.duckduckgo.com to avoid JS heavy page
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }
    data = {"q": query + " site:audible.com"}
    
    try:
        print(f"Searching DDG for: {data['q']}")
        r = requests.post(url, data=data, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"Failed: {r.status_code}")
            return []
            
        soup = BeautifulSoup(r.text, "html.parser")
        links = []
        for a in soup.select(".result__a"):
            href = a.get("href")
            # DDG result links are wrapped in /l/?kh=-1&uddg=...
            # But the html version might be simpler or redirect.
            # Actually html DDG returns direct links or slightly wrapped.
            # Let's extract the actual URL.
            print(f"Found link: {href}")
            links.append(href)
        return links
    except Exception as e:
        print(f"Error: {e}")
        return []

def extract_asin(url):
    # Match /pd/ASIN or /dp/ASIN
    # B0... 10 chars
    m = re.search(r"/(?:pd|dp|freqs)/([A-Z0-9]{10})", url)
    if m: return m.group(1)
    
    # Sometimes it's just /ASIN ending
    m = re.search(r"/([A-Z0-9]{10})(?:[/?#]|$)", url)
    if m: return m.group(1)
    return None

if __name__ == "__main__":
    # Test with a known book
    q = "Project Hail Mary Andy Weir"
    links = search_ddg(q)
    found = set()
    for l in links:
        asin = extract_asin(l)
        if asin and asin.startswith("B"): # Audiobooks usually B...
            found.add(asin)
    
    print("Found ASINs:", found)
