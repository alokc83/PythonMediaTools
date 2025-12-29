#!/usr/bin/env python3
import os
import sys
import re
import shutil
import subprocess
import urllib.parse
import requests
from io import BytesIO
from tqdm import tqdm
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TIT2, TALB, TCON, APIC, error
from mutagen.mp4 import MP4
from PIL import Image

# We process MP3 files only (which will later be converted to M4A)
ALLOWED_EXT = {".mp3"}
use_parent_genre = False  # Global flag

def print_script_info():
    info = """
    =======================================================================
    This script processes MP3 files in a specified folder as follows:
    
      1. Metadata Update:
         - Updates the MP3 metadata by ensuring that both the "title" (TIT2) and 
           "album" (TALB) tags are present. If one is missing, the available tag is 
           copied; if both are missing, the file name (without extension) is used.
         - If the Genre (TCON) tag is missing and you choose to use the parent folder 
           name, the Genre is set to the MP3 file’s immediate parent folder name.
         - **Cover Art:**  
             * If no cover art (APIC) is present—or if the existing cover art is of low 
               quality (less than 800×800 pixels)—the script prompts you to fetch a high‑quality
               cover.
             * It first attempts to fetch from Blinkist.com by constructing a URL from the title
               (slugified and suffixed with "-en"). If that fails or if the image quality is insufficient,
               it falls back to Audible, then Goodreads, and finally (optionally) Google Images.
    
      2. Conversion:
         After metadata is updated, each MP3 file is converted to M4A using ffmpeg.
    
      3. Grouping:
         Two subfolders ("mp3" and "m4a") are created in the operation folder.
         The original MP3 files are moved into "mp3" and the converted M4A files into "m4a".
    
    Note: This script requires ffmpeg and the Python packages: mutagen, tqdm, requests,
          beautifulsoup4, and pillow.
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
            if allowed_extensions:
                if file.lower().endswith(tuple(allowed_extensions)):
                    file_list.append(os.path.join(root, file))
            else:
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
            # Update Genre if missing and if user opted to use parent folder name.
            current_genre = tags.get("TCON")
            if (not current_genre or not current_genre.text or not current_genre.text[0].strip()) and use_parent_genre:
                parent_folder = os.path.basename(os.path.dirname(file_path))
                tags.add(TCON(encoding=3, text=[parent_folder]))
            # Check cover art.
            if any(key.startswith("APIC") for key in tags.keys()):
                existing_cover = tags.getall("APIC")[0].data
                if not check_image_quality(existing_cover):
                    tqdm.write(f"[DEBUG] Existing cover art for '{title}' is low quality.")
                    answer_refetch = input(f"Do you want to re-fetch high-quality cover art for '{title}'? (y/n): ").strip().lower()
                    if answer_refetch == "y":
                        cover = fetch_album_cover(title)
                        if cover and check_image_quality(cover):
                            tqdm.write("[DEBUG] High-quality cover art successfully fetched.")
                            tags.delall("APIC")
                            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
                        else:
                            answer_continue = input(f"Failed to fetch high-quality cover art for '{file_path}'. Continue processing remaining files? (y/n): ").strip().lower()
                            if answer_continue != "y":
                                sys.exit(0)
                    else:
                        tqdm.write("[DEBUG] Keeping existing low-quality cover art.")
            else:
                tqdm.write(f"[DEBUG] Cover art missing for '{title}'.")
                answer_fetch = input(f"Do you want to fetch cover art for '{title}'? (y/n): ").strip().lower()
                if answer_fetch == "y":
                    cover = fetch_album_cover(title)
                    if cover and check_image_quality(cover):
                        tqdm.write("[DEBUG] Cover art successfully fetched.")
                        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
                    else:
                        answer_continue = input(f"Failed to fetch high-quality cover art for '{file_path}'. Continue processing remaining files? (y/n): ").strip().lower()
                        if answer_continue != "y":
                            sys.exit(0)
                else:
                    tqdm.write("[DEBUG] Skipping cover art fetching for this file.")
            tags.save(file_path)
        except Exception as e:
            sys.stdout.write(f"\nError updating metadata for '{file_path}': {e}\n")
    return mp3_files

def fetch_album_cover(title):
    headers = {"User-Agent": "Mozilla/5.0"}
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
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            meta = soup.find("meta", property="og:image")
            if meta and meta.get("content"):
                cover_url = meta.get("content")
                tqdm.write(f"[DEBUG] Blinkist cover URL: {cover_url}")
                r2 = requests.get(cover_url, headers=headers, timeout=10)
                tqdm.write(f"[DEBUG] Blinkist cover fetch status: {r2.status_code}")
                if r2.status_code == 200 and check_image_quality(r2.content):
                    return r2.content
                else:
                    tqdm.write("[DEBUG] Blinkist cover fetched but quality is insufficient.")
    except Exception as e:
        tqdm.write(f"[DEBUG] Blinkist failed: {e}")
    
    tqdm.write("[DEBUG] Falling back to Audible search for cover art...")
    try:
        search_url = f"https://www.audible.com/search?keywords={urllib.parse.quote(title)}"
        r = requests.get(search_url, headers=headers, timeout=10)
        tqdm.write(f"[DEBUG] Audible HTTP status: {r.status_code}")
        if r.status_code == 200:
            from bs4 import BeautifulSoup
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
            from bs4 import BeautifulSoup
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
    
    # Optionally, you could implement a Google Images fallback here.
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
