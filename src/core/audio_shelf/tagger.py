
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
    """Normalize title for comparison: remove subtitles, disc references, and parenthetical content."""
    # Remove subtitle after colon: "Title: Subtitle" -> "Title"
    # Remove subtitle after dash: "Title - Subtitle" -> "Title"
    if ':' in title:
        title = title.split(':', 1)[0]
    elif ' - ' in title:
        # Only split on " - " (with spaces) to avoid splitting hyphenated words
        title = title.split(' - ', 1)[0]
    
    # Remove ALL parenthetical content: "Title (Anything Here)" -> "Title"
    title = re.sub(r'\s*\([^)]*\)\s*', ' ', title)
    
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
    
    # Normalize titles before comparison (remove subtitles)
    query_title_norm = normalize_title(query.title).lower()
    found_title_norm = normalize_title(meta.title).lower()
    
    # Title Similarity
    title_sim = difflib.SequenceMatcher(None, query_title_norm, found_title_norm).ratio()
    
    # Author Similarity (if available in query)
    author_sim = None
    if query.author and meta.authors:
        # Normalize both sides
        q_auth = normalize_author(query.author).lower()
        
        # Join multiple authors for comparison (handles "Author1, Author2" format)
        found_auth_joined = ", ".join([normalize_author(a) for a in meta.authors]).lower()
        
        # Compare the full author strings
        author_sim = difflib.SequenceMatcher(None, q_auth, found_auth_joined).ratio()
    
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
            if typ == "genre": genres.append(name)
            else: tags.append(name) 
        
        cover_url = str(data.get("image") or "")
            
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
            asin=asin
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

def google_books_search(session: requests.Session, q: BookQuery) -> Optional[BookMeta]:
    if not q.title: return None
    parts = [f'intitle:"{q.title}"']
    if q.author: parts.append(f'inauthor:"{q.author}"')
    query = " ".join(parts)
    
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": query, "maxResults": 1, "printType": "books"}
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

class TaggerEngine:
    def __init__(self):
        self.session = make_session()
        
    def process_file(self, path: str, fields_to_update: dict = None, dry_run: bool = False, force_cover: bool = False, log_callback=None) -> Tuple[bool, str]:
        """
        Returns (success, message)
        fields_to_update: dict with keys: title, author, album, genre, year, publisher, description, cover
        dry_run: if True, skip writing but show what would be written
        force_cover: if True, replace cover art even if it exists
        """
        def log(msg):
            if log_callback:
                log_callback(msg)

        log(f"--- Processing: {os.path.basename(path)} ---")
        
        q = read_metadata(path)
        log(f"Extracted Metadata from File:\n\tTitle: {q.title}\n\tAuthor: {q.author}")
        
        if not q.title:
            return False, "No Title found to search"
            
        meta = None

        # Strategy 1: Internal Audible Search -> Audnexus
        log("Step 1: Trying Internal Audible Search (Audnexus)...")
        asin, _ = audible_find_asin(self.session, q)
        if asin:
             log(f"Found ASIN via Internal Search: {asin}")
             meta = provider_audnexus_by_asin(self.session, asin)

        # Strategy 2: Robust External Search (DuckDuckGo) because Internal search sucks
        if not meta:
            log("Internal search failed. Step 2: Trying Robust External Search (DuckDuckGo)...")
            query_str = f"{q.title} {q.author}".strip()
            found_urls = search_duckduckgo_audible(query_str)
            
            for url in found_urls:
                log(f"Found candidate URL: {url}")
                # Try to extract ASIN first for Audnexus (Cleanest Data)
                found_asin = extract_asin_from_url(url)
                if found_asin:
                    log(f"Extracted ASIN: {found_asin}. Querying Audnexus...")
                    meta = provider_audnexus_by_asin(self.session, found_asin)
                    if meta:
                        log("Audnexus Success!")
                        break
                
                # If no ASIN or Audnexus failed, Try Direct Scrape (Robust fallback)
                if not meta:
                    log("Audnexus failed. Fallback: Direct HTML Scraping...")
                    meta = provider_audible_scrape(self.session, url)
                    if meta:
                        log("Direct Scraping Success!")
                        break
        
        # Strategy 3: Google Books (Last Resort)
        if not meta:
             log("Audible strategies failed. Step 3: Falling back to Google Books...")
             meta = google_books_search(self.session, q)
        else:
             log(f"Match Found: '{meta.title}' via {meta.source}")
             
        if not meta:
            log("No metadata found from any source.")
            return False, "No metadata found online"
            
        # 4. Confidence Check
        log("Step 4: Calculating Confidence Score...")
        confidence = calculate_confidence(q, meta)
        
        source_detail = meta.source
        if meta.asin:
            source_detail += f", ASIN: {meta.asin}"
        
        # Format authors without square brackets
        authors_str = ", ".join(meta.authors) if meta.authors else "Unknown"
        found_info = f"Found: '{meta.title}' by {authors_str} [{source_detail}]"
        
        if confidence < 0.90:
             msg = f"Skipped (Low Confidence {confidence:.2f})\n\tFound: {found_info}"
             msg += f"\n\tGenres: {meta.genres}"
             log(f"CONFIDENCE FAIL: {confidence:.2f} < 0.90")
             log(f"Query was: {q.title} / {q.author}")
             log(f"Found was: {meta.title} / {meta.authors}")
             return False, msg

        log(f"Confidence PASS ({confidence:.2f}). Proceeding to update.")

        # 5. Handle Cover Art
        cover_data = None
        if force_cover:
            log("Force Replace Cover Art enabled. Will download and replace.")
            if meta.cover_url:
                try:
                    log(f"Downloading Cover from: {meta.cover_url}")
                    r = self.session.get(meta.cover_url, timeout=10)
                    if r.status_code == 200:
                        cover_data = r.content
                        log("Cover downloaded successfully.")
                except Exception:
                    log("Failed to download cover.")
            else:
                log("No Cover URL in metadata.")
        elif has_cover_art(path):
            log("Existing Cover Art detected. Preserving it.")
        else:
             log("No Cover Art. Attempting to fetch...")
             if meta.cover_url:
                 try:
                     log(f"Downloading Cover from: {meta.cover_url}")
                     r = self.session.get(meta.cover_url, timeout=10)
                     if r.status_code == 200:
                         cover_data = r.content
                         log("Cover downloaded successfully.")
                 except Exception:
                     log("Failed to download cover.")
             else:
                 log("No Cover URL in metadata.")
        
        try:
            if dry_run:
                log("🔍 DRY RUN: Skipping file write (would apply tags...)")
                msg = f"[DRY RUN] Would Update (Confidence {confidence:.2f})\n\t{found_info}"
                msg += f"\n\tGenres: {meta.genres}"
                log("DRY RUN: File would be updated.")
                return True, msg
            else:
                log("Applying tags to file...")
                apply_metadata(path, meta, cover_data, fields_to_update)
                msg = f"Updated (Confidence {confidence:.2f})\n\t{found_info}"
                msg += f"\n\tGenres: {meta.genres}"
                log("SUCCESS: File updated.")
                return True, msg
        except Exception as e:
            log(f"ERROR: Failed to write tags: {e}")
            return False, f"Write Error: {str(e)}"
