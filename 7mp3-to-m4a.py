#!/usr/bin/env python3
import os
import sys
import re
import shutil
import urllib.parse
import requests
from tqdm import tqdm
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TIT2, TALB, TCON, APIC, error

def print_script_info():
    info = """
    =======================================================================
    This script processes MP3 files in a specified folder as follows:
    
      - Scans the folder (and subfolders) for MP3 files.
      - For each MP3 file, it updates metadata:
          * If the "title" (TIT2) tag is missing but "album" (TALB) exists (or vice versa),
            the missing tag is filled using the available one.
          * If both are missing, it uses the file name (without extension) for both.
          * If the Genre (TCON) tag is missing and you choose to use the parent folder name,
            it will set the Genre to the MP3 file’s immediate parent folder name.
          * If no album cover (APIC) exists, the script attempts to download one.
            It first tries to download from Blinkist.com (constructing a URL from the title by
            slugifying and appending "-en"). If that fails, it falls back to Audible, and if that
            also fails, then Goodreads.
    
    =======================================================================
    """
    print(info)
    answer = input("Do you want to run this script? (y/n): ").strip().lower()
    if answer != "y":
        print("Exiting.")
        sys.exit(0)

def normalize_path(p):
    """Normalize a path by replacing shell escape sequences."""
    return p.replace("\\ ", " ").replace("\\(", "(").replace("\\)", ")")

def sizeof_fmt(num, suffix='B'):
    """Convert a number of bytes into a human-readable string."""
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} Y{suffix}"

def get_audio_title(file_path):
    """
    Reads metadata from an MP3 file using EasyID3.
    It retrieves the "title" tag and falls back to "album" if necessary.
    Returns the title (stripped) or None.
    """
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
    """
    Recursively collects file paths from the given folder.
    If allowed_extensions is provided (as a set), only includes files with those extensions.
    """
    file_list = []
    for root, dirs, files in os.walk(folder):
        for file in files:
            if allowed_extensions:
                if file.lower().endswith(tuple(allowed_extensions)):
                    file_list.append(os.path.join(root, file))
            else:
                file_list.append(os.path.join(root, file))
    return file_list

def process_metadata(operation_folder):
    """
    Scans the specified folder (and subfolders) for MP3 files and updates their metadata.
    - If "title" is missing but "album" exists (or vice versa), copies the available tag.
    - If both are missing, uses the file's base name (without extension) for both.
    - If Genre (TCON) is missing and you chose to use the parent folder name, sets Genre to that.
    - If no album cover (APIC) exists, attempts to fetch one.
    Returns the list of MP3 file paths processed.
    """
    mp3_files = get_all_files(operation_folder, {".mp3"})
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
            # Set Genre if missing and if user opted to use parent folder name.
            current_genre = tags.get("TCON")
            if (not current_genre or not current_genre.text or not current_genre.text[0].strip()) and use_parent_genre:
                parent_folder = os.path.basename(os.path.dirname(file_path))
                tags.add(TCON(encoding=3, text=[parent_folder]))
            # Fetch and embed cover art if missing.
            if not any(key.startswith("APIC") for key in tags.keys()):
                cover = fetch_album_cover(get_audio_title(file_path))
                if cover:
                    tags.add(APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,
                        desc="Cover",
                        data=cover
                    ))
            tags.save(file_path)
        except Exception as e:
            sys.stdout.write(f"\nError updating metadata for '{file_path}': {e}\n")
    return mp3_files

def fetch_album_cover(title):
    """
    Attempts to fetch a cover image for the given title.
    1. Constructs a Blinkist URL from the title by:
         - Lowercasing the title.
         - Removing punctuation (keeping only letters, digits, and spaces).
         - Replacing spaces with hyphens.
         - Appending "-en" if not present.
       E.g., "How to Speed Read People" becomes:
            "https://www.blinkist.com/en/books/how-to-speed-read-people-en"
       If that page exists, it looks for the OpenGraph meta tag "og:image".
    2. If Blinkist fails, falls back to an Audible search.
    3. If Audible fails, falls back to Goodreads.
    Returns image bytes if found, or None.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug).strip('-')
    if not slug.endswith("-en"):
        slug = slug + "-en"
    blinkist_url = f"https://www.blinkist.com/en/books/{slug}"
    try:
        r = requests.get(blinkist_url, headers=headers, timeout=10)
        if r.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            meta = soup.find("meta", property="og:image")
            if meta and meta.get("content"):
                cover_url = meta.get("content")
                r2 = requests.get(cover_url, headers=headers, timeout=10)
                if r2.status_code == 200:
                    return r2.content
    except Exception:
        pass
    # Fallback: Audible search
    try:
        search_url = f"https://www.audible.com/search?keywords={urllib.parse.quote(title)}"
        r = requests.get(search_url, headers=headers, timeout=10)
        if r.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            img = soup.find("img")
            if img and img.get("src"):
                cover_url = img.get("src")
                r2 = requests.get(cover_url, headers=headers, timeout=10)
                if r2.status_code == 200:
                    return r2.content
    except Exception:
        pass
    # Fallback: Goodreads search
    try:
        search_url = f"https://www.goodreads.com/search?q={urllib.parse.quote(title)}"
        r = requests.get(search_url, headers=headers, timeout=10)
        if r.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            img = soup.find("img", {"class": "bookCover"})
            if img and img.get("src"):
                cover_url = img.get("src")
                r2 = requests.get(cover_url, headers=headers, timeout=10)
                if r2.status_code == 200:
                    return r2.content
    except Exception:
        pass
    return None

def get_unique_dest_path(dest_folder, filename):
    """
    Returns a unique file path in dest_folder by appending a counter if needed.
    """
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
    """
    Converts each MP3 file in the provided list to M4A format using ffmpeg.
    The output M4A file will have the same base name and be placed in the same directory.
    Returns a list of tuples: (mp3_file, m4a_file) for successful conversions.
    """
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
    """
    Creates two subfolders ("mp3" and "m4a") within the operation folder.
    Moves the original MP3 files into the "mp3" folder and the converted M4A files into the "m4a" folder.
    """
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
    
    # Ask user for the folder where the operation will be performed.
    operation_folder = input("Enter the folder path where the operation will be performed: ").strip()
    operation_folder = normalize_path(operation_folder)
    if not os.path.isdir(operation_folder):
        print(f"Error: '{operation_folder}' is not a valid directory.")
        sys.exit(1)
    print(f"\nOperation folder: {operation_folder}")
    
    global use_parent_genre
    answer = input("Do you want to use the parent folder name as Genre for MP3 files missing Genre? (y/n): ").strip().lower()
    use_parent_genre = (answer == "y")
    
    # Phase 1: Update metadata for all MP3 files in the operation folder.
    print("\nPhase 1: Updating metadata for MP3 files...")
    updated_mp3_files = process_metadata(operation_folder)
    if not updated_mp3_files:
        print("No MP3 files processed. Exiting.")
        sys.exit(0)
    else:
        print(f"Metadata updated for {len(updated_mp3_files)} MP3 files.")
    
    # Phase 2: Convert updated MP3 files to M4A.
    print("\nPhase 2: Converting MP3 files to M4A...")
    conversion_list = convert_mp3_to_m4a(updated_mp3_files)
    if not conversion_list:
        print("No MP3 files were converted.")
    else:
        print(f"Converted {len(conversion_list)} MP3 files to M4A.")
    
    # Phase 3: Organize files into separate "mp3" and "m4a" folders.
    print("\nPhase 3: Organizing files into 'mp3' and 'm4a' folders...")
    group_files(operation_folder, conversion_list)
    print("\nProcessing complete.")

if __name__ == "__main__":
    main()
