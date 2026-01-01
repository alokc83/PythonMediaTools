
import os
import re
import requests
import json
import time
import difflib
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from bs4 import BeautifulSoup

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TDRC, TCON, COMM, APIC, TPUB, TLAN, TXXX, TIT1, TCMP, TRCK, TPOS
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus

# Import Search Engine
from .search_engine import search_duckduckgo_audible, extract_asin_from_url

@dataclass
class BookQuery:
    title: str
    author: str

@dataclass
class BookMeta:
    title: str = ""
    authors: List[str] = None
    subtitle: str = ""
    narrators: List[str] = None
    publisher: str = ""
    published_date: str = ""
    language: str = ""
    description: str = ""
    genres: List[str] = None
    tags: List[str] = None
    isbn10: str = ""
    isbn13: str = ""
    rating: str = ""
    rating_count: str = ""
    source: str = ""
    source_url: str = ""
    cover_url: str = ""
    asin: str = ""
    grouping: str = "" # Added for Series/Collection support

    def __post_init__(self):
        self.authors = self.authors or []
        self.narrators = self.narrators or []
        self.genres = self.genres or []
        self.tags = self.tags or []

def norm_space(s: str) -> str:
    s = s.replace("_", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def uniq_ci(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for v in values:
        vv = norm_space(str(v))
        if not vv: continue
        k = vv.lower()
        if k not in seen:
            seen.add(k)
            out.append(vv)
    return out

def shorten_description(s: str, limit: int = 900) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip()
    if len(s) <= limit: return s
    return s[:limit].rstrip() + "..."

def normalize_author(author: str) -> str:
    """Normalize author names for comparison: collapse spaces between initials."""
    # "George R. R. Martin" -> "George R.R. Martin"
    # Pattern: Letter + dot + space + Letter + dot -> Letter + dot + Letter + dot
    normalized = re.sub(r'([A-Z])\. ([A-Z])\.', r'\1.\2.', author)
    # Also handle single initial case: "R. Martin" stays "R. Martin"
    return normalized.strip()

def normalize_title(title: str) -> str:
    """Normalize title for comparison: remove subtitles, disc references, and bracketed content."""
    # Remove subtitle after colon: "Title: Subtitle" -> "Title"
    if ':' in title:
        title = title.split(':', 1)[0]
    # Remove subtitle after dash (with or without spaces): "Title - Subtitle" OR "Title- Subtitle" -> "Title"
    elif '-' in title:
        # Use regex to split on dash with optional surrounding spaces
        parts = re.split(r'\s*-\s*', title, 1)
        if len(parts) > 1:
            title = parts[0]
    
    # Remove ALL parenthetical content: "Title (Anything Here)" -> "Title"
    title = re.sub(r'\s*\([^)]*\)\s*', ' ', title)
    
    # Remove ALL square bracket content: "Title [Anything Here]" -> "Title"
    title = re.sub(r'\s*\[[^\]]*\]\s*', ' ', title)
    
    # Remove edition references universally: "Title, X Edition" -> "Title"
    # Matches ANY word(s) before "Edition" (e.g., Third, Revised, Special Anniversary, etc.)
    title = re.sub(r',?\s+[\w\s]+Edition\s*', '', title, flags=re.IGNORECASE)
    
    # Remove disc/disk references (with or without parentheses)
    # "Title Disc 1" OR "Title Disk 2" -> "Title"
    title = re.sub(r'\s*(?:Disc|Disk|CD)\s*\d+\s*', ' ', title, flags=re.IGNORECASE)
    
    # Remove leading articles: "The Title" -> "Title"
    title = re.sub(r'^(?:The|A|An)\s+', '', title, flags=re.IGNORECASE)
    
    # Normalize ordinal numbers: "5th" -> "fifth", "1st" -> "first"
    ordinal_map = {
        '1st': 'first', '2nd': 'second', '3rd': 'third', '4th': 'fourth', 
        '5th': 'fifth', '6th': 'sixth', '7th': 'seventh', '8th': 'eighth',
        '9th': 'ninth', '10th': 'tenth'
    }
    for ordinal, word in ordinal_map.items():
        title = re.sub(r'\b' + ordinal + r'\b', word, title, flags=re.IGNORECASE)
    
    # Clean up multiple spaces
    title = re.sub(r'\s+', ' ', title)
    
    return title.strip()

def calculate_confidence(query: BookQuery, meta: BookMeta) -> float:
    """Calculates confidence score (0.0 to 1.0) based on Title and Author match.
    Uses adaptive weighting: only scores fields that exist in the query."""
    if not query.title or not meta.title:
        return 0.0
    
    # Normalize titles before comparison (remove subtitles, brackets, etc.)
    query_title_norm = normalize_title(query.title).lower()
    found_title_norm = normalize_title(meta.title).lower()
    
    # Strip commas and normalize whitespace for comparison
    query_title_clean = re.sub(r'[,\s]+', ' ', query_title_norm).strip()
    found_title_clean = re.sub(r'[,\s]+', ' ', found_title_norm).strip()
    
    # Title Similarity
    # Strategy 1: Substring Matching (Direct)

    # Fuzzy Matching Helpers (Standard Library only)
    def fuzzy_ratio(s1, s2):
        return difflib.SequenceMatcher(None, s1, s2).ratio()
        
    def token_sort_ratio(s1, s2):
        """Sorts words alphabetically and compares. Handles 'Dan Brown' vs 'Brown, Dan'."""
        t1 = " ".join(sorted(s1.split()))
        t2 = " ".join(sorted(s2.split()))
        return fuzzy_ratio(t1, t2)
        
    def token_set_ratio(s1, s2):
        """
        Intersection of words. Handles 'Origin' vs 'Origin: A Novel'. 
        If intersection covers the shorter string, score is high.
        """
        set1 = set(s1.split())
        set2 = set(s2.split())
        intersection = set1.intersection(set2)
        if not intersection: return 0.0
        
        # Reconstruct intersection string (sorted for consistency)
        intersect_str = " ".join(sorted(list(intersection)))
        
        # Compare intersection with each original string (sorted)
        # This gives high score if one is a subset of the other
        t1 = " ".join(sorted(list(set1)))
        t2 = " ".join(sorted(list(set2)))
        
        score1 = fuzzy_ratio(intersect_str, t1)
        score2 = fuzzy_ratio(intersect_str, t2)
        
        return max(score1, score2)

    # Title Similarity
    # Strategy 1: Substring Matching (Direct)
    if found_title_clean in query_title_clean or query_title_clean in found_title_clean:
        title_sim = 1.0
    else:
        # Strategy 2: Split Matching (Handles "Series - Title" vs "Title")
        q_parts = re.split(r'\s*[-:]\s*', query_title_norm)
        f_parts = re.split(r'\s*[-:]\s*', found_title_norm)
        q_parts_clean = [re.sub(r'[,\s]+', ' ', p).strip() for p in q_parts]
        f_parts_clean = [re.sub(r'[,\s]+', ' ', p).strip() for p in f_parts]
        
        match_found = False
        for qp in q_parts_clean:
            if not qp: continue
            if qp == found_title_clean or qp in f_parts_clean:
                match_found = True; break
        
        if match_found:
             title_sim = 1.0
        else:
             # Strategy 3: Multi-Fuzzy Fallback
             base_score = fuzzy_ratio(query_title_clean, found_title_clean)
             sort_score = token_sort_ratio(query_title_clean, found_title_clean)
             set_score = token_set_ratio(query_title_clean, found_title_clean)
             
             # Take the BEST fuzzy match
             title_sim = max(base_score, sort_score, set_score)
    
    # Author Similarity (if available in query)
    author_sim = None
    if query.author and meta.authors:
        # Normalize both sides
        q_auth = normalize_author(query.author).lower()
        
        # Join multiple authors for comparison (handles "Author1, Author2" format)
        found_auth_joined = ", ".join([normalize_author(a) for a in meta.authors]).lower()
        
        # Strip commas and normalize whitespace for comparison
        q_auth_clean = re.sub(r'[,\s]+', ' ', q_auth).strip()
        found_auth_clean = re.sub(r'[,\s]+', ' ', found_auth_joined).strip()
        
        # Helper function to strip degree suffixes and clean individual names
        def clean_author_name(author_name):
            # Remove PhD, MD, Dr., MA, MBA, etc. (case-insensitive)
            # Also strip extra whitespace
            name = re.sub(r'\s*(phd|md|dr\.?|ma|mba|mfa|ms|bs|ba)\s*', '', author_name, flags=re.IGNORECASE)
            return re.sub(r'\s+', ' ', name).strip()
        
        # Order-independent author matching: split into individual names and compare as sets
        # IMPORTANT: Use q_auth/found_auth_joined (with separators) for splitting, 
        # NOT q_auth_clean/found_auth_clean (which have commas stripped)
        # Regex split by: comma, ampersand, slash, backslash, or " and "
        sep_pattern = r'[,&/\\]|\sand\s'
        
        q_authors_list = re.split(sep_pattern, q_auth)
        q_authors_set = set([clean_author_name(a) for a in q_authors_list if a.strip()])
        
        found_authors_list = re.split(sep_pattern, found_auth_joined)
        found_authors_set = set([clean_author_name(a) for a in found_authors_list if a.strip()])
        
        # Check if all query authors are in found authors (allows extra authors in found)
        if q_authors_set and q_authors_set.issubset(found_authors_set):
            # All query authors found (order doesn't matter)
            author_sim = 1.0
        else:
            # Fall back to fuzzy matching (on cleaned strings)
            author_sim = difflib.SequenceMatcher(None, q_auth_clean, found_auth_clean).ratio()
    
    # Adaptive Weighting: Only score fields that exist in query
    if author_sim is not None:
        # Both title and author available: weighted scoring
        score = (title_sim * 0.6) + (author_sim * 0.4)
    else:
        # Only title available: use 100% title similarity (no penalty for missing author)
        score = title_sim
    
    return score

# --- Providers ---

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s

def audible_find_asin(session: requests.Session, q: BookQuery, region: str="us") -> Tuple[Optional[str], Optional[str]]:
    query = (q.title + " " + q.author).strip() if q.author else q.title
    if not query:
        return None, None

    base = f"https://www.audible.{region}" if region in ("uk", "in") else "https://www.audible.com"
    try:
        r = session.get(f"{base}/search", params={"keywords": query}, timeout=10)
        if r.status_code in (401, 403):
            return None, None
        
        soup = BeautifulSoup(r.text, "html.parser")
        a = soup.select_one("a[href*='/pd/']")
        if not a:
            return None, None

        href = a.get("href", "")
        book_url = href if href.startswith("http") else base + href

        m = re.search(r"/pd/[^/]+/([A-Z0-9]{10})", book_url)
        if not m:
            m = re.search(r"/([A-Z0-9]{10})(?:\?|$)", book_url)
        asin = m.group(1) if m else None

        return asin, book_url
    except Exception:
        return None, None

def provider_audnexus_by_asin(session: requests.Session, asin: str) -> Optional[BookMeta]:
    url = f"https://api.audnex.us/books/{asin}"
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            return None
            
        data = r.json() or {}
        
        title = norm_space(str(data.get("title") or ""))
        desc = shorten_description(str(data.get("description") or "") or str(data.get("summary") or ""))
        
        authors = [a.get("name") for a in (data.get("authors") or []) if isinstance(a, dict) and a.get("name")]
        narrators = [n.get("name") for n in (data.get("narrators") or []) if isinstance(n, dict) and n.get("name")]
        
        genres = []
        tags = []
        for g in (data.get("genres") or []):
            if not isinstance(g, dict): continue
            name = norm_space(str(g.get("name") or ""))
            typ = norm_space(str(g.get("type") or "")).lower()
            if not name: continue
            
            # Helper to split granular genres by "&" and ","
            # "Business & Careers" -> ["Business", "Careers"]
            sub_parts = re.split(r'[,&]|\sand\s', name)
            clean_parts = [p.strip() for p in sub_parts if p.strip()]

            if typ == "genre": 
                genres.extend(clean_parts)
            else: 
                tags.extend(clean_parts) 
        
        cover_url = str(data.get("image") or "")
        
        # Extract Series for Grouping
        # "series": [{"title": "Series Name", "sequence": "1"}]
        grouping = ""
        series_list = data.get("series") or []
        if series_list and isinstance(series_list, list) and len(series_list) > 0:
            first_series = series_list[0]
            if isinstance(first_series, dict):
                 series_name = first_series.get("title")
                 if series_name:
                     grouping = series_name
            
        return BookMeta(
            title=title,
            authors=uniq_ci(authors),
            narrators=uniq_ci(narrators),
            publisher=norm_space(str(data.get("publisherName") or "")),
            published_date=norm_space(str(data.get("releaseDate") or "")),
            language=norm_space(str(data.get("language") or "")),
            description=desc,
            genres=uniq_ci(genres),
            tags=uniq_ci(tags),
            source="audnexus",
            source_url=f"https://www.audible.com/pd/{asin}",
            cover_url=cover_url,
            asin=asin,
            grouping=grouping
        )
    except Exception:
        return None

def provider_audible_scrape(session: requests.Session, url: str) -> Optional[BookMeta]:
    try:
        print(f"DEBUG: Scrape URL: {url}")
        # Simply scrape the page
        r = session.get(url, timeout=10)
        print(f"DEBUG: Status Code: {r.status_code}")
        print(f"DEBUG: Snippet: {r.text[:500]}")
        if r.status_code != 200:
            return None
            
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 1. Title: <h1 slot="title">Project Hail Mary</h1>
        title = ""
        h1 = soup.select_one("h1[slot='title']")
        print(f"DEBUG: H1 (slot): {h1}")
        if not h1:
             # Fallback to standard h1
             h1 = soup.select_one("h1.bc-heading")
             print(f"DEBUG: H1 (heading): {h1}")
        if h1:
            title = h1.get_text().strip()
        
        print(f"DEBUG: Extracted Title: '{title}'")
        if not title: return None
        
        # 2. Metadata from JSON (Best Source)
        # <adbl-product-metadata ...><script type="application/json">...</script></adbl-product-metadata>
        authors = []
        narrators = []
        
        json_script = soup.select_one("adbl-product-metadata script[type='application/json']")
        if json_script:
            try:
                data = json.loads(json_script.get_text())
                # Authors
                for a in data.get("authors", []):
                    if a.get("name"): authors.append(a["name"])
                # Narrators
                for n in data.get("narrators", []):
                    if n.get("name"): narrators.append(n["name"])
            except:
                pass
        
        # Fallback to visual elements if JSON failed
        if not authors:
            for li in soup.select(".authorLabel a"):
                authors.append(li.get_text().strip())
        if not narrators:
            for li in soup.select(".narratorLabel a"):
                narrators.append(li.get_text().strip())

        # 3. Description
        desc = ""
        # Try meta tag first
        meta_desc = soup.select_one("meta[name='description']")
        if meta_desc:
            desc = meta_desc.get("content", "")
        else:
            desc_div = soup.select_one("div[class*='productDescription']")
            if desc_div:
                desc = desc_div.get_text().strip()
            
        # Clean up "Check out this great listen..." or "Publisher's Summary"
        if "Publisher's Summary" in desc:
            desc = desc.split("Publisher's Summary", 1)[1].strip()
            
        # 4. Genres: <li class="categoriesLabel">
        genres = []
        for li in soup.select(".categoriesLabel a"):
            g = li.get_text().strip()
            if g.lower() != "audiobook": 
                genres.append(g)
                
        # 5. Publisher
        publisher = ""
        pub_li = soup.select_one(".publisherLabel a")
        if pub_li:
            publisher = pub_li.get_text().strip()
            
        # 6. Release Date
        release_date = ""
        date_li = soup.select_one(".releaseDateLabel")
        if date_li:
            txt = date_li.get_text().strip()
            if "Release date:" in txt:
                release_date = txt.split("Release date:", 1)[1].strip()
                
        # 7. Image
        cover_url = ""
        # adbl-product-image img
        img = soup.select_one("adbl-product-image img")
        if not img:
            img = soup.select_one("img.bc-image-inset-border")
        if img:
            cover_url = img.get("src", "")
            
        asin = extract_asin_from_url(url) or ""
        
        return BookMeta(
            title=title,
            authors=uniq_ci(authors),
            narrators=uniq_ci(narrators),
            publisher=publisher,
            published_date=release_date,
            description=shorten_description(desc),
            genres=uniq_ci(genres),
            source="audible_scrape",
            source_url=url,
            cover_url=cover_url,
            asin=asin
        )
    except Exception as e:
        print(f"DEBUG: Scrape Error: {e}")
        return None

def google_books_search(session: requests.Session, q: BookQuery, api_key: str = None) -> Optional[BookMeta]:
    if not q.title: return None
    parts = [f'intitle:"{q.title}"']
    if q.author: parts.append(f'inauthor:"{q.author}"')
    query = " ".join(parts)
    
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": query, "maxResults": 1, "printType": "books"}
    
    # Add API key if provided for higher rate limits
    if api_key:
        params["key"] = api_key
    
    try:
        r = session.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        if not items: return None
        
        vi = items[0].get("volumeInfo", {})
        
        # Cover Art URL
        image_links = vi.get("imageLinks", {})
        cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")
        if cover_url:
             # Try to get higher res
             cover_url = cover_url.replace("&edge=curl", "") 
            
        # Try to find ISBN as ASIN equivalent? No, different systems.

        return BookMeta(
            title=vi.get("title", ""),
            authors=vi.get("authors", []),
            publisher=vi.get("publisher", ""),
            published_date=vi.get("publishedDate", ""),
            description=shorten_description(vi.get("description", "")),
            genres=uniq_ci(vi.get("categories", [])),
            language=vi.get("language", ""),
            rating=str(vi.get("averageRating", "")),
            source="google_books",
            source_url=vi.get("infoLink", ""),
            cover_url=cover_url
        )
    except Exception:
        return None

# --- Tagging Logic ---

def read_metadata(path: str) -> BookQuery:
    title = ""
    author = ""
    try:
        if path.lower().endswith(".mp3"):
            tags = EasyID3(path)
            # User Request: Use Album for Book Name lookup if available
            album = tags.get("album", [""])[0]
            title = album if album else tags.get("title", [""])[0]
            author = tags.get("artist", [""])[0] or tags.get("albumartist", [""])[0]
        elif path.lower().endswith((".m4a", ".m4b")):
            tags = MP4(path)
            # Similarly for M4B, 'alb' is usually the book title
            album = tags.get("\xa9alb", [""])[0]
            title = album if album else tags.get("\xa9nam", [""])[0]
            author = tags.get("\xa9ART", [""])[0] or tags.get("aART", [""])[0]
        elif path.lower().endswith(".opus"):
            tags = OggOpus(path)
            title = tags.get("album", [""])[0] if tags.get("album") else tags.get("title", [""])[0]
            author = tags.get("artist", [""])[0] if tags.get("artist") else ""
    except Exception:
        pass
        
    if not title:
        # Fallback to filename
        base = os.path.splitext(os.path.basename(path))[0]
        # Common patterns: "Title (Author)" or "Author - Title"
        
        # Pattern: Title (Author)
        m = re.match(r"(.+)\s+\((.+)\)", base)
        if m:
            title = m.group(1)
            author = m.group(2)
        else:
            base = re.sub(r"[_\-]", " ", base)
            title = base
        
    return BookQuery(title=title.strip(), author=author.strip())

def has_cover_art(path: str) -> bool:
    try:
        if path.lower().endswith(".mp3"):
            tags = ID3(path)
            return any(k.startswith("APIC") for k in tags.keys())
        elif path.lower().endswith((".m4a", ".m4b")):
            tags = MP4(path)
            return "covr" in tags
        elif path.lower().endswith(".opus"):
            tags = OggOpus(path)
            return "metadata_block_picture" in tags or "coverart" in tags
    except Exception:
        return False

def has_valid_genre(path: str) -> bool:
    """
    Check if file already has a valid genre (not just 'Audiobook' or empty).
    Returns True if genre exists and is not just the generic 'Audiobook' placeholder.
    """
    try:
        existing_genre = ""
        if path.lower().endswith(".mp3"):
            tags = EasyID3(path)
            existing_genre = tags.get("genre", [""])[0]
        elif path.lower().endswith((".m4a", ".m4b")):
            tags = MP4(path)
            existing_genre = tags.get("\xa9gen", [""])[0] if tags.get("\xa9gen") else ""
        elif path.lower().endswith(".opus"):
            tags = OggOpus(path)
            existing_genre = tags.get("genre", [""])[0] if tags.get("genre") else ""
        
        # Normalize and check
        existing_genre = existing_genre.strip()
        if not existing_genre:
            return False
        
        # Check if it's just the generic "Audiobook" placeholder
        if existing_genre.lower() in ["audiobook", "audiobooks", "audio book", "audio books"]:
            return False
            
        return True  # Has a real genre value
    except Exception:
        return False

def update_mp3_tags(path: str, meta: BookMeta, cover_data: bytes = None, fields_to_update: dict = None):
    if fields_to_update is None:
        fields_to_update = {"title": True, "author": True, "album": True, "album_artist": True, "genre": True, "year": True, "publisher": True, "description": True, "cover": True, "grouping": True, "compilation": True}
    
    try:
        tags = ID3(path)
    except Exception:
        tags = ID3()
    
    # Text Tags (conditional)
    if fields_to_update.get("title") and meta.title:
        tags.add(TIT2(encoding=3, text=[meta.title]))
    if fields_to_update.get("author") and meta.authors:
        tags.add(TPE1(encoding=3, text=meta.authors))  # Artist
    if fields_to_update.get("album") and meta.title:
        tags.add(TALB(encoding=3, text=[meta.title]))  # Album = Title for audiobooks
    if fields_to_update.get("album_artist") and meta.authors:
        tags.add(TPE2(encoding=3, text=meta.authors))  # Album Artist = Author
    if fields_to_update.get("year") and meta.published_date:
        tags.add(TDRC(encoding=3, text=[meta.published_date]))
    if fields_to_update.get("publisher") and meta.publisher:
        tags.add(TPUB(encoding=3, text=[meta.publisher]))
    if meta.language:
        tags.add(TLAN(encoding=3, text=[meta.language]))
    if fields_to_update.get("description") and meta.description:
        tags.add(COMM(encoding=3, lang="eng", desc="Description", text=[meta.description]))
    if fields_to_update.get("grouping") and meta.genres:
        # Use first genre as grouping
        tags.add(TIT1(encoding=3, text=[meta.genres[0]]))
    if fields_to_update.get("compilation"):
        # Mark as compilation (1 = yes, 0 = no)
        tags.add(TCMP(encoding=3, text=["1"]))
    
    # Genre Update
    if fields_to_update.get("genre") and meta.genres:
        genre_str = "; ".join(meta.genres)
        tags.add(TCON(encoding=3, text=[genre_str]))

    # Clear Track/Disc Numbers (single file audiobooks shouldn't have these)
    tags.delall("TRCK")  # Track number
    tags.delall("TPOS")  # Disc number

    # Cover Art
    if fields_to_update.get("cover") and cover_data:
        tags.delall("APIC")
        tags.add(APIC(
            encoding=3,
            mime='image/jpeg',
            type=3, 
            desc='Cover',
            data=cover_data
        ))
    
    tags.save(path, v2_version=3)

def update_mp4_tags(path: str, meta: BookMeta, cover_data: bytes = None, fields_to_update: dict = None):
    if fields_to_update is None:
        fields_to_update = {"title": True, "author": True, "album": True, "album_artist": True, "genre": True, "year": True, "publisher": True, "description": True, "cover": True, "grouping": True, "compilation": True}
    
    tags = MP4(path)
    
    if fields_to_update.get("title") and meta.title:
        tags["\xa9nam"] = [meta.title]
    if fields_to_update.get("author") and meta.authors:
        tags["\xa9ART"] = meta.authors  # Artist
    if fields_to_update.get("album") and meta.title:
        tags["\xa9alb"] = [meta.title]  # Album = Title for audiobooks
    if fields_to_update.get("album_artist") and meta.authors:
        tags["aART"] = meta.authors  # Album Artist = Author
    if fields_to_update.get("year") and meta.published_date:
        tags["\xa9day"] = [meta.published_date]
    if fields_to_update.get("publisher") and meta.publisher:
        tags["\xa9pub"] = [meta.publisher]
    if fields_to_update.get("description") and meta.description:
        tags["desc"] = [meta.description]
    if fields_to_update.get("grouping") and meta.genres:
        tags["\xa9grp"] = [meta.genres[0]]  # First genre as grouping
    if fields_to_update.get("compilation"):
        tags["cpil"] = [True]  # Compilation flag
    
    # Genre
    if fields_to_update.get("genre") and meta.genres:
        tags["\xa9gen"] = ["; ".join(meta.genres)]
    
    # Clear Track/Disc Numbers (single file audiobooks shouldn't have these)
    if "trkn" in tags:
        del tags["trkn"]  # Track number
    if "disk" in tags:
        del tags["disk"]  # Disc number
        
    if fields_to_update.get("cover") and cover_data:
        tags["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]
        
    tags.save()

def update_opus_tags(path: str, meta: BookMeta, cover_data: bytes = None, fields_to_update: dict = None):
    if fields_to_update is None:
        fields_to_update = {"title": True, "author": True, "album": True, "album_artist": True, "genre": True, "year": True, "publisher": True, "description": True, "cover": True, "grouping": True, "compilation": True}
    
    tags = OggOpus(path)
    
    if fields_to_update.get("title") and meta.title:
        tags["title"] = meta.title
    if fields_to_update.get("author") and meta.authors:
        tags["artist"] = "; ".join(meta.authors)
    if fields_to_update.get("album") and meta.title:
        tags["album"] = meta.title
    if fields_to_update.get("album_artist") and meta.authors:
        tags["albumartist"] = "; ".join(meta.authors)
    if fields_to_update.get("year") and meta.published_date:
        tags["date"] = meta.published_date
    if fields_to_update.get("publisher") and meta.publisher:
        tags["organization"] = meta.publisher
    if fields_to_update.get("description") and meta.description:
        tags["description"] = meta.description
    if fields_to_update.get("grouping") and meta.genres:
        tags["grouping"] = meta.genres[0]
    if fields_to_update.get("compilation"):
        tags["compilation"] = "1"
    if fields_to_update.get("genre") and meta.genres:
        tags["genre"] = "; ".join(meta.genres)
    
    # Clear Track/Disc Numbers (single file audiobooks shouldn't have these)
    if "tracknumber" in tags:
        del tags["tracknumber"]
    if "discnumber" in tags:
        del tags["discnumber"]
    if "totaltracks" in tags:
        del tags["totaltracks"]
    if "totaldiscs" in tags:
        del tags["totaldiscs"]
    
    # Note: Cover art for Opus is complex (requires base64 encoding), skipping for now
    
    tags.save()

def apply_metadata(path: str, meta: BookMeta, cover_data: bytes = None, fields_to_update: dict = None):
    if path.lower().endswith(".mp3"):
        update_mp3_tags(path, meta, cover_data, fields_to_update)
    elif path.lower().endswith((".m4a", ".m4b")):
        update_mp4_tags(path, meta, cover_data, fields_to_update)
    elif path.lower().endswith(".opus"):
        update_opus_tags(path, meta, cover_data, fields_to_update)

from src.core.audio_shelf.atf import ATFHandler


def is_file_metadata_match(path: str, meta: BookMeta, fields_to_update: dict) -> bool:
    """
    Checks if the file's current tags ALREADY match the target metadata.
    Returns True if they match (so we can skip writing).
    Only checks the fields specified in fields_to_update.
    """
    if not os.path.exists(path):
        return False

    try:
        # Helper to compare values loosely
        def is_match(tag_val, target_val):
            if not target_val: return True # If target is empty, ignore
            if not tag_val: return False   # If target exists but tag doesn't, mismatch
            
            # Normalize to strings/lists
            if isinstance(tag_val, list):
                s_tag = "; ".join([str(v) for v in tag_val]).lower()
            else:
                s_tag = str(tag_val).lower()
                
            if isinstance(target_val, list):
                s_target = "; ".join([str(v) for v in target_val]).lower()
            else:
                s_target = str(target_val).lower()
            
            # Simple fuzzy-ish check: string equality after normalization
            return s_tag.strip() == s_target.strip()

        # Load Tags based on format
        tags = None
        if path.lower().endswith(".mp3"):
            try:
                tags = EasyID3(path)
            except:
                return False
        elif path.lower().endswith((".m4a", ".m4b")):
            try:
                 tags = MP4(path)
            except:
                return False
        elif path.lower().endswith(".opus"):
            try:
                tags = OggOpus(path)
            except:
                return False
        else:
            return False

        if not tags:
            return False

        # Check Fields
        is_mp3 = path.lower().endswith(".mp3")
        is_mp4 = path.lower().endswith((".m4a", ".m4b"))
        is_opus = path.lower().endswith(".opus")

        # Map internal 'meta' fields to file tags
        if fields_to_update.get("title") and meta.title:
            t_key = "title" if (is_mp3 or is_opus) else "\xa9nam"
            if not is_match(tags.get(t_key), meta.title): return False

        if fields_to_update.get("author") and meta.authors:
            a_key = "artist" if (is_mp3 or is_opus) else "\xa9ART"
            if not is_match(tags.get(a_key), meta.authors): return False
            
        if fields_to_update.get("album") and meta.title:
            alb_key = "album" if (is_mp3 or is_opus) else "\xa9alb"
            if not is_match(tags.get(alb_key), meta.title): return False

        if fields_to_update.get("genre") and meta.genres:
            g_key = "genre" if (is_mp3 or is_opus) else "\xa9gen"
            if not is_match(tags.get(g_key), meta.genres): return False

        if fields_to_update.get("publisher") and meta.publisher:
            p_key = "organization" if (is_mp3 or is_opus) else "\xa9pub" # EasyID3 uses organization? actually often TCOR/TPUB
            if is_mp3:
                # EasyID3 mapping for publisher is sometimes 'organization' or 'performer'? 
                # EasyID3 standard keys: album, compilation, title, artist, albumartist...
                # 'publisher' is valid in standard definitions?
                # Actually EasyID3 maps 'organization' to TPUB.
                p_key = "organization" 
            if not is_match(tags.get(p_key), meta.publisher): return False
            
        if fields_to_update.get("year") and meta.published_date:
            y_key = "date" if (is_mp3 or is_opus) else "\xa9day"
            if not is_match(tags.get(y_key), meta.published_date): return False
            
        # If we passed all checks
        return True
        
    except Exception as e:
        # On any error reading tags, assume mismatch and force update
        return False


# --- Merging Logic ---

def merge_metadata(primary: BookMeta, secondary: BookMeta) -> BookMeta:
    """
    Merges secondary metadata into primary.
    - Lists (Genres, Tags, Authors, Narrators): Union (Deduplicated).
    - Singles (Description, Publisher, Date): Keep Primary unless empty, or if Secondary is significantly better.
    """
    if not secondary:
        return primary
    if not primary:
        return secondary
        
    # Merge genres (Union)
    # 1. Combine
    raw_genres = primary.genres + secondary.genres
    
    # 2. Split granularly (Aggressive splitting to fix "Business & Economics")
    final_genres = []
    for g in raw_genres:
        # Split by & , or ' and '
        parts = re.split(r'[,&]|\sand\s', g)
        clean_parts = [p.strip() for p in parts if p.strip()]
        final_genres.extend(clean_parts)
        
    new_genres = uniq_ci(final_genres)
    new_tags = uniq_ci(primary.tags + secondary.tags)
    new_authors = uniq_ci(primary.authors + secondary.authors)
    new_narrators = uniq_ci(primary.narrators + secondary.narrators)
    
    # Description: Prefer Longest
    desc = primary.description
    if secondary.description and len(secondary.description) > len(desc or ""):
        desc = secondary.description
        
    # Date/Publisher: Prefer Primary, fallback to secondary
    pub = primary.publisher or secondary.publisher
    date = primary.published_date or secondary.published_date
    lang = primary.language or secondary.language
    
    # Source string
    source_str = f"{primary.source}+{secondary.source}" if primary.source and secondary.source else (primary.source or secondary.source)
    
    return BookMeta(
        title=primary.title, # Always keep primary title identification
        authors=new_authors,
        narrators=new_narrators,
        publisher=pub,
        published_date=date,
        language=lang,
        description=desc,
        genres=new_genres,
        tags=new_tags,
        isbn10=primary.isbn10 or secondary.isbn10,
        isbn13=primary.isbn13 or secondary.isbn13,
        rating=primary.rating or secondary.rating,
        rating_count=primary.rating_count or secondary.rating_count,
        source=source_str,
        source_url=primary.source_url or secondary.source_url,
        cover_url=primary.cover_url or secondary.cover_url,
        asin=primary.asin or secondary.asin,
        grouping=primary.grouping or secondary.grouping
    )

class TaggerEngine:
    def __init__(self, log_callback=None, google_books_api_key=None):
        self.session = make_session()
        self.atf_handler = ATFHandler()
        self.log_callback = log_callback
        self.google_books_api_key = google_books_api_key
        
    def log(self, msg):
        if self.log_callback:
            self.log_callback(msg)
        else:
            print(msg)

    def process_file(self, path: str, fields_to_update: dict = None, dry_run: bool = False, force_cover: bool = False, providers: List[str] = None) -> Tuple[bool, str]:
        """
        Returns (success, message)
        fields_to_update: dict with keys: title, author, album, genre, year, publisher, description, cover
        dry_run: if True, skip writing but show what would be written
        force_cover: if True, replace cover art even if it exists
        providers: List of providers to fetch from. Options: ['audnexus', 'google']. Default: ['audnexus']
        """
        if providers is None:
            providers = ['audnexus']
            
        directory = os.path.dirname(path)
        self.log(f"--- Processing: {os.path.basename(path)} ---")
        
        # --- ATF CACHE CHECK ---
        atf_status, atf_data = self.atf_handler.read_atf(directory)
        
        if atf_status == "METADATA_NOT_FOUND":
            return False, "Skipped (Cached: Metadata previously found not to exist)"
        elif atf_status == "LOW_CONFIDENCE":
            return False, "Skipped (Cached: Previous confidence check failed)"
            
        elif atf_status == "SUCCESS" and atf_data:
            # Check if ATF has all fields we want to update
            # For now, if we have a successful cache, we assume it's good enough unless forced
            # But the user asked to check if "current run is for specific fields that is already not in ATF file"
            
            missing_fields = []
            if fields_to_update:
                for field, needed in fields_to_update.items():
                    if needed:
                        if field == "cover":
                             # Check if cover_base64 exists
                             if "cover_base64" not in atf_data and not has_cover_art(path):
                                 missing_fields.append("cover")
                        elif field == "album_artist":
                             if not atf_data.get("authors"): # Album Artist maps to authors
                                 missing_fields.append(field)
                        elif field == "grouping":
                             if not atf_data.get("genres"): # Grouping maps to genres
                                 missing_fields.append(field)
                        elif field == "compilation":
                             pass # Compilation is a flag, usually not in metadata search
                        elif field not in atf_data:
                            # Map internal names if needed, but for now ATF uses 'title', 'authors', etc.
                            # 'author' in fields -> 'authors' in ATF
                            if field == "author" and "authors" in atf_data: continue
                            if field == "album" and "title" in atf_data: continue # Album = Title
                            
                            # If we really are missing data, add to list
                            # For simplicity, if we have a SUCCESS cache, we likely have the main data.
                            pass

            # If we decide to use cache:
            # We can use the data from ATF to write tags directly without fetching from API!
            pass 
            # But for "Skipping directory", user said: "If current run is same for the data already there. then it would skip the directory."
            # So if we have SUCCESS and we are not forcing, we can skip fetching?
            # Actually, let's implement the "Skip Directory" logic first. 
            # If the user wants to update tags on files that *haven't* been updated, but the directory scan
            # says "I already did this book", do we skip?
            # Yes, "app is not updating each and every file that have been update before."
            
            # Simple logic: If valid ATF exists and we are not forcing a refresh, SKIP.
            # But we might need to APPLY the cached tags to the file if the file lacks them?
            # User said: "app is not updating... each file that have been updated before"
            # implying we assume files are done if ATF is present.
            
            # However, if the user added new files to the folder, we might want to tag them using cached data.
            # Let's try to USE valid cache to tag the file, skipping the API search.
            self.log("Found cached metadata (ATF). Using cache instead of online search.")
            
            meta = BookMeta(
                source=atf_data.get("source", "Cache"),
                title=atf_data.get("title"),
                authors=atf_data.get("authors", []),
                published_date=atf_data.get("published_date"),
                description=atf_data.get("description"),
                publisher=atf_data.get("publisher"),
                genres=atf_data.get("genres", []),
                asin=atf_data.get("asin"),
                cover_url=None
            )
            
            cover_data = None
            if atf_data.get("cover_base64"):
                try:
                    cover_data = base64.b64decode(atf_data["cover_base64"])
                except:
                    pass
            
            # Proceed to write tags using this meta -- BUT SKIP IF ALREADY MATCHES
            if not dry_run and not force_cover:
                 # Check if the file tags effectively match the meta we are about to write
                 # This prevents re-writing thousands of files that are already correct.
                 if is_file_metadata_match(path, meta, fields_to_update):
                     # Also check cover? (Rough check: if not forcing cover, and text matches, we assume good)
                     # Or check if cover exists. logic is complex, simpler to trust text match + has_cover check
                     if has_cover_art(path):
                         self.log("Skipping file (Metadata & Cover already up-to-date with Cache).")
                         return True, "Skipped (Already up-to-date)"
            
            if dry_run:
                self.log("🔍 DRY RUN: Using Cached Metadata (would apply tags...)")
                return True, "Dry Run"
            else:
                apply_metadata(path, meta, cover_data, fields_to_update)
                return True, "Tags updated from Cache"

        # --- END ATF CHECK ---

        q = read_metadata(path)
        self.log(f"Extracted Metadata from File:\n\tTitle: {q.title}\n\tAuthor: {q.author}")
        
        if not q.title:
            return False, "No Title found to search"
            
            
        meta_results = []
        
        # --- MULTI-PROVIDER SEARCH ---
        
        # Provider 1: Audnexus (Audible) - Primary
        if 'audnexus' in providers:
            self.log("Step 1: Trying Audnexus (Audible)...")
            asin, _ = audible_find_asin(self.session, q)
            if asin:
                self.log(f"Found ASIN via Internal Search: {asin}")
                audnexus_meta = provider_audnexus_by_asin(self.session, asin)
                if audnexus_meta:
                    meta_results.append(audnexus_meta)
                    self.log(f"Audnexus: Found '{audnexus_meta.title}'")
            
            # Fallback: DuckDuckGo external search if internal fails
            if not meta_results:
                self.log("Internal search failed. Trying Robust External Search (DuckDuckGo)...")
                query_str = f"{q.title} {q.author}".strip()
                found_urls = search_duckduckgo_audible(query_str)
                
                for url in found_urls:
                    self.log(f"Found candidate URL: {url}")
                    # Try to extract ASIN first for Audnexus (Cleanest Data)
                    found_asin = extract_asin_from_url(url)
                    if found_asin:
                        self.log(f"Extracted ASIN: {found_asin}. Querying Audnexus...")
                        audnexus_meta = provider_audnexus_by_asin(self.session, found_asin)
                        if audnexus_meta:
                            self.log("Audnexus Success!")
                            meta_results.append(audnexus_meta)
                            break
                    
                    # If no ASIN or Audnexus failed, Try Direct Scrape
                    if not meta_results:
                        self.log("Audnexus failed. Fallback: Direct HTML Scraping...")
                        scrape_meta = provider_audible_scrape(self.session, url)
                        if scrape_meta:
                            self.log("Direct Scraping Success!")
                            meta_results.append(scrape_meta)
                            break
        
        # Provider 2: Google Books (Enrichment)
        if 'google' in providers:
            self.log("Step 2: Querying Google Books for enrichment...")
            google_meta = google_books_search(self.session, q, api_key=self.google_books_api_key)
            if google_meta:
                meta_results.append(google_meta)
                self.log(f"Google Books: Found '{google_meta.title}'")
            else:
                self.log("Google Books: No results")
        
        #  If no metadata found from ANY provider
        if not meta_results:
            self.log("No metadata found from any source.")
            # Record failure in ATF to skip this directory next time
            self.atf_handler.write_atf(directory, os.path.basename(directory), "METADATA_NOT_FOUND")
            return False, "No metadata found online"
        
        # --- MERGE RESULTS ---
        if len(meta_results) == 1:
            meta = meta_results[0]
            self.log(f"Match Found: '{meta.title}' via {meta.source}")
        else:
            # Multiple sources - merge them!
            self.log(f"Merging metadata from {len(meta_results)} sources...")
            meta = meta_results[0]  # Start with primary (usually Audnexus)
            for secondary in meta_results[1:]:
                meta = merge_metadata(meta, secondary)
            self.log(f"Merged Result: '{meta.title}' from {meta.source}")
              
        # 4. Confidence Check
        self.log("Step 3: Calculating Confidence Score...")
        confidence = calculate_confidence(q, meta)
        
        source_detail = meta.source
        if meta.asin:
            source_detail += f", ASIN: {meta.asin}"
        
        # Format authors without square brackets
        authors_str = ", ".join(meta.authors) if meta.authors else "Unknown"
        found_info = f"Found: '{meta.title}' by {authors_str} [{source_detail}]"
        
        if confidence < 0.85:
             msg = f"Skipped (Low Confidence {confidence:.2f})\n\tFound: {found_info}"
             msg += f"\n\tGenres: {meta.genres}"
             self.log(f"CONFIDENCE FAIL: {confidence:.2f} < 0.85")
             self.log(f"Query was: {q.title} / {q.author}")
             self.log(f"Found was: {meta.title} / {meta.authors}")
             # Record failure in ATF to skip this directory next time
             self.atf_handler.write_atf(directory, os.path.basename(directory), "LOW_CONFIDENCE")
             return False, msg

        self.log(f"Confidence PASS ({confidence:.2f}). Proceeding to update.")

        # 5. Handle Cover Art (only if checkbox is enabled)
        cover_data = None
        if fields_to_update.get('cover', True):  # Default to True if not specified
            if force_cover:
                self.log("Force Replace Cover Art enabled. Will download and replace.")
                if meta.cover_url:
                    try:
                        self.log(f"Downloading Cover from: {meta.cover_url}")
                        r = self.session.get(meta.cover_url, timeout=10)
                        if r.status_code == 200:
                            cover_data = r.content
                            self.log("Cover downloaded successfully.")
                    except Exception:
                        self.log("Failed to download cover.")
                else:
                    self.log("No Cover URL in metadata.")
            elif has_cover_art(path):
                self.log("Existing Cover Art detected. Preserving it.")
            else:
                self.log("No Cover Art. Attempting to fetch...")
                if meta.cover_url:
                    try:
                        self.log(f"Downloading Cover from: {meta.cover_url}")
                        r = self.session.get(meta.cover_url, timeout=10)
                        if r.status_code == 200:
                            cover_data = r.content
                            self.log("Cover downloaded successfully.")
                    except Exception:
                        self.log("Failed to download cover.")
                else:
                    self.log("No Cover URL in metadata.")
        else:
            self.log("Cover Art checkbox unchecked. Skipping cover art update.")
        
        try:
            if dry_run:
                self.log("🔍 DRY RUN: Skipping file write (would apply tags...)")
                msg = f"[DRY RUN] Would Update (Confidence {confidence:.2f})\n\t{found_info}"
                msg += f"\n\tGenres: {meta.genres}"
                self.log("DRY RUN: File would be updated.")
                return True, msg
            else:
                self.log("Applying tags to file...")
                # Log which fields will be updated
                updating_fields = [k for k, v in fields_to_update.items() if v]
                if updating_fields:
                    self.log(f"Fields to update: {', '.join(updating_fields)}")
                else:
                    self.log("⚠️  WARNING: No fields selected for update!")
                
                apply_metadata(path, meta, cover_data, fields_to_update)
                
                # --- WRITE ATF SUCCESS ---
                # Only write success if we actually passed confidence checks
                # Convert BookMeta to dict for storage
                meta_dict = {
                    "title": meta.title,
                    "authors": meta.authors,
                    "published_date": meta.published_date,
                    "description": meta.description,
                    "publisher": meta.publisher,
                    "genres": meta.genres,
                    "asin": meta.asin,
                    "source": meta.source
                }
                # Title for filename (sanitize handled by handler)
                book_title = meta.title if meta.title else os.path.basename(directory)
                self.atf_handler.write_atf(directory, book_title, "SUCCESS", meta_dict, cover_data)
                
                msg = f"Updated (Confidence {confidence:.2f})\n\t{found_info}"
                msg += f"\n\tGenres: {meta.genres}"
                self.log("SUCCESS: File updated.")
                return True, msg
        except Exception as e:
            self.log(f"ERROR: Failed to write tags: {e}")
            return False, f"Write Error: {str(e)}"
