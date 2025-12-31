
import requests
from src.core.audio_shelf.tagger import (
    make_session, 
    BookQuery, 
    provider_audible_scrape,
    provider_audnexus_by_asin,
    search_duckduckgo_audible,
    extract_asin_from_url
)

def test_hybrid_flow():
    session = make_session()
    
    # Test Case: "Project Hail Mary" by Andy Weir
    # This is a good test because it has a clear ASIN B08G9PRS1K
    q = BookQuery(title="Project Hail Mary", author="Andy Weir")
    
    print(f"--- Testing Hybrid Flow for: {q.title} ---")
    
    # 1. Test DDG Search
    print("\n[1] Testing DuckDuckGo Search...")
    urls = search_duckduckgo_audible(f"{q.title} {q.author}")
    print(f"Found {len(urls)} URLs: {urls}")
    
    if not urls:
        print("FAIL: No URLs found via DDG (Continuing with hardcoded URL...)")
        # return

    first_url = "https://www.audible.com/pd/Project-Hail-Mary-Audiobook/B08G9PRS1K" 
    if urls:
        first_url = urls[0]
    print(f"Using URL: {first_url}")
    
    # 2. Test ASIN Extraction
    asin = extract_asin_from_url(first_url)
    print(f"Extracted ASIN: {asin}")
    
    if asin:
        # 3. Test Audnexus via ASIN
        print("\n[2] Testing Audnexus (via ASIN)...")
        meta = provider_audnexus_by_asin(session, asin)
        if meta:
            print("SUCCESS: Retrieved Metadata via Audnexus")
            print(f"Title: {meta.title}")
            print(f"Author: {meta.authors}")
            print(f"Genres: {meta.genres}")
        else:
            print("FAIL: Audnexus returned None")
            
    # 4. Test Direct Scraping (Fallback)
    print("\n[3] Testing Direct Scraping (Fallback)...")
    meta_scrape = provider_audible_scrape(session, first_url)
    if meta_scrape:
        print("SUCCESS: Retrieved Metadata via Direct Scrape")
        print(f"Title: {meta_scrape.title}")
        print(f"Author: {meta_scrape.authors}")
        print(f"Genres: {meta_scrape.genres}")
        print(f"Description sample: {meta_scrape.description[:50]}...")
    else:
        print("FAIL: Direct Scraping returned None")

if __name__ == "__main__":
    test_hybrid_flow()
