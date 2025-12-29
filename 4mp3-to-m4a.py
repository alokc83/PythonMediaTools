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

# Allowed audio formats for copying – we treat MP3 and MP4 (M4A) as allowed.
ALLOWED_EXT = {".mp3", ".mp4"}

# Global flag: set based on user confirmation whether to use parent folder name as Genre.
use_parent_genre = False

def print_script_info():
    info = """
    =======================================================================
    This script compares the metadata titles in the current folder (destination)
    with one or more source folders. It then copies any files from the source 
    folders whose title is missing in the destination (selecting, per title, the 
    smallest file if duplicates exist).

    For MP3 files, after copying:
      - If the "title" (TIT2) or "album" (TALB) tag is missing, the script 
        fills the missing tag from the available one; if both are missing, it uses 
        the file name (without extension).
      - If the Genre (TCON) tag is missing, the script can (after confirmation)
        set the Genre to the name of the parent folder (the source folder name).
      - If no album cover (APIC) exists, the script attempts to fetch one from Blinkist.
        It constructs a Blinkist URL from the title (by slugifying and appending "-en").
        If Blinkist fails, it falls back to using an Audible search.
    
    Files in the source folders that are not MP3 or MP4 are listed in 
    "needs to be converted.txt".
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
    Reads metadata from an MP3 or MP4 file.
    For MP3: uses EasyID3 to get "title" (falls back to "album").
    For MP4 (M4A): uses MP4 to get "\xa9nam" (falls back to "\xa9alb").
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
    """Recursively collects file paths from folder; filters by allowed_extensions if provided."""
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
      1. Construct a Blinkist URL from the title:
         - Lowercase the title.
         - Remove punctuation (keep only letters, digits, spaces).
         - Replace spaces with hyphens.
         - Append "-en" if not present.
         Example: "How to Speed Read People" ->
                  "https://www.blinkist.com/en/books/how-to-speed-read-people-en"
         If that page exists, the function looks for the OpenGraph meta tag "og:image".
      2. If that fails, falls back to an Audible search.
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

def update_mp3_metadata_tags(dest_path, title, source_folder):
    """
    Updates the MP3 file at dest_path:
      - Ensures both TIT2 (title) and TALB (album) tags exist; if one is missing, copies from the other.
      - If both are missing, uses the file name (without extension) for both.
      - If the Genre (TCON) tag is missing, uses the parent folder name (source_folder's basename)
        as the Genre.
      - If no album cover (APIC) exists, attempts to fetch one using fetch_album_cover(title)
        from Blinkist (with fallback to Audible).
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
        # Update Genre: if missing, use the parent folder name.
        current_genre = tags.get("TCON")
        if not current_genre or not current_genre.text or not current_genre.text[0].strip():
            parent_genre = os.path.basename(source_folder)
            tags.add(TCON(encoding=3, text=[parent_genre]))
        # Update cover art if missing.
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

def copy_missing_files(missing_map, dest_folder):
    """
    Copies each missing file (one per title) from missing_map into dest_folder.
    After copying, if the file is an MP3, updates its metadata using update_mp3_metadata_tags.
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
                update_mp3_metadata_tags(dest_path, title, src_folder)
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

    # Use current working directory as destination.
    dest_folder = os.getcwd()
    print(f"\nUsing current folder as destination: {dest_folder}")

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
    copied_count = copy_missing_files(missing_map, dest_folder)
    print(f"\nTotal files copied: {copied_count}")

    write_conversion_list(to_convert)

if __name__ == "__main__":
    main()
