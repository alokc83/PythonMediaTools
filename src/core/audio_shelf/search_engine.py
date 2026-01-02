
import requests
import re
from typing import List, Optional, Dict, Any
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

    return None

def search_goodreads_direct(query: str, limit: int = 3) -> List[str]:
    """
    Searches Goodreads directly via /search?q=...
    Scrapes the results page for book links.
    """
    
    # Clean query for URL
    import urllib.parse
    q_enc = urllib.parse.quote(query)
    url = f"https://www.goodreads.com/search?q={q_enc}"
    
    headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }
    
    exclusions = ["summary of", "workbook", "study guide", "analysis of", "notes on", "key takeaways"]
    query_lower = query.lower()
    
    found_urls = []
    
    try:
            print(f"DEBUG: Querying Goodreads Direct: {url}")
            r = requests.get(url, headers=headers, timeout=10)
            
            if r.status_code != 200:
                 print(f"DEBUG: Goodreads Search Status: {r.status_code}")
                 return []
                 
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Goodreads search results usually have class "bookTitle"
            # <a class="bookTitle" itemprop="url" href="/book/show/...">
            
            count = 0
            for a in soup.select("a.bookTitle"):
                if count >= limit: break
                
                href = a.get("href", "")
                title_text = a.get_text().strip().lower()
                
                # Filter spam/summaries
                is_spam = False
                for exc in exclusions:
                    if exc in title_text and exc not in query_lower:
                        is_spam = True
                        print(f"DEBUG: Skipped spam/summary result: '{title_text}'")
                        break
                if is_spam: continue
                
                if href:
                    # Often relative path
                    if href.startswith("/"):
                        href = f"https://www.goodreads.com{href}"
                        
                    # Clean off query params if needed
                    if "?" in href:
                        href = href.split("?")[0]
                        
                    print(f"DEBUG: Found GR Book: {href}")
                    found_urls.append(href)
                    count += 1
                
    except Exception as e:
        print(f"DEBUG: GR Search Error: {e}")
        pass
        
    return found_urls

def scrape_goodreads_rating(session, url: str):
    """
    Scrapes Goodreads URL for JSON-LD data to get Rating and Count.
    Returns dict: {'rating': float, 'count': int} or None
    """
    try:
        headers = {
             "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
        }
        r = session.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
            
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Look for JSON-LD
        scripts = soup.find_all("script", type="application/ld+json")
        for s in scripts:
            try:
                data = json.loads(s.string)
                # Goodreads often puts Book data in the main object
                # Strategy: Search recursively for 'AggregateRating' type or key
                agg = None
                
                # Direct check
                if data.get("@type") == "Book":
                    agg = data.get("aggregateRating")
                    
                # If not found, check deeper (sometimes graph structure)
                if not agg and "@graph" in data:
                    for node in data["@graph"]:
                        if node.get("@type") == "Book":
                            agg = node.get("aggregateRating")
                            break
                            
                if agg:
                    rating = float(agg.get("ratingValue", 0))
                    count = int(agg.get("ratingCount", 0))
                    if count == 0:
                        count = int(agg.get("reviewCount", 0))
                        
                    if rating > 0:
                         return {"rating": rating, "count": count}
            except:
                continue
                
        # If JSON-LD fails, try meta tags (Standard Schema.org)
        rating_node = soup.find("meta", property="books:rating:value") # OpenGraph style
        if not rating_node: rating_node = soup.find("meta", itemprop="ratingValue")
        
        count_node = soup.find("meta", property="books:rating:count")
        if not count_node: count_node = soup.find("meta", itemprop="ratingCount")
        
        if rating_node and count_node:
             return {
                 "rating": float(rating_node["content"]),
                 "count": int(count_node["content"])
             }

        # Fallback 3: Scrape Visible HTML (Class names often change, but effective as last resort)
        # Rating: <div class="RatingStatistics__rating">4.58</div>
        # Count: <span data-testid="ratingsCount">1,234 ratings</span>
        try:
            html_rating = soup.select_one("div.RatingStatistics__rating")
            html_count = soup.select_one('[data-testid="ratingsCount"]')
            
            if html_rating and html_count:
                r_val = float(html_rating.get_text().strip())
                c_val = int(html_count.get_text().strip().split()[0].replace(",", ""))
                return {"rating": r_val, "count": c_val}
        except:
            pass

    except Exception:
        pass
        
    return None

def search_duckduckgo_amazon(query: str, limit: int = 3) -> List[str]:
    """
    Searches DuckDuckGo HTML for 'site:amazon.com <query>' and returns urls.
    """
    url = "https://html.duckduckgo.com/html/"
    headers = {
         "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }
    
    # Restrict to books for better relevance
    search_term = f"{query} site:amazon.com/dp/ OR site:amazon.com/Harry-Potter" # generic site:amazon.com often hits noise
    search_term = f"{query} site:amazon.com"
    data = {"q": search_term}
    
    found_urls = []
    
    try:
        print(f"DEBUG: Searching DDG for Amazon: {search_term}")
        r = requests.post(url, data=data, headers=headers, timeout=10)
        
        soup = BeautifulSoup(r.text, "html.parser")
        
        for a in soup.select(".result__a"):
            if len(found_urls) >= limit: break
            
            href = a.get("href", "")
            # Look for product pages: /dp/ or /gp/product/
            if "/dp/" in href or "/gp/product/" in href:
                # Clean URL
                if "http" in href:
                     # Remove query params
                     if "?" in href: href = href.split("?")[0]
                     found_urls.append(href)
                     
    except Exception as e:
        print(f"Amazon Search Error: {e}")
        
    return found_urls

def scrape_amazon_rating(session, url: str) -> Optional[Dict[str, Any]]:
    """
    Scrapes Amazon product page for rating and review count.
    Strategies:
    1. #acrPopover (The star rating trigger) -> title attribute "4.8 out of 5 stars"
    2. #acrCustomerReviewText -> "12,943 ratings"
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        print(f"DEBUG: Scrape Amazon URL: {url}")
        r = session.get(url, headers=headers, timeout=10)
        
        if r.status_code != 200:
            print(f"DEBUG: Amazon Status Code: {r.status_code}")
            return None
            
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 1. Extract Rating
        rating = 0.0
        # Try finding the "X out of 5 stars" text
        # Usually in <span id="acrPopover" title="4.8 out of 5 stars">
        # Or <i class="a-icon a-icon-star a-star-4-5"><span class="a-icon-alt">4.6 out of 5 stars</span></i>
        
        rating_node = soup.select_one("#acrPopover")
        rating_text = ""
        if rating_node:
            rating_text = rating_node.get("title", "")
        
        if not rating_text:
             # Try fallback selector
             alt_node = soup.select_one(".a-icon-star .a-icon-alt")
             if alt_node: rating_text = alt_node.get_text()
             
        # Parse "4.8 out of 5 stars"
        if "out of 5 stars" in rating_text:
            try:
                rating = float(rating_text.split("out")[0].strip())
            except: pass
            
        # 2. Extract Count
        count = 0
        # <span id="acrCustomerReviewText">12,345 ratings</span>
        count_node = soup.select_one("#acrCustomerReviewText")
        if count_node:
            text = count_node.get_text().strip() # "12,345 ratings"
            try:
                # Remove commas, split
                num_str = text.split()[0].replace(",", "").replace(".", "") # European?
                count = int(num_str)
            except: pass
            
        if rating > 0 and count > 0:
            return {"rating": rating, "count": count}
            
    except Exception as e:
        print(f"Amazon Scrape Error: {e}")
        
    return None
