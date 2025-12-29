#!/usr/bin/env python3
import os
import sys
import re
import shutil
import subprocess
import urllib.parse
import requests
from io import BytesIO
from datetime import datetime
from tqdm import tqdm
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TIT2, TALB, TCON, APIC, error
from mutagen.mp4 import MP4
from PIL import Image
from bs4 import BeautifulSoup

# Global configuration
ALLOWED_EXT = {".mp3"}
use_parent_genre = False  # Set based on user input later

def print_script_info():
    info = """
=======================================================================
This script processes MP3 files in a specified folder as follows:

  1. Metadata Update:
     - Reads and updates the MP3 metadata.
     - Fills missing Title (TIT2) and Album (TALB) tags using available values or the file name.
     - Optionally sets Genre (TCON) from the parent folder name.
     - Checks for cover art (APIC) and ensures it is high quality (>=800×800 pixels).
       If missing or low quality, it attempts to fetch a high-quality cover via a fallback
       chain: Blinkist → Audible → Goodreads → Google Books API.

  2. Conversion:
     Converts updated MP3 files to M4A using ffmpeg.

  3. Grouping:
     Organizes the original MP3 files and converted M4A files into subfolders "mp3" and "m4a".

Note: This script requires ffmpeg and the following Python packages:
      mutagen, tqdm, requests, beautifulsoup4, pillow.
=======================================================================
    """
    print(info)
    answer = input("Do you want to run this script? (y/n): ").strip().lower()
    if answer != "y":
        print("Exiting.")
        sys.exit(0)

def normalize_path(p):
    return p.replace("\\ ", " ").replace("\\(", "(").replace("\\)", ")")

def sizeof_fmt(num, suffix='B'):
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} Y{suffix}"

def get_audio_title(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    title = None
    if ext == ".mp3":
        try:
            audio = EasyID3(file_path)
            title = audio.get("title", [None])[0]
            if not title or title.strip() == "":
                title = audio.get("album", [None])[0]
        except Exception as e:
            sys.stdout.write(f"\nError reading MP3 metadata for '{file_path}': {e}\n")
            return None
    else:
        return None
    return title.strip() if title else None

def get_all_files(folder, allowed_extensions=None):
    file_list = []
    for root, dirs, files in os.walk(folder):
        for file in files:
            if allowed_extensions and file.lower().endswith(tuple(allowed_extensions)):
                file_list.append(os.path.join(root, file))
            elif not allowed_extensions:
                file_list.append(os.path.join(root, file))
    return file_list

def check_image_quality(image_bytes):
    try:
        im = Image.open(BytesIO(image_bytes))
        width, height = im.size
        return width >= 800 and height >= 800
    except Exception:
        return False

def process_metadata(operation_folder):
    mp3_files = get_all_files(operation_folder, ALLOWED_EXT)
    for file_path in tqdm(mp3_files, desc="Updating Metadata", unit="file"):
        confirm = input(f"Update metadata for '{file_path}'? (y/n): ").strip().lower()
        if confirm != "y":
            tqdm.write("Skipping this file.")
            continue
        title = get_audio_title(file_path)
        if not title:
            title = os.path.splitext(os.path.basename(file_path))[0]
        try:
            try:
                tags = ID3(file_path)
            except error:
                tags = ID3()
            current_title = tags.get("TIT2")
            current_album = tags.get("TALB")
            if not current_title and current_album:
                tags.add(TIT2(encoding=3, text=current_album.text))
            elif not current_album and current_title:
                tags.add(TALB(encoding=3, text=current_title.text))
            elif not current_title and not current_album:
                basename = os.path.splitext(os.path.basename(file_path))[0]
                tags.add(TIT2(encoding=3, text=[basename]))
                tags.add(TALB(encoding=3, text=[basename]))
            # Update Genre if missing and if opted.
            current_genre = tags.get("TCON")
            if (not current_genre or not current_genre.text or not current_genre.text[0].strip()) and use_parent_genre:
                parent_folder = os.path.basename(os.path.dirname(file_path))
                tags.add(TCON(encoding=3, text=[parent_folder]))
            # Cover Art: Check if cover art exists.
            if any(key.startswith("APIC") for key in tags.keys()):
                existing_cover = tags.getall("APIC")[0].data
                if not check_image_quality(existing_cover):
                    tqdm.write(f"[DEBUG] Existing cover art for '{title}' is low quality.")
                    answer_refetch = input(f"Re-fetch high-quality cover art for '{title}'? (y/n): ").strip().lower()
                    if answer_refetch == "y":
                        cover = fetch_album_cover(title)
                        if cover and check_image_quality(cover):
                            tqdm.write("[DEBUG] High-quality cover art successfully fetched.")
                            tags.delall("APIC")
                            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
                        else:
                            answer_continue = input(f"Failed to fetch high-quality cover art for '{file_path}'. Continue processing? (y/n): ").strip().lower()
                            if answer_continue != "y":
                                sys.exit(0)
                    else:
                        tqdm.write("[DEBUG] Keeping existing low-quality cover art.")
            else:
                tqdm.write(f"[DEBUG] Cover art missing for '{title}'.")
                answer_fetch = input(f"Fetch cover art for '{title}'? (y/n): ").strip().lower()
                if answer_fetch == "y":
                    cover = fetch_album_cover(title)
                    if cover and check_image_quality(cover):
                        tqdm.write("[DEBUG] Cover art successfully fetched.")
                        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
                    else:
                        answer_continue = input(f"Failed to fetch high-quality cover art for '{file_path}'. Continue processing? (y/n): ").strip().lower()
                        if answer_continue != "y":
                            sys.exit(0)
                else:
                    tqdm.write("[DEBUG] Skipping cover art fetching for this file.")
            tags.save(file_path)
        except Exception as e:
            sys.stdout.write(f"\nError updating metadata for '{file_path}': {e}\n")
    return mp3_files

def fetch_album_cover(title):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://www.blinkist.com/"
    }
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug).strip('-')
    if not slug.endswith("-en"):
        slug = slug + "-en"
    blinkist_url = f"https://www.blinkist.com/en/books/{slug}"
    tqdm.write(f"[DEBUG] Trying Blinkist URL: {blinkist_url}")
    try:
        r = requests.get(blinkist_url, headers=headers, timeout=10)
        tqdm.write(f"[DEBUG] Blinkist HTTP status: {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            # Look for the specific div containing the cover image URL in its style attribute.
            div = soup.find("div", class_=lambda c: c and "rounded-md" in c)
            if div:
                style = div.get("style", "")
                match = re.search(r"url\((.*?)\)", style)
                if match:
                    cover_url = match.group(1).strip().strip("'\"")
                    tqdm.write(f"[DEBUG] Blinkist cover URL extracted from div: {cover_url}")
                    r2 = requests.get(cover_url, headers=headers, timeout=10)
                    tqdm.write(f"[DEBUG] Blinkist cover fetch status: {r2.status_code}")
                    if r2.status_code == 200 and check_image_quality(r2.content):
                        return r2.content
                    else:
                        tqdm.write("[DEBUG] Blinkist cover fetched but quality is insufficient.")
            else:
                # Fallback: try using the og:image meta tag.
                meta = soup.find("meta", property="og:image")
                if meta and meta.get("content"):
                    cover_url = meta.get("content")
                    tqdm.write(f"[DEBUG] Blinkist fallback og:image URL: {cover_url}")
                    r2 = requests.get(cover_url, headers=headers, timeout=10)
                    tqdm.write(f"[DEBUG] Blinkist fallback fetch status: {r2.status_code}")
                    if r2.status_code == 200 and check_image_quality(r2.content):
                        return r2.content
                    else:
                        tqdm.write("[DEBUG] Blinkist fallback cover fetched but quality is insufficient.")
    except Exception as e:
        tqdm.write(f"[DEBUG] Blinkist failed: {e}")
    
    tqdm.write("[DEBUG] Falling back to Audible search for cover art...")
    try:
        search_url = f"https://www.audible.com/search?keywords={urllib.parse.quote(title)}"
        r = requests.get(search_url, headers=headers, timeout=10)
        tqdm.write(f"[DEBUG] Audible HTTP status: {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            img = soup.find("img")
            if img and img.get("src"):
                cover_url = img.get("src")
                tqdm.write(f"[DEBUG] Audible cover URL: {cover_url}")
                r2 = requests.get(cover_url, headers=headers, timeout=10)
                tqdm.write(f"[DEBUG] Audible cover fetch status: {r2.status_code}")
                if r2.status_code == 200 and check_image_quality(r2.content):
                    return r2.content
                else:
                    tqdm.write("[DEBUG] Audible cover fetched but quality is insufficient.")
    except Exception as e:
        tqdm.write(f"[DEBUG] Audible search failed: {e}")
    
    tqdm.write("[DEBUG] Falling back to Goodreads search for cover art...")
    try:
        search_url = f"https://www.goodreads.com/search?q={urllib.parse.quote(title)}"
        r = requests.get(search_url, headers=headers, timeout=10)
        tqdm.write(f"[DEBUG] Goodreads HTTP status: {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            img = soup.find("img", {"class": "bookCover"})
            if img and img.get("src"):
                cover_url = img.get("src")
                tqdm.write(f"[DEBUG] Goodreads cover URL: {cover_url}")
                r2 = requests.get(cover_url, headers=headers, timeout=10)
                tqdm.write(f"[DEBUG] Goodreads cover fetch status: {r2.status_code}")
                if r2.status_code == 200 and check_image_quality(r2.content):
                    return r2.content
                else:
                    tqdm.write("[DEBUG] Goodreads cover fetched but quality is insufficient.")
    except Exception as e:
        tqdm.write(f"[DEBUG] Goodreads search failed: {e}")
    
    tqdm.write("[DEBUG] Falling back to Google Books API for cover art...")
    try:
        query = f"intitle:{title}"
        google_books_url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(query)}"
        tqdm.write(f"[DEBUG] Google Books API URL: {google_books_url}")
        r = requests.get(google_books_url, timeout=10)
        tqdm.write(f"[DEBUG] Google Books HTTP status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if "items" in data and len(data["items"]) > 0:
                volume_info = data["items"][0].get("volumeInfo", {})
                image_links = volume_info.get("imageLinks", {})
                for key in ["extraLarge", "large", "medium", "small", "thumbnail", "smallThumbnail"]:
                    if key in image_links:
                        cover_url = image_links[key]
                        tqdm.write(f"[DEBUG] Google Books cover URL from key '{key}': {cover_url}")
                        r2 = requests.get(cover_url, timeout=10)
                        tqdm.write(f"[DEBUG] Google Books cover fetch status: {r2.status_code}")
                        if r2.status_code == 200 and check_image_quality(r2.content):
                            return r2.content
                        else:
                            tqdm.write(f"[DEBUG] Google Books cover from key '{key}' failed quality check.")
    except Exception as e:
        tqdm.write(f"[DEBUG] Google Books API search failed: {e}")
    
    tqdm.write("[DEBUG] No suitable cover art found.")
    return None

def get_unique_dest_path(dest_folder, filename):
    dest_path = os.path.join(dest_folder, filename)
    if not os.path.exists(dest_path):
        return dest_path
    base, ext = os.path.splitext(filename)
    counter = 1
    while True:
        new_filename = f"{base}_{counter}{ext}"
        dest_path = os.path.join(dest_folder, new_filename)
        if not os.path.exists(dest_path):
            return dest_path
        counter += 1

def convert_mp3_to_m4a(mp3_files):
    conversions = []
    for mp3_file in tqdm(mp3_files, desc="Converting MP3 to M4A", unit="file"):
        base, _ = os.path.splitext(mp3_file)
        m4a_file = base + ".m4a"
        if os.path.exists(m4a_file):
            conversions.append((mp3_file, m4a_file))
            continue
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", mp3_file, "-c:a", "aac", "-b:a", "128k", m4a_file],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if result.returncode == 0 and os.path.exists(m4a_file):
                conversions.append((mp3_file, m4a_file))
            else:
                tqdm.write(f"Conversion failed for {mp3_file}: {result.stderr.decode('utf-8')}")
        except Exception as e:
            tqdm.write(f"Error converting {mp3_file} to M4A: {e}")
    return conversions

def group_files(operation_folder, conversion_list):
    mp3_folder = os.path.join(operation_folder, "mp3")
    m4a_folder = os.path.join(operation_folder, "m4a")
    os.makedirs(mp3_folder, exist_ok=True)
    os.makedirs(m4a_folder, exist_ok=True)
    for mp3_file, m4a_file in conversion_list:
        try:
            shutil.move(mp3_file, os.path.join(mp3_folder, os.path.basename(mp3_file)))
            shutil.move(m4a_file, os.path.join(m4a_folder, os.path.basename(m4a_file)))
            tqdm.write(f"Moved {os.path.basename(mp3_file)} to 'mp3' and {os.path.basename(m4a_file)} to 'm4a'")
        except Exception as e:
            tqdm.write(f"Error moving files for {mp3_file}: {e}")

def update_metadata_from_audible(file_path):
    """
    Fetch additional metadata from Audible using the local title.
    Updates local ID3 tags (for example, release date and summary) and attempts to update cover art.
    This function uses a simplified version of Audible scraping logic.
    """
    meta = fetch_audible_metadata(get_audio_title(file_path))
    if meta is None:
        tqdm.write(f"[DEBUG] No Audible metadata found for '{get_audio_title(file_path)}'.")
        return
    try:
        tags = ID3(file_path)
    except error:
        tags = ID3()
    if meta.get("title"):
        tags.add(TIT2(encoding=3, text=[meta["title"]]))
    if meta.get("release_date"):
        try:
            tags.add(TDRC(encoding=3, text=[meta["release_date"].strftime("%Y-%m-%d")]))
        except Exception:
            pass
    if meta.get("summary"):
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Summary", data=meta["summary"].encode('utf-8')))
    if meta.get("studio"):
        tags.add(TALB(encoding=3, text=[meta["studio"]]))
    if meta.get("cover"):
        r2 = requests.get(meta["cover"], timeout=10)
        if r2.status_code == 200 and check_image_quality(r2.content):
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=r2.content))
    tags.save(file_path)
    tqdm.write(f"[DEBUG] Updated metadata from Audible for '{get_audio_title(file_path)}'.")

def fetch_audible_metadata(title):
    """
    Uses Audible search to retrieve additional metadata.
    This is a simplified version that:
      - Searches Audible for the title.
      - Fetches the first result's detail page.
      - Extracts metadata fields such as release date, studio, summary, author.
    Returns a dictionary of metadata or None if not found.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    search_url = "https://www.audible.com/search?keywords=" + urllib.parse.quote(title)
    try:
        r = requests.get(search_url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        result_link = soup.find("a", href=re.compile(r'/pd/'))
        if not result_link:
            return None
        detail_url = "https://www.audible.com" + result_link['href']
        r2 = requests.get(detail_url, headers=headers, timeout=10)
        if r2.status_code != 200:
            return None
        soup2 = BeautifulSoup(r2.text, "html.parser")
        metadata = {}
        h1 = soup2.find("h1")
        metadata["title"] = h1.get_text(strip=True) if h1 else title
        date_span = soup2.find("span", text=re.compile(r'Release date', re.I))
        if date_span:
            date_str = date_span.find_next_sibling(text=True)
            try:
                metadata["release_date"] = datetime.strptime(date_str.strip(), "%B %d, %Y").date()
            except Exception:
                metadata["release_date"] = None
        else:
            metadata["release_date"] = None
        studio_span = soup2.find("span", text=re.compile(r'Publisher', re.I))
        metadata["studio"] = studio_span.find_next_sibling(text=True).strip() if studio_span else ""
        synopsis_div = soup2.find("div", class_=re.compile(r'(synopsis|ProductSynopsis)', re.I))
        metadata["summary"] = synopsis_div.get_text(" ", strip=True) if synopsis_div else ""
        cover_img = soup2.find("img", class_=re.compile(r'bc-image', re.I))
        metadata["cover"] = cover_img.get("src") if cover_img and cover_img.get("src") else None
        return metadata
    except Exception as e:
        tqdm.write(f"[DEBUG] Audible metadata fetch failed: {e}")
        return None

def get_unique_dest_path(dest_folder, filename):
    dest_path = os.path.join(dest_folder, filename)
    if not os.path.exists(dest_path):
        return dest_path
    base, ext = os.path.splitext(filename)
    counter = 1
    while True:
        new_filename = f"{base}_{counter}{ext}"
        dest_path = os.path.join(dest_folder, new_filename)
        if not os.path.exists(dest_path):
            return dest_path
        counter += 1

def convert_mp3_to_m4a(mp3_files):
    conversions = []
    for mp3_file in tqdm(mp3_files, desc="Converting MP3 to M4A", unit="file"):
        base, _ = os.path.splitext(mp3_file)
        m4a_file = base + ".m4a"
        if os.path.exists(m4a_file):
            conversions.append((mp3_file, m4a_file))
            continue
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", mp3_file, "-c:a", "aac", "-b:a", "128k", m4a_file],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if result.returncode == 0 and os.path.exists(m4a_file):
                conversions.append((mp3_file, m4a_file))
            else:
                tqdm.write(f"Conversion failed for {mp3_file}: {result.stderr.decode('utf-8')}")
        except Exception as e:
            tqdm.write(f"Error converting {mp3_file} to M4A: {e}")
    return conversions

def group_files(operation_folder, conversion_list):
    mp3_folder = os.path.join(operation_folder, "mp3")
    m4a_folder = os.path.join(operation_folder, "m4a")
    os.makedirs(mp3_folder, exist_ok=True)
    os.makedirs(m4a_folder, exist_ok=True)
    for mp3_file, m4a_file in conversion_list:
        try:
            shutil.move(mp3_file, os.path.join(mp3_folder, os.path.basename(mp3_file)))
            shutil.move(m4a_file, os.path.join(m4a_folder, os.path.basename(m4a_file)))
            tqdm.write(f"Moved {os.path.basename(mp3_file)} to 'mp3' and {os.path.basename(m4a_file)} to 'm4a'")
        except Exception as e:
            tqdm.write(f"Error moving files for {mp3_file}: {e}")

def main():
    print_script_info()
    
    operation_folder = input("Enter the folder path where the operation will be performed: ").strip()
    operation_folder = normalize_path(operation_folder)
    if not os.path.isdir(operation_folder):
        print(f"Error: '{operation_folder}' is not a valid directory.")
        sys.exit(0)
    print(f"\nOperation folder: {operation_folder}")
    
    global use_parent_genre
    answer = input("Do you want to use the parent folder name as Genre for MP3 files missing Genre? (y/n): ").strip().lower()
    use_parent_genre = (answer == "y")
    
    print("\nPhase 1: Updating metadata for MP3 files...")
    updated_mp3_files = process_metadata(operation_folder)
    if not updated_mp3_files:
        print("No MP3 files processed. Exiting.")
        sys.exit(0)
    else:
        print(f"Metadata updated for {len(updated_mp3_files)} MP3 files.")
    
    print("\nPhase 2: Converting MP3 files to M4A...")
    conversion_list = convert_mp3_to_m4a(updated_mp3_files)
    if not conversion_list:
        print("No MP3 files were converted.")
    else:
        print(f"Converted {len(conversion_list)} MP3 files to M4A.")
    
    print("\nPhase 3: Organizing files into 'mp3' and 'm4a' folders...")
    group_files(operation_folder, conversion_list)
    print("\nProcessing complete.")

if __name__ == "__main__":
    main()
