import os
import re
import requests
import json
from typing import List, Optional, Tuple, Callable

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, COMM
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
    def __init__(self, log_callback: Callable[[str], None] = None):
        self.session = make_session()
        self.atf_handler = ATFHandler()
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
        
        # 2. Process each book directory
        for i, directory in enumerate(book_dirs):
            self.log(f"\n--- Processing Book {i+1}/{total}: {os.path.basename(directory)} ---")
            
            try:
                # Get/Update ATF Metadata (Always fetches fresh as per rule)
                meta = self._get_or_update_atf(directory)
                
                if meta and meta.rating:
                    self._update_files_in_dir(directory, meta)
                else:
                    self.log("Skipping files: No rating found for this book.")
                    
            except Exception as e:
                self.log(f"Error processing {directory}: {e}")
            
            if progress_callback:
                progress_callback(i + 1, total)

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
        
        # Provider 2: Google Books (Enrichment)
        self.log("Step 2: Querying Google Books for enrichment...")
        google_meta = google_books_search(self.session, query)
        if google_meta:
            meta_results.append(google_meta)
            self.log(f"Google Books: Found '{google_meta.title}'")
        else:
            self.log("Google Books: No results")
        
        # Provider 3: Goodreads (Scraping)
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

        # Provider 4: Amazon (Scraping)
        # Added per request for 4th source
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
                if rc > 0:
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
        
        BASELINE_RATING = 4.0  # Assume median "good" book is 4.0
        MIN_VOTES_REQUIRED = 250  # Damping factor (tune based on your collection)
        
        bayesian_ratings = []
        total_count = 0
        
        for item in found_ratings:
            v = item["count"]  # votes for this source
            R = item["rating"]  # actual rating from this source
            
            # Apply Bayesian formula
            bayesian_rating = (v / (v + MIN_VOTES_REQUIRED)) * R + (MIN_VOTES_REQUIRED / (v + MIN_VOTES_REQUIRED)) * BASELINE_RATING
            
            bayesian_ratings.append({
                "source": item["source"],
                "original_rating": R,
                "bayesian_rating": bayesian_rating,
                "count": v
            })
            total_count += v
        
        # Now calculate final weighted rating using Bayesian-adjusted ratings
        total_weight = 0.0
        for item in bayesian_ratings:
            total_weight += (item["bayesian_rating"] * item["count"])
        
        weighted_rating = 0.0
        if total_count > 0:
            weighted_rating = total_weight / total_count
            
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
            if source_name == "Audnexus": source_name = "Audible"
            elif source_name == "google_books": source_name = "Google"
            
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
        
        count = 0
        for f in files:
            path = os.path.join(directory, f)
            try:
                self._apply_rating_to_file(path, header)
                count += 1
            except Exception as e:
                self.log(f"Failed to update {f}: {e}")
        
        self.log(f"Updated {count} files with rating header.")

    def _apply_rating_to_file(self, path: str, new_header: str):
        """
        Reads file, modifies description using Line 1 Rule, saves.
        """
        ext = os.path.splitext(path)[1].lower()
        
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
            
            # Save to Comment tag
            audio.add(COMM(encoding=3, lang='eng', desc='', text=[new_comment]))
            audio.save()

        # --- MP4 ---
        elif ext in ('.m4a', '.m4b'):
             audio = MP4(path)
             # Use ©cmt (Comment) tag for rating data
             old_comment = ""
             if '©cmt' in audio:
                 old_comment = audio['©cmt'][0]
             
             new_comment = self._prepend_rating(old_comment, new_header)
             audio['©cmt'] = [new_comment]
             audio.save()

        # --- OPUS ---
        elif ext in ('.opus', '.ogg'):
             audio = OggOpus(path)
             # Use COMMENT tag
             old_comment = ""
             if 'COMMENT' in audio:
                 old_comment = audio['COMMENT'][0]
                 
             new_comment = self._prepend_rating(old_comment, new_header)
             audio['COMMENT'] = [new_comment]
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
