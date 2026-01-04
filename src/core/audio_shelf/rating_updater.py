import os
import re
import requests
import json
import concurrent.futures
from typing import List, Optional, Tuple, Callable

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, COMM, TIT1
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus

# Import from main tagger
from .tagger import (
    BookQuery, BookMeta, make_session, merge_metadata,
    audible_find_asin, provider_audnexus_by_asin, 
    google_books_search, read_metadata, provider_audible_scrape
)
from .search_engine import (
    search_duckduckgo_audible, extract_asin_from_url,
    search_goodreads_direct, scrape_goodreads_rating,
    search_duckduckgo_amazon, scrape_amazon_rating
)
from .atf import ATFHandler

class RatingUpdaterEngine:
    def __init__(self, settings_manager=None, log_callback: Callable[[str], None] = None):
        self.session = make_session()
        self.atf_handler = ATFHandler()
        self.settings = settings_manager # Can be None if run CLI without it, should handle graceful defaults
        self.log_callback = log_callback or (lambda x: None)

    def log(self, msg: str):
        self.log_callback(msg)

    def scan_and_update(self, directories: List[str], progress_callback: Callable[[int, int], None] = None):
        """
        Main entry point for batch updating.
        Handles root directories by recursively finding subfolders with audio files.
        """
        # 1. Expand input directories into a list of actual Book Directories (containing audio)
        book_dirs = []
        for d in directories:
            if not os.path.exists(d): continue
            found = self._find_audio_directories(d)
            if found:
                book_dirs.extend(found)
            else:
                self.log(f"No audio files found in {os.path.basename(d)} or its subdirectories.")

        total = len(book_dirs)
        self.log(f"Found {total} audio directories to process.")
        
        # 2. Process each book directory in parallel
        # Reduced from 20 to 5 to avoid rate limiting/timeouts from Search Engines
        self.log(f"Starting parallel processing with 5 workers...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i, directory in enumerate(book_dirs):
                futures.append(executor.submit(self._process_book, directory, i + 1, total))
            
            # Wait for all to complete
            completed_count = 0
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    self.log(f"Thread Error: {e}")
                
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, total)

    def _process_book(self, directory, idx, total):
        """
        Helper method to process a single book directory.
        """
        try:
            self.log(f"\n--- Processing Book {idx}/{total}: {os.path.basename(directory)} ---")
            
            # Smart Skip removed to ensure ratings are always updated/corrected.
            # if self._is_already_rated(directory): ...

            # Get/Update ATF Metadata (Always fetches fresh as per rule)
            meta = self._get_or_update_atf(directory)
            
            if meta and meta.rating:
                self._update_files_in_dir(directory, meta)
            else:
                self.log(f"Skipping files in {os.path.basename(directory)}: No rating found.")
                
        except Exception as e:
            self.log(f"Error processing {directory}: {e}")

    def _is_already_rated(self, directory: str) -> bool:
        """
        Checks if the first found audio file in the directory already has an "X+ Rated Books" tag.
        """
        try:
             # Find first audio file
             extensions = ('.mp3', '.m4a', '.m4b', '.opus', '.ogg')
             target_file = None
             for f in os.listdir(directory):
                 if f.lower().endswith(extensions) and not f.startswith("._"):
                     target_file = os.path.join(directory, f)
                     break
             
             if not target_file: return False # Treat as not rated if no files
             
             ext = os.path.splitext(target_file)[1].lower()
             
             # Check based on extension
             if ext == '.mp3':
                 from mutagen.id3 import ID3
                 audio = ID3(target_file)
                 if "TIT1" in audio:
                     # TIT1 is list of strings
                     for item in audio["TIT1"].text:
                         if re.search(r"^[0-9]+\+ Rated Books", str(item), re.IGNORECASE):
                             return True
                             
             elif ext in ('.m4a', '.m4b'):
                 from mutagen.mp4 import MP4
                 audio = MP4(target_file)
                 if "\xa9grp" in audio:
                     val = audio["\xa9grp"]
                     # Can be list or string
                     if isinstance(val, list):
                         val = val[0]
                     
                     if re.search(r"^[0-9]+\+ Rated Books", str(val), re.IGNORECASE):
                        return True
                        
             elif ext in ('.opus', '.ogg'):
                 from mutagen.oggopus import OggOpus
                 audio = OggOpus(target_file)
                 if "grouping" in audio:
                     val = audio["grouping"] 
                     # List
                     for item in val:
                        if re.search(r"^[0-9]+\+ Rated Books", str(item), re.IGNORECASE):
                             return True
                             
        except Exception:
            return False # On error, assume not rated
            
        return False

    def _find_audio_directories(self, root_path: str) -> List[str]:
        """
        Recursively finds all directories that contain supported audio files.
        """
        audio_dirs = []
        EXTENSIONS = ('.mp3', '.m4a', '.m4b', '.opus', '.ogg')
        
        # efficient walk
        for root, dirs, files in os.walk(root_path):
            has_audio = False
            for f in files:
                if f.lower().endswith(EXTENSIONS) and not f.startswith("._"):
                    has_audio = True
                    break
            
            if has_audio:
                audio_dirs.append(root)
        
        return audio_dirs

    def _get_or_update_atf(self, directory: str) -> Optional[BookMeta]:
        """
        Reads ATF. If rating is missing, fetches from API and updates ATF.
        Returns BookMeta with valid rating if possible.
        """
        status, atf_data = self.atf_handler.read_atf(directory)
        
        # User Request: ALWAYS fetch fresh rating because ratings change over time.
        # We ignore existing ATF rating validity for the fetch step, but we use ATF data 
        # (like title) to help the search.
        
        self.log("Fetching fresh rating data (ignoring cache validity)...")
        
        # We need a query to search. Try to get it from ATF or first file
        query = None
        if atf_data:
             # ATF stores 'authors' as a list, BookQuery needs 'author' as string
             authors_list = atf_data.get("authors", [])
             author_str = authors_list[0] if authors_list else ""
             query = BookQuery(title=atf_data.get("title", ""), author=author_str)
        else:
             # Strategy 2: File Metadata
             for f in os.listdir(directory):
                 if f.lower().endswith(('.mp3', '.m4a', '.m4b', '.opus', '.ogg')):
                     q = read_metadata(os.path.join(directory, f))
                     if q and q.title:
                         query = q
                         break
             
             # Strategy 3: Directory Name Parsing (Author - Title)
             if not query:
                 dirname = os.path.basename(directory)
                 parts = dirname.split(" - ")
                 if len(parts) >= 2:
                     # Assume "Author - Title"
                     query = BookQuery(title=parts[1].strip(), author=parts[0].strip())
                 else:
                     # Assume just Title
                     query = BookQuery(title=dirname.strip(), author="")
         
         # Clean Query (remove parentheses content like 'Full Cast', 'Unabridged', etc.)
         # Regex: Remove anything in (...) or [...]
        clean_title = re.sub(r"[\(\[].*?[\)\]]", "", query.title).strip()
        if clean_title != query.title:
            self.log(f"Cleaning search query: '{query.title}' -> '{clean_title}'")
            query.title = clean_title

        self.log(f"Searching for: {query.title} ({query.author})")
        
        if not query or not query.title:
            self.log("Could not determine book title to search.")
            return None
        
        # === USE EXACT SAME SEARCH LOGIC AS METADATA TAGGER ===
        meta_results = []
        found_ratings = []  # Initialize for rating collection from all sources
        
        # Provider 1: Audnexus (Audible) - Primary
        use_audnexus = self.settings.get('metadata_use_audnexus', True) if self.settings else True
        if use_audnexus:
            self.log("Step 1: Trying Audnexus (Audible)...")
            asin, _ = audible_find_asin(self.session, query)
            if asin:
                self.log(f"Found ASIN via Internal Search: {asin}")
                audnexus_meta = provider_audnexus_by_asin(self.session, asin)
                if audnexus_meta:
                    meta_results.append(audnexus_meta)
                    rc = self._parse_count(audnexus_meta.rating_count)
                    self.log(f"✅ Audnexus Success! Found Rating: {audnexus_meta.rating} ({rc} votes)")
                    
                    # Check for low count, force scrape verification
                    try:
                        rc = self._parse_count(audnexus_meta.rating_count)
                        if rc < 50:
                            self.log("Audnexus count low. Attempting direct Audible scrape verification...")
                            url = f"https://www.audible.com/pd/{asin}"
                            scrape_meta = provider_audible_scrape(self.session, url)
                            if scrape_meta:
                                 src = self._parse_count(scrape_meta.rating_count)
                                 if src > rc:
                                     self.log(f"✅ Scrape Upgrade! Audnexus count {rc} -> {src}")
                                     # Update existing meta logic instead of removing
                                     audnexus_meta.rating_count = src
                                     audnexus_meta.rating = scrape_meta.rating 
                                 else:
                                     self.log("Scrape verified count (no improvement).")
                    except Exception as e:
                        self.log(f"Verification warning: {e}")

            
            # Fallback: DuckDuckGo external search if internal fails
            if not meta_results:
                self.log("Internal search failed. Trying Robust External Search (DuckDuckGo)...")
                query_str = f"{query.title} {query.author}".strip()
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
        else:
            self.log("Skipping Audnexus (Disabled in Settings).")
        
        # Provider 2: Google Books (Enrichment)
        use_google = self.settings.get('metadata_use_google', True) if self.settings else True
        if use_google:
            self.log("Step 2: Querying Google Books for enrichment...")
            api_key = self.settings.get('google_api_key', '') if self.settings else None
            google_meta = google_books_search(self.session, query, api_key=api_key)
            if google_meta:
                meta_results.append(google_meta)
                self.log(f"Google Books: Found '{google_meta.title}'")
            else:
                self.log("Google Books: No results")
        else:
            self.log("Skipping Google Books (Disabled in Settings).")
        
        # CONDITIONAL SCRAPING LOGIC (Waterfall Fallback)
        # If we already have high-quality vote data (Audnexus + Google), skip slow/fragile scraping.
        current_valid_votes = 0
        for m in meta_results:
             if m.rating_count:
                 current_valid_votes += self._parse_count(m.rating_count)
        
        SCRAPE_THRESHOLD = 50
        skip_scraping = False
        
        if current_valid_votes >= SCRAPE_THRESHOLD:
             self.log(f"High confidence data found ({current_valid_votes} votes). Skipping slow scraping (Goodreads/Amazon).")
             skip_scraping = True
        else:
             self.log(f"Low vote counts ({current_valid_votes} < {SCRAPE_THRESHOLD}). Enabling fallback scraping...")

        # Provider 3: Goodreads (Scraping)
        use_goodreads = self.settings.get('metadata_use_goodreads', True) if self.settings else True
        if use_goodreads and not skip_scraping:
            self.log("Step 3: Trying Goodreads (Scraping)...")
            gr_found = False
            try:
                query_str = f"{query.title} {query.author}".strip()
                # Use Direct Search instead of DDG
                gr_urls = search_goodreads_direct(query_str)
                for url in gr_urls:
                    self.log(f"Scanning Goodreads URL: {url}")
                    gr_data = scrape_goodreads_rating(self.session, url)
                    if gr_data:
                        self.log(f"✅ Goodreads Success! Found Rating: {gr_data['rating']} ({gr_data['count']:,} votes)")
                        gr_data["source"] = "Goodreads"
                        gr_data["count"] = self._parse_count(gr_data["count"])
                        found_ratings.append(gr_data)
                        gr_found = True
                        break
                if not gr_found and not gr_urls:
                     self.log(f"❌ Goodreads Search failed. No valid URLs found despite direct search.")
                     
            except Exception as e:
                self.log(f"Goodreads Error: {e}")
        elif skip_scraping:
            self.log("Skipping Goodreads (Sufficient data found).")
        else:
            self.log("Skipping Goodreads (Disabled in Settings).")

        # Provider 4: Amazon (Scraping)
        # Added per request for 4th source
        use_amazon = self.settings.get('metadata_use_amazon', True) if self.settings else True
        if use_amazon and not skip_scraping:
            self.log("Step 4: Trying Amazon (Scraping)...")
            amz_found = False
            try:
                 query_str = f"{query.title} {query.author} book"
                 amz_urls = search_duckduckgo_amazon(query_str)
                 for url in amz_urls:
                     self.log(f"Scanning Amazon URL: {url}")
                     amz_data = scrape_amazon_rating(self.session, url)
                     if amz_data:
                          self.log(f"✅ Amazon Success! Found Rating: {amz_data['rating']} ({amz_data['count']:,} ratings)")
                          amz_data['source'] = "Amazon"
                          found_ratings.append(amz_data)
                          amz_found = True
                          break
            except Exception as e:
                 self.log(f"Amazon Error: {e}")
        elif skip_scraping:
            self.log("Skipping Amazon (Sufficient data found).")
        else:
            self.log("Skipping Amazon (Disabled in Settings).")
             
        # If no metadata found from ANY provider
        if not meta_results and not gr_found and not amz_found:
            self.log("No metadata found from any source.")
            return None
        
        # Merge results from multiple sources (same as Tagger)
        # Note: Goodreads data is only for rating, we don't merge its metadata into the file tags yet
        # as it's just scraping rating/count.
        
        if not meta_results:
             # Fallback if only Goodreads found rating but no Tagger metadata
             # Create a skeleton meta from query
             base_meta = BookMeta(title=query.title, authors=[query.author] if query.author else [])
             self.log("Using basic query metadata (only Goodreads rating found).")
        elif len(meta_results) == 1:
            base_meta = meta_results[0]
            self.log(f"Match Found: '{base_meta.title}' via {base_meta.source}")
        else:
            self.log(f"Merging metadata from {len(meta_results)} sources...")
            base_meta = meta_results[0]  # Start with primary (usually Audnexus)
            for secondary in meta_results[1:]:
                base_meta = merge_metadata(base_meta, secondary)
            self.log(f"Merged Result: '{base_meta.title}' from {base_meta.source}")
        
        # === NOW DIVERGE FOR WEIGHTED RATING CALCULATION ===
        # Extract ratings from all valid sources (already initialized above)
        
        for meta in meta_results:
            if meta.rating:
                rc = self._parse_count(meta.rating_count)
                # Allow 0 count if rating is valid (Fix for Audnexus returning None count)
                if rc > 0 or (meta.rating and float(meta.rating) > 0):
                    found_ratings.append({
                        "source": meta.source,
                        "rating": float(meta.rating),
                        "count": rc
                    })
        
        if not found_ratings:
            self.log("No ratings found in metadata results.")
            return None
        
        # === BAYESIAN AVERAGE (IMDB Method) ===
        # Formula: BR = (v/(v+m)) × R + (m/(v+m)) × C
        # Where:
        #   v = number of votes for this book
        #   m = minimum votes required (damping factor)
        #   R = average rating for this book  
        #   C = baseline rating (assumed average)
        #
        # This accounts for sample size confidence:
        # - Books with few votes get pulled toward baseline
        # - Books with many votes stay close to actual rating
        
        BASELINE_RATING = 2.0  # Assume unproven book is Neutral/Low (2.0) to force proof of quality
        MIN_VOTES_REQUIRED = 500  # Damping factor: Increased to 500 to require more "proof" for high ratings
        
        bayesian_ratings = []
        total_count = sum(item["count"] for item in found_ratings)
        
        weighted_rating = 0.0

        if total_count == 0:
            # Special Case: No vote counts available (e.g. only Audnexus with missing count)
            # Fallback to Simple Average of Raw Ratings to prevent discarding valid data
            # or crushing it to 2.0 via Bayesian logic.
            raw_vals = [item["rating"] for item in found_ratings]
            weighted_rating = sum(raw_vals) / len(raw_vals)
            self.log(f"⚠️ No vote counts found (Total 0). Using Raw Average: {round(weighted_rating, 2)}")
        else:
            # Standard Bayesian Logic
            # Only process items with votes (v > 0) contribute to the weighted average
            # Items with v=0 technically contribute 0 weight so they are ignored here.
            
            for item in found_ratings:
                v = item["count"]
                
                # Skip 0-vote items in Bayesian Calc (they provide no confidence)
                if v == 0:
                    continue
                    
                R = item["rating"]
                
                # Apply Bayesian formula
                bayesian_rating = (v / (v + MIN_VOTES_REQUIRED)) * R + (MIN_VOTES_REQUIRED / (v + MIN_VOTES_REQUIRED)) * BASELINE_RATING
                
                bayesian_ratings.append({
                    "source": item["source"],
                    "original_rating": R,
                    "bayesian_rating": bayesian_rating,
                    "count": v
                })
            
            # Now calculate final weighted rating using Bayesian-adjusted ratings
            total_weight = 0.0
            processed_count = 0
            for item in bayesian_ratings:
                total_weight += (item["bayesian_rating"] * item["count"])
                processed_count += item["count"]
            
            if processed_count > 0:
                weighted_rating = total_weight / processed_count
            
        weighted_rating = round(weighted_rating, 2)
        
        # Unicode Bold digits for "Weighted Rating"
        # Map: 0-9 to 𝟎-𝟗 (Math Bold)
        def to_bold(s):
            # Standard ASCII digits to Mathematical Bold digits
            # 0 is 0x30, Bold 0 is 0x1D7CE
            # Offset is 0x1D7CE - 0x30 = 120782
            # But simple approach: replace char by char
            chars = "0123456789."
            bolds = "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗."
            trans = str.maketrans(chars, bolds)
            return s.translate(trans)

        bold_rating = to_bold(f"{weighted_rating:.2f}")
        
        self.log(f"Final Bayesian Weighted Rating: {weighted_rating}/5 ({total_count:,} total votes)")
        self.log(f"Algorithm: IMDB Bayesian Average (m={MIN_VOTES_REQUIRED}, C={BASELINE_RATING})")
        
        # Construct Description Header with Breakdown
        # ⭐️ Weighted Rating: 𝟒.𝟒𝟕/5
        #    • Audible: 4.5 (12,000 votes)
        #    • Google: 4.1 (6,000 votes)
        #    • Goodreads: 4.3 (15,000 votes)
        
        header_lines = [f"⭐️ Weighted Rating: {bold_rating}/5"]
        for item in found_ratings:
            source_name = item['source']
            # Normalize source names for user-friendly display
            source_lower = source_name.lower()
            if source_lower == "audnexus" or source_lower == "audible":
                source_name = "Audible"
            elif source_lower == "google_books" or source_lower == "google":
                source_name = "Google Books"
            elif source_lower == "goodreads":
                source_name = "Goodreads"
            elif source_lower == "amazon":
                source_name = "Amazon"
            
            header_lines.append(f"   • {source_name}: {item['rating']} ({item['count']:,} votes)")
            
        final_header = "\n".join(header_lines)
        
        # Update ATF with weighted data (DO NOT store BookMeta objects - not JSON serializable)
        # NEW STRUCTURE: Nest all rating data under 'ratings' key
        ratings_data = {
            "rating": str(weighted_rating),
            "rating_count": str(total_count),
            "rating_breakdown": found_ratings  # Only dict data, no BookMeta
        }
        
        if atf_data:
            atf_data["ratings"] = ratings_data
        else:
            atf_data = {
                "title": base_meta.title,
                "authors": base_meta.authors,  # Store as list
                "description": base_meta.description,
                "ratings": ratings_data
            }
             
        self.atf_handler.write_atf(directory, base_meta.title or "metadata", "SUCCESS", atf_data)
        self.log("Updated ATF cache.")
        
        # Return a special meta object with the pre-formatted header as "rating" 
        # (hacky but efficient for passing to _update_files_in_dir)
        # Actually, let's just pass the final header directly to _update_files_in_dir
        base_meta.rating = str(weighted_rating)
        base_meta.rating_count = str(total_count)
        base_meta._custom_header = final_header 
        
        return base_meta
        
    def _parse_count(self, count_str):
        if not count_str: return 0
        try:
            return int(str(count_str).replace(",", "").replace(".", ""))
        except:
            return 0

    def _update_files_in_dir(self, directory: str, meta: BookMeta):
        """
        Updates Description tag of supported files in directory using Line 1 Rule.
        """
        extensions = ('.mp3', '.m4a', '.m4b', '.opus', '.ogg')
        files = [f for f in os.listdir(directory) if f.lower().endswith(extensions) and not f.startswith("._")]
        
        if not files: return
        
        # Use custom header if available (from weighted calc), else standard
        header = getattr(meta, "_custom_header", None)
        if not header:
            # Fallback for standard meta objects
            r_val = float(meta.rating)
            header = f"⭐️ Rating: {r_val}/5"
            if meta.rating_count:
                try:
                    rc = int(str(meta.rating_count).replace(",", ""))
                    header += f" ({rc:,} reviews)"
                except:
                    header += f" ({meta.rating_count} reviews)"
        
        # Debug: Show header line-by-line
        self.log(f"Rating Header ({len(header.splitlines())} lines):")
        for i, line in enumerate(header.splitlines(), 1):
            self.log(f"  L{i}: {line}")
        

        # Calculate Grouping Tag
        # Logic: 4+: "Book Rated 4+", 3-3.99: "Book Rated 3+", 2-2.99: "Book Rated 2+"
        # Remove all if < 2
        rating_val = float(meta.rating)
        grouping_tag = None
        if rating_val >= 4.0:
            grouping_tag = "4+ Rated Books"
        elif rating_val >= 3.0:
            grouping_tag = "3+ Rated Books"
        elif rating_val >= 2.0:
            grouping_tag = "2+ Rated Books"
        
        count = 0
        
        # Determine strict sequential or parallel based on file count
        # For small number of files, overhead of threads might not be worth it
        # But for 7000 files, it is essential.
        if len(files) > 10:
             self.log(f"Updating {len(files)} files in parallel...")
             with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 10) as file_executor:
                 futures = []
                 for f in files:
                     path = os.path.join(directory, f)
                     futures.append(file_executor.submit(self._safe_apply_rating, path, header, grouping_tag))
                 
                 for future in concurrent.futures.as_completed(futures):
                     if future.result():
                         count += 1
        else:
            # Sequential for small batches
            for f in files:
                path = os.path.join(directory, f)
                if self._safe_apply_rating(path, header, grouping_tag):
                    count += 1
        
        self.log(f"Updated {count} files with rating header and grouping tag in {os.path.basename(directory)}.")

    def _safe_apply_rating(self, path, header, grouping_tag):
        try:
            self._apply_rating_to_file(path, header, grouping_tag)
            return True
        except Exception as e:
            import traceback
            self.log(f"❌ FAILED to update {os.path.basename(path)}")
            self.log(f"   Error: {e}")
            self.log(f"   Traceback: {traceback.format_exc()}")
            return False

    def _apply_rating_to_file(self, path: str, new_header: str, grouping_tag: str = None):
        """
        Reads file, modifies description using Line 1 Rule, and updates Grouping tag.
        """
        ext = os.path.splitext(path)[1].lower()
        
        # Logic to update tag list (for Grouping and Genre)
        def update_tag_list(current_list, new_tag):
            # 1. Remove ANY existing "Book Rated X+" tags
            # We look for specific pattern "Book Rated [2345]\+" to be safe
            clean_list = []
            if current_list:
                for item in current_list:
                    # Clean up if it's a single string with semicolons (often case for Genre)
                    sub_items = [s.strip() for s in str(item).split(';') if s.strip()]
                    for sub in sub_items:
                        # Regex handles: "Book Rated X+", "Books Rated X+", "X+ Rated Books"
                        if not re.match(r"^(Books? Rated [0-9]+\+|[0-9]+\+ Rated Books?)$", sub, re.IGNORECASE):
                            clean_list.append(sub)
            
            # 2. Add new tag if provided (PREPEND)
            if new_tag:
                 # Check if already exists (shouldn't be in clean_list due to regex, but safety check)
                 if new_tag not in clean_list:
                     clean_list.insert(0, new_tag)
            
            return clean_list

        # --- MP3 ---
        if ext == '.mp3':
            audio = ID3(path)
            # Find COMM frame
            comm_frames = [f for f in audio.values() if isinstance(f, COMM)]
            # Use 'eng' or first found, or create new
            target_frame = None
            if comm_frames:
                # Prefer one with description content
                target_frame = comm_frames[0]
                for f in comm_frames:
                    if f.text:
                        target_frame = f
                        break
            
            old_comment = ""
            if target_frame:
                old_comment = target_frame.text[0] if target_frame.text else ""
            
            new_comment = self._prepend_rating(old_comment, new_header)
            
            # Save to Comment tag - Clear all existing COMM frames first to avoid duplicates
            audio.delall("COMM")
            audio.add(COMM(encoding=3, lang='eng', desc='', text=[new_comment]))
            self.log(f"---> Wrote MP3 Comment (first 100 chars): {new_comment[:100]}...")
            
            # Grouping (TIT1)
            current_grouping = []
            if "TIT1" in audio:
                current_grouping = audio["TIT1"].text
            
            new_grouping = update_tag_list(current_grouping, grouping_tag)
            
            if new_grouping:
                # User preference: Join with semicolon to ensure visibility as "Old; New"
                grp_str = "; ".join(new_grouping)
                self.log(f"--> Writing MP3 Grouping: {grp_str}")
                audio.add(TIT1(encoding=3, text=[grp_str]))
            elif "TIT1" in audio:
                self.log(f"--> Removing MP3 Grouping")
                audio.delall("TIT1")
                
            audio.save()
            self.log(f"✅ MP3 Saved: {os.path.basename(path)}")


        # --- MP4 ---
        elif ext in ('.m4a', '.m4b'):
             audio = MP4(path)
             # Use \u00a9cmt (Comment) tag for rating data
             old_comment = ""
             if '\u00a9cmt' in audio:
                 old_comment = audio['\u00a9cmt'][0]
             
             new_comment = self._prepend_rating(old_comment, new_header)
             audio['\u00a9cmt'] = [new_comment]
             
             # Grouping (\u00a9grp)
             current_grouping = []
             if "\u00a9grp" in audio:
                 val = audio["\u00a9grp"]
                 if isinstance(val, list):
                     current_grouping = val
                 else:
                     current_grouping = [str(val)]
                     
             new_grouping = update_tag_list(current_grouping, grouping_tag)
             
             if new_grouping:
                # User preference: Join with semicolon to ensure visibility as "Old; New"
                grp_str = "; ".join(new_grouping)
                self.log(f"--> Writing MP4 Grouping: {grp_str}")
                audio["\u00a9grp"] = [grp_str]
             elif "\u00a9grp" in audio:
                self.log(f"--> Removing MP4 Grouping")
                del audio["\u00a9grp"]

             audio.save()
             
             # Verify Write
             try:
                 check = MP4(path)
                 if "\u00a9grp" in check:
                     self.log(f"    [Verify] Saved Grouping: {check['\u00a9grp'][0]}")
                 else:
                     self.log(f"    [Verify] No Grouping tag found after save.")
             except:
                 pass

        # --- OPUS ---
        elif ext in ('.opus', '.ogg'):
             audio = OggOpus(path)
             # Use COMMENT tag
             old_comment = ""
             if 'COMMENT' in audio:
                 old_comment = audio['COMMENT'][0]
                 
             new_comment = self._prepend_rating(old_comment, new_header)
             audio['COMMENT'] = [new_comment]
             
             # Grouping (grouping)
             current_grouping = []
             if "grouping" in audio:
                 current_grouping = audio["grouping"] # OggOpus returns list
                 
             new_grouping = update_tag_list(current_grouping, grouping_tag)
             
             if new_grouping:
                 # User preference: Join with semicolon to ensure visibility as "Old; New"
                 grp_str = "; ".join(new_grouping)
                 self.log(f"--> Writing Opus Grouping: {grp_str}")
                 audio['grouping'] = [grp_str]
             elif "grouping" in audio:
                 self.log(f"--> Removing Opus Grouping")
                 del audio['grouping']
             
             audio.save()

    def _prepend_rating(self, current_text: str, new_header: str) -> str:
        """
        Prepends rating header to existing comment text.
        If existing content already has a rating block, replace it.
        Otherwise, prepend new rating with separator.
        """
        if not current_text:
            return new_header
            
        lines = current_text.split('\n')
        
        # Check if first line is already a rating block
        if lines[0].strip().startswith(("⭐️ Rating:", "⭐️ Weighted Rating:")):
            # Find end of rating block (lines starting with "   •")
            end_idx = 1
            while end_idx < len(lines) and lines[end_idx].strip().startswith("•"):
                end_idx += 1
            
            # Replace old rating block with new one
            remaining_text = '\n'.join(lines[end_idx:]).strip()
            if remaining_text:
                return f"{new_header}\n\n{remaining_text}"
            else:
                return new_header
        else:
            # Prepend rating to existing content
            return f"{new_header}\n\n{current_text}"

    def _rewrite_description(self, current_text: str, new_header: str) -> str:
        """
        Apply Line 1 Rule:
        - Checks for EXISTING rating block (which might be multi-line now).
        - Replaces it or prepends.
        """
        if not current_text:
            return new_header
            
        lines = current_text.split('\n')
        
        # We need to detect if multiple lines at start constitute a rating block
        # Pattern: Starts with "⭐️ Rating:" or "⭐️ Weighted Rating:"
        # And subsequent lines start with "   •"
        
        start_idx = 0
        end_idx = 0
        
        if lines[0].strip().startswith(("⭐️ Rating:", "⭐️ Weighted Rating:")):
            # Found header start
            end_idx = 1
            # Check for breakdown lines
            while end_idx < len(lines) and lines[end_idx].strip().startswith("•"):
                end_idx += 1
            
            # Replace [start_idx : end_idx] with new_header
            # Note: new_header includes newlines
            
            rest_of_desc = lines[end_idx:]
            # Ensure proper spacing
            while rest_of_desc and not rest_of_desc[0].strip():
                rest_of_desc.pop(0) # Remove leading blank lines
                
            return f"{new_header}\n\n" + "\n".join(rest_of_desc)
            
        else:
            # Prepend
            return f"{new_header}\n\n{current_text}"
