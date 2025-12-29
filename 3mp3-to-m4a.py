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
from mutagen.mp4 import MP4

# Allowed audio formats for copying – now MP3 and MP4 (audio files in MP4 container)
ALLOWED_EXT = {".mp3", ".mp4"}

def print_script_info():
    info = """
    =======================================================================
    This script compares the metadata titles in the current folder (destination)
    with one or more source folders. It then copies any files from the source 
    folders that have a title missing in the destination. If multiple source 
    files share the same title, the smallest file (by size) is chosen.

    Additionally, for MP3 files:
      - If the "title" (TIT2) tag is missing but the "album" (TALB) tag exists,
        it copies the album value into the title tag, or vice versa.
      - If both are missing, the file name (without extension) is used for both.
      - If a default Genre is provided and the Genre (TCON) tag is missing,
        the script attempts to fetch the genre from online sources (Blinkist,
        then falling back to Audible and Goodreads). If successful, that genre
        is added; otherwise, the default is used.
      - If no album cover (APIC) exists, the script attempts to scrape one.
        The primary method is to construct a Blinkist URL from the title by
        slugifying it and appending "-en". If that fails, it falls back to 
        Audible and then Goodreads.

    Files in source folders that are not in MP3 or MP4 format are listed in 
    "needs to be converted.txt".
    =======================================================================
    """
    print(info)
    answer = input("Do you want to run this script? (y/n): ").strip().lower()
    if answer != "y":
        print("Exiting.")
        sys.exit(0)

def normalize_path(p):
    """
    Normalize a path by replacing shell escape sequences.
    E.g., converts:
         /path/to/Folder\\ Name\\ \\(2023\\)
         to: /path/to/Folder Name (2023)
    """
    return p.replace("\\ ", " ").replace("\\(", "(").replace("\\)", ")")

def sizeof_fmt(num, suffix='B'):
    """
    Convert a number of bytes into a human-readable string.
    """
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} Y{suffix}"

def get_audio_title(file_path):
    """
    Reads metadata from an MP3 or MP4 file.
    For MP3, uses EasyID3 to get "title" (falls back to "album").
    For MP4 (or M4A), uses MP4 to get "\xa9nam" (falls back to "\xa9alb").
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
    elif ext in [".mp4", ".m4a"]:
        try:
            audio = MP4(file_path)
            title = audio.get("\xa9nam", [None])[0]
            if not title or title.strip() == "":
                title = audio.get("\xa9alb", [None])[0]
        except Exception as e:
            sys.stdout.write(f"\nError reading MP4 metadata for '{file_path}': {e}\n")
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

def process_destination(dest_folder):
    """
    Scans the destination folder for allowed audio files (MP3/MP4)
    and returns a set of titles extracted from metadata.
    Uses a progress bar.
    """
    dest_titles = set()
    files_list = get_all_files(dest_folder, ALLOWED_EXT)
    for full_path in tqdm(files_list, desc="Scanning Destination", unit="file"):
        title = get_audio_title(full_path)
        if title:
            dest_titles.add(title)
    return dest_titles

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

def fetch_album_cover(title):
    """
    Attempts to fetch a cover image for the given title.
    Enhanced logic:
      1. Constructs a Blinkist URL from the title:
         - Lowercase the title.
         - Remove punctuation (only letters, digits, and spaces remain).
         - Replace spaces with hyphens.
         - Append "-en" if not present.
         E.g.: "How to Speed Read People" becomes
              "https://www.blinkist.com/en/books/how-to-speed-read-people-en"
         If that page exists, look for the OpenGraph meta tag "og:image".
      2. If that fails, falls back to Blinkist search, then Audible, then Goodreads.
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

    # Fallback: Blinkist search
    try:
        search_url = f"https://www.blinkist.com/en/search?q={urllib.parse.quote(title)}"
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

def fetch_genre(title):
    """
    Attempts to fetch a genre for the given title from online sources.
    Primary: Blinkist – constructs URL using the title (slugified and suffixed with "-en")
             and looks for a meta tag (e.g., property="books:genre" or "og:genre").
    Fallback: Audible search, then Goodreads search.
    Returns the genre string if found, or None.
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
            meta = soup.find("meta", property="books:genre")
            if meta and meta.get("content"):
                return meta.get("content").strip()
            meta = soup.find("meta", property="og:genre")
            if meta and meta.get("content"):
                return meta.get("content").strip()
    except Exception:
        pass

    # Fallback: Audible search (hypothetical selector)
    try:
        search_url = f"https://www.audible.com/search?keywords={urllib.parse.quote(title)}"
        r = requests.get(search_url, headers=headers, timeout=10)
        if r.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            span = soup.find("span", class_="genreLabel")
            if span:
                return span.get_text().strip()
    except Exception:
        pass

    # Fallback: Goodreads search (hypothetical selector)
    try:
        search_url = f"https://www.goodreads.com/search?q={urllib.parse.quote(title)}"
        r = requests.get(search_url, headers=headers, timeout=10)
        if r.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            div = soup.find("div", class_="bookGenre")
            if div:
                return div.get_text().strip()
    except Exception:
        pass
    return None

def process_sources(source_folders, dest_titles):
    """
    Processes each source folder recursively.
    For files with allowed extensions (MP3/MP4), extracts the title.
    If the title is not in dest_titles, adds the file to missing_map (keeping the smallest file if duplicates occur).
    Files with other formats are collected in a list (to_convert).
    Returns (missing_map, to_convert) with progress bars.
    """
    missing_map = {}  # title -> (file_path, size, source_folder)
    to_convert = []   # list of file paths (non allowed formats)
    for folder in source_folders:
        files_list = get_all_files(folder)
        for full_path in tqdm(files_list, desc=f"Scanning {os.path.basename(folder)}", unit="file"):
            ext = os.path.splitext(full_path)[1].lower()
            if ext in ALLOWED_EXT:
                title = get_audio_title(full_path)
                if not title:
                    continue
                if title in dest_titles:
                    continue
                size = os.path.getsize(full_path)
                if title not in missing_map:
                    missing_map[title] = (full_path, size, folder)
                else:
                    existing_path, existing_size, _ = missing_map[title]
                    if size < existing_size:
                        missing_map[title] = (full_path, size, folder)
            else:
                to_convert.append(full_path)
    return missing_map, to_convert

def update_mp3_metadata_tags(dest_path, default_genre, title):
    """
    Updates the MP3 file at dest_path:
      - If the "title" (TIT2) tag is missing but "album" (TALB) exists, copies TALB to TIT2, or vice versa.
      - If both TIT2 and TALB are missing, uses the file name (without extension) for both.
      - If the Genre (TCON) tag is missing, it first attempts to fetch the genre from online 
        (via Blinkist, falling back to Audible and Goodreads). If found, that genre is used;
        if not and a default Genre is provided, the default is used.
      - If no album cover (APIC) exists, attempts to fetch one using fetch_album_cover(title)
        and embeds it.
    """
    try:
        try:
            tags = ID3(dest_path)
        except error:
            tags = ID3()
        # Ensure title and album tags exist.
        current_title = tags.get("TIT2")
        current_album = tags.get("TALB")
        if not current_title and current_album:
            tags.add(TIT2(encoding=3, text=current_album.text))
        elif not current_album and current_title:
            tags.add(TALB(encoding=3, text=current_title.text))
        elif not current_title and not current_album:
            basename = os.path.splitext(os.path.basename(dest_path))[0]
            tags.add(TIT2(encoding=3, text=[basename]))
            tags.add(TALB(encoding=3, text=[basename]))
        # Update Genre if missing.
        current_genre = tags.get("TCON")
        if not current_genre or not current_genre.text or not current_genre.text[0].strip():
            fetched_genre = fetch_genre(title)
            if fetched_genre:
                tags.add(TCON(encoding=3, text=[fetched_genre]))
            elif default_genre:
                tags.add(TCON(encoding=3, text=[default_genre]))
        # If no cover art exists, fetch one.
        if not any(key.startswith("APIC") for key in tags.keys()):
            cover = fetch_album_cover(title)
            if cover:
                tags.add(APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,  # front cover
                    desc="Cover",
                    data=cover
                ))
        tags.save(dest_path)
    except Exception as e:
        sys.stdout.write(f"\nError updating metadata for '{dest_path}': {e}\n")

def copy_missing_files(missing_map, dest_folder, default_genre):
    """
    Copies each missing file (one per title) from missing_map into dest_folder.
    After copying, if the file is an MP3, updates its metadata (ensuring title/album consistency,
    genre update, and embedding cover art).
    Returns the number of files copied.
    """
    files_copied = 0
    for title, (src_path, size, src_folder) in missing_map.items():
        filename = os.path.basename(src_path)
        dest_path = get_unique_dest_path(dest_folder, filename)
        try:
            shutil.copy2(src_path, dest_path)
            tqdm.write(f"Copied '{src_path}' to '{dest_path}' (Title: {title}, Size: {sizeof_fmt(size)})")
            files_copied += 1
            if dest_path.lower().endswith(".mp3"):
                update_mp3_metadata_tags(dest_path, default_genre, title)
        except Exception as e:
            tqdm.write(f"Error copying '{src_path}' to '{dest_path}': {e}")
    return files_copied

def write_conversion_list(to_convert, output_filename="needs to be converted.txt"):
    """
    Writes the list of files (full paths) that are not in allowed formats to output_filename.
    """
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            if not to_convert:
                f.write("No files need to be converted.\n")
            else:
                f.write("Files that need to be converted (unsupported formats):\n\n")
                for file in to_convert:
                    f.write(file + "\n")
        print(f"\nConversion list written to '{output_filename}'.")
    except Exception as e:
        print(f"\nError writing conversion list: {e}")

def main():
    print_script_info()

    # Use current working directory as the destination folder.
    dest_folder = os.getcwd()
    print(f"\nUsing current folder as destination: {dest_folder}")

    default_genre = input("Enter default Genre for MP3 files (leave blank to skip): ").strip()

    source_folders = []
    while True:
        src = input("Enter a source folder path (or press Enter to finish): ").strip()
        if not src:
            break
        src = normalize_path(src)
        if not os.path.isdir(src):
            print(f"Error: '{src}' is not a valid directory. Please try again.")
            continue
        source_folders.append(src)
    if not source_folders:
        print("No valid source folders entered. Exiting.")
        sys.exit(0)

    print("\nScanning destination folder to build title set...")
    dest_titles = process_destination(dest_folder)
    print(f"Found {len(dest_titles)} title(s) in the destination folder.")

    print("\nScanning source folders for files missing in destination...")
    missing_map, to_convert = process_sources(source_folders, dest_titles)
    print(f"\nIdentified {len(missing_map)} missing title(s) from source folders.")

    print("\nCopying missing files to destination folder...")
    copied_count = copy_missing_files(missing_map, dest_folder, default_genre)
    print(f"\nTotal files copied: {copied_count}")

    write_conversion_list(to_convert)

if __name__ == "__main__":
    main()
