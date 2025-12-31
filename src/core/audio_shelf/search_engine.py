
import requests
import re
from typing import List, Optional
from bs4 import BeautifulSoup

def search_duckduckgo_audible(query: str, limit: int = 3) -> List[str]:
    """
    Searches DuckDuckGo HTML for 'site:audible.com <query>' and returns a list of Audible product URLs.
    """
    url = "https://html.duckduckgo.com/html/"
    headers = {
         "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }
    
    # We want to find the audiobook on audible.com
    search_term = f"{query} site:audible.com"
    data = {"q": search_term}
    
    found_urls = []
    
    try:
        r = requests.post(url, data=data, headers=headers, timeout=10)
        if r.status_code != 200:
            return []
            
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Parse results
        # DDG HTML results usually have class 'result__a' for title links
        for a in soup.select(".result__a"):
            if len(found_urls) >= limit:
                break
                
            href = a.get("href", "")
            
            # Filter for actual audible product pages
            # standard patterns: /pd/..., /dp/...
            if "audible.com/pd/" in href or "audible.com/dp/" in href:
                # Sometimes DDG wraps links, but usually html version is direct or close enough
                # Let's clean it just in case
                if href.startswith("//duckduckgo.com/l/?"):
                    # It's a redirect link, try to extract 'uddg' param if possible or just skip
                    # Parsing query params is safer
                    pass 
                
                found_urls.append(href)
                
    except Exception:
        pass
        
    return found_urls

def extract_asin_from_url(url: str) -> Optional[str]:
    """
    Extracts ASIN (B0...) from an Audible URL.
    """
    # Pattern 1: /pd/Title-Audiobook/B0XXXXXX
    m = re.search(r"/pd/[^/]+/([A-Z0-9]{10})", url)
    if m: return m.group(1)
    
    # Pattern 2: /dp/B0XXXXXX
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    if m: return m.group(1)
    
    # Pattern 3: Generic /ASIN
    m = re.search(r"/([A-Z0-9]{10})(?:[/?#]|$)", url)
    if m: return m.group(1)
    
    return None
