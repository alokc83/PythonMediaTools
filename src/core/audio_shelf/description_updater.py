import os
import re
import requests
import json
import concurrent.futures
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

class DescriptionUpdaterEngine:
    def __init__(self, settings_manager=None, log_callback: Callable[[str], None] = None):
        self.session = make_session()
        self.atf_handler = ATFHandler()
        self.settings = settings_manager 
        self.log_callback = log_callback or (lambda x: None)

    def log(self, msg: str):
        self.log_callback(msg)

    def scan_and_update(self, directories: List[str], progress_callback: Callable[[int, int], None] = None):
        """
        Main entry point for batch updating.
        """
        book_dirs = []
        for d in directories:
            if not os.path.exists(d): continue
            found = self._find_audio_directories(d)
            if found:
                book_dirs.extend(found)
            else:
                self.log(f"No audio files found in {os.path.basename(d)}.")

        total = len(book_dirs)
        self.log(f"Found {total} audio directories to process.")
        
        self.log(f"Starting parallel processing with 5 workers...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i, directory in enumerate(book_dirs):
                futures.append(executor.submit(self._process_book, directory, i + 1, total))
            
            completed_count = 0
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    self.log(f"Thread Error: {e}")
                
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, total)

    def _find_audio_directories(self, root_path: str) -> List[str]:
        audio_dirs = []
        EXTENSIONS = ('.mp3', '.m4a', '.m4b', '.opus', '.ogg')
        for root, dirs, files in os.walk(root_path):
            if any(f.lower().endswith(EXTENSIONS) and not f.startswith("._") for f in files):
                audio_dirs.append(root)
        return audio_dirs

    def _process_book(self, directory, idx, total):
        try:
            self.log(f"\n--- Processing Book {idx}/{total}: {os.path.basename(directory)} ---")
            
            # Fetch Metadata (Using same robust logic as RatingUpdater)
            meta = self._get_or_update_atf(directory)
            
            if meta and meta.description:
                self._update_files_in_dir(directory, meta)
            else:
                self.log(f"Skipping {os.path.basename(directory)}: No description found.")
                
        except Exception as e:
            self.log(f"Error processing {directory}: {e}")

    def _get_or_update_atf(self, directory: str) -> Optional[BookMeta]:
        """
        Reads ATF. If description is missing or force refresh is needed (future), fetches from API.
        For this tool, we will try to fetch fresh if ATF is missing description.
        """
        status, atf_data = self.atf_handler.read_atf(directory)
        
        # If we have a description in ATF, do we use it? 
        # User said "scrape the data as rating_updater does". 
        # RatingUpdater forces refresh. Let's force refresh for description too to ensure quality.
        
        self.log("Fetching fresh metadata for description...")
        
        # 1. Determine Query
        query = None
        if atf_data:
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
             
             # Strategy 3: Directory Name
             if not query:
                 dirname = os.path.basename(directory)
                 parts = dirname.split(" - ")
                 if len(parts) >= 2:
                     query = BookQuery(title=parts[1].strip(), author=parts[0].strip())
                 else:
                     query = BookQuery(title=dirname.strip(), author="")
        
        # Clean Query
        clean_title = re.sub(r"[\(\[].*?[\)\]]", "", query.title).strip()
        if clean_title != query.title:
            query.title = clean_title

        self.log(f"Searching for: {query.title} ({query.author})")
        
        if not query or not query.title:
            return None
        
        # === FETCH LOGIC (Similar to Tagger/RatingUpdater) ===
        meta_results = []
        
        # 1. Audnexus
        if self.settings.get('metadata_use_audnexus', True):
            self.log("Step 1: Trying Audnexus...")
            asin, _ = audible_find_asin(self.session, query)
            if asin:
                audnexus_meta = provider_audnexus_by_asin(self.session, asin)
                if audnexus_meta:
                    meta_results.append(audnexus_meta)
                    self.log("✅ Audnexus Success!")
            
            if not meta_results:
                 # Fallback External Search
                 self.log("Internal search failed. Trying External Search...")
                 query_str = f"{query.title} {query.author}".strip()
                 found_urls = search_duckduckgo_audible(query_str)
                 for url in found_urls:
                    found_asin = extract_asin_from_url(url)
                    if found_asin:
                        audnexus_meta = provider_audnexus_by_asin(self.session, found_asin)
                        if audnexus_meta:
                            meta_results.append(audnexus_meta)
                            break
                    if not meta_results: # Fallback Scrape
                         scrape_meta = provider_audible_scrape(self.session, url)
                         if scrape_meta:
                             meta_results.append(scrape_meta)
                             break

        # 2. Google Books
        if self.settings.get('metadata_use_google', True):
            self.log("Step 2: Querying Google Books...")
            api_key = self.settings.get('google_api_key', '')
            google_meta = google_books_search(self.session, query, api_key=api_key)
            if google_meta:
                meta_results.append(google_meta)
        
        # Merge
        if not meta_results:
            self.log("No metadata found.")
            return None
            
        base_meta = meta_results[0]
        for secondary in meta_results[1:]:
             base_meta = merge_metadata(base_meta, secondary)
             
        self.log(f"Merged Metadata. Description Length: {len(base_meta.description)}")
        
        # Update ATF (Keep existing ratings if any)
        if atf_data:
            atf_data["description"] = base_meta.description
        else:
            atf_data = {
                "title": base_meta.title,
                "authors": base_meta.authors,
                "description": base_meta.description,
                "ratings": {} # Placeholder
            }
        
        self.atf_handler.write_atf(directory, base_meta.title or "metadata", "SUCCESS", atf_data)
        
        return base_meta

    def _update_files_in_dir(self, directory: str, meta: BookMeta):
        extensions = ('.mp3', '.m4a', '.m4b', '.opus', '.ogg')
        files = [f for f in os.listdir(directory) if f.lower().endswith(extensions) and not f.startswith("._")]
        
        if not files: return
        
        count = 0
        if len(files) > 10:
             with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 10) as file_executor:
                 futures = []
                 for f in files:
                     path = os.path.join(directory, f)
                     futures.append(file_executor.submit(self._safe_apply_desc, path, meta.description))
                 
                 for future in concurrent.futures.as_completed(futures):
                     if future.result(): count += 1
        else:
            for f in files:
                path = os.path.join(directory, f)
                if self._safe_apply_desc(path, meta.description):
                    count += 1
        
        self.log(f"Updated {count} files in {os.path.basename(directory)}.")

    def _safe_apply_desc(self, path, description):
        try:
            self._apply_description_to_file(path, description)
            return True
        except Exception as e:
            self.log(f"Failed to update {os.path.basename(path)}: {e}")
            return False

    def _apply_description_to_file(self, path: str, new_description: str):
        """
        Reads file, PRESERVES EXISTING RATING HEADER, and appends new description.
        """
        if not new_description: return

        def merge_text(current_text, new_desc):
            if not current_text:
                return new_desc
            
            lines = current_text.split('\n')
            
            # Check for Rating Block at start
            has_rating = False
            end_idx = 0
            
            if lines[0].strip().startswith(("⭐️ Rating:", "⭐️ Weighted Rating:")):
                has_rating = True
                end_idx = 1
                while end_idx < len(lines) and lines[end_idx].strip().startswith("•"):
                    end_idx += 1
                
                # Check for blank lines after rating block
                while end_idx < len(lines) and not lines[end_idx].strip():
                     end_idx += 1
            
            if has_rating:
                # Keep the rating block [0:end_idx]
                rating_block = "\n".join(lines[:end_idx]).strip()
                # Return Rating Block + New Description
                return f"{rating_block}\n\n{new_description}"
            else:
                # No rating detected, currently we OVERWRITE the description if we are updating description.
                # User's logic: "If comment was empty then proceed as normal" (Write Description).
                # But if comment has "Junk" or old description?
                # User: "if file already have first line as rating... append... if comment was empty proceed normal"
                # Implication: If it has something else, we overwrite it with fresh description?
                # "We are not replacing it but append... if comment was empty then proceed as normal."
                # I will assume we OVERWRITE old descriptions that are NOT ratings.
                return new_description

        ext = os.path.splitext(path)[1].lower()
        
        # --- MP3 ---
        if ext == '.mp3':
            audio = ID3(path)
            # Find COMM with desc="" (Default) or desc="Description"
            # We want to write to the SAME frame we read from, preferably default.
            
            target_frame = None
            comm_frames = [f for f in audio.values() if isinstance(f, COMM)]
            if comm_frames:
                # logic to pick best frame: empty desc preferred
                for f in comm_frames:
                    if f.desc == "": 
                        target_frame = f; break
                if not target_frame:
                    target_frame = comm_frames[0]
            
            old_comment = target_frame.text[0] if target_frame and target_frame.text else ""
            final_comment = merge_text(old_comment, new_description)
            
            # Write back to standard COMM
            audio.add(COMM(encoding=3, lang='eng', desc='', text=[final_comment]))
            audio.save()

        # --- MP4 ---
        elif ext in ('.m4a', '.m4b'):
             audio = MP4(path)
             # Check \u00a9cmt (Comment) AND desc (Description)
             # Priority: Comment
             old_comment = ""
             if '\u00a9cmt' in audio:
                 old_comment = audio['\u00a9cmt'][0]
             elif 'desc' in audio: # Fallback to existing desc
                 old_comment = audio['desc'][0]
             
             final_comment = merge_text(old_comment, new_description)
             
             # Write to BOTH
             audio['\u00a9cmt'] = [final_comment]
             audio['desc'] = [final_comment]
             audio.save()

        # --- OPUS ---
        elif ext in ('.opus', '.ogg'):
             audio = OggOpus(path)
             old_comment = ""
             if 'COMMENT' in audio:
                 old_comment = audio['COMMENT'][0]
             elif 'DESCRIPTION' in audio:
                 old_comment = audio['DESCRIPTION'][0]
                 
             final_comment = merge_text(old_comment, new_description)
             audio['COMMENT'] = [final_comment]
             # audio['DESCRIPTION'] = [final_comment] # Standard is COMMENT usually for Ogg
             audio.save()
