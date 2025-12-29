#!/usr/bin/env python3
import os
import sys
import re
import time
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp4 import MP4

# Try to import OggOpus for .opus files
try:
    from mutagen.oggopus import OggOpus
except ImportError:
    OggOpus = None

def normalize_path(p):
    """
    Normalize a path by replacing shell escape sequences.
    For example, convert:
      /path/to/Folder\ Name\ \(2023\)
    to:
      /path/to/Folder Name (2023)
    """
    return p.replace("\\ ", " ").replace("\\(", "(").replace("\\)", ")")

def sizeof_fmt(num, suffix='B'):
    """
    Convert a size in bytes into a human-readable string.
    For example, 3732932480 becomes "3.5 GB".
    """
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} Y{suffix}"

def get_audio_title(file_path):
    """
    Reads the metadata of the audio file to determine its title.
    For MP3 files, it uses EasyID3 (checks the "title" tag,
    falling back to "album" if needed).
    For M4A files, it uses MP4 (checking the "\xa9nam" tag,
    falling back to "\xa9alb").
    For Opus files, it uses OggOpus (if available).
    Returns the title as a stripped string or None if not found.
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
            print(f"Error reading MP3 metadata for '{file_path}': {e}")
            return None
    elif ext == ".m4a":
        try:
            audio = MP4(file_path)
            title = audio.get("\xa9nam", [None])[0]
            if not title or title.strip() == "":
                title = audio.get("\xa9alb", [None])[0]
        except Exception as e:
            print(f"Error reading M4A metadata for '{file_path}': {e}")
            return None
    elif ext == ".opus":
        if OggOpus is None:
            print(f"Skipping Opus file '{file_path}': OggOpus module not available.")
            return None
        try:
            audio = OggOpus(file_path)
            title = audio.get("title", [None])[0]
            if not title or title.strip() == "":
                title = audio.get("album", [None])[0]
        except Exception as e:
            print(f"Error reading Opus metadata for '{file_path}': {e}")
            return None
    else:
        return None

    return title.strip() if title else None

def process_folder(folder_path):
    """
    Recursively walks through the folder and collects audio files with
    extensions .mp3, .m4a, or .opus. For each file, reads its metadata
    to extract the title. Files that do not yield a valid title are skipped.
    Returns a dictionary mapping title -> list of (file_path, file_size).
    """
    title_dict = {}
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith((".mp3", ".m4a", ".opus")):
                full_path = os.path.join(root, file)
                title = get_audio_title(full_path)
                if not title:
                    continue
                size = os.path.getsize(full_path)
                if title not in title_dict:
                    title_dict[title] = []
                title_dict[title].append((full_path, size))
    return title_dict

def analyze_folder(folder_path, title_dict):
    """
    Analyzes the given folder's title dictionary to determine:
      - Number of unique titles.
      - Number of duplicate titles (titles with more than one file).
      - Total duplicate size (i.e. sum over duplicate groups: total size minus the smallest copy).
    Prints the results for the folder.
    """
    unique_titles = len(title_dict)
    duplicate_titles = sum(1 for title, files in title_dict.items() if len(files) > 1)
    duplicate_size = 0
    for title, files in title_dict.items():
        if len(files) > 1:
            sizes = [size for (_, size) in files]
            duplicate_size += (sum(sizes) - min(sizes))
    print(f"\nFolder: {folder_path}")
    print(f"  Unique Titles: {unique_titles}")
    print(f"  Duplicate Titles (within folder): {duplicate_titles}")
    print(f"  Total Duplicate Size (within folder): {sizeof_fmt(duplicate_size)}")
    return unique_titles, duplicate_titles, duplicate_size

def compare_across_folders(folder_data):
    """
    Given a dictionary mapping folder paths to title dictionaries, build a
    cross-folder mapping of title -> {folder: list of (file, size)}.
    Then, print the list of titles that appear in more than one folder along with
    details (file paths and sizes). Also print the combined size of all copies for
    each duplicate title.
    """
    cross_titles = {}
    for folder, data in folder_data.items():
        for title, files in data.items():
            if title not in cross_titles:
                cross_titles[title] = {}
            cross_titles[title][folder] = files

    cross_duplicates = {title: info for title, info in cross_titles.items() if len(info) > 1}

    print("\nCross-folder Duplicate Titles:")
    if not cross_duplicates:
        print("  No duplicate titles found across the provided folders.")
    else:
        for title, folder_files in cross_duplicates.items():
            print(f"\nTitle: {title}")
            total_size = 0
            for folder, files in folder_files.items():
                print(f"  In Folder: {folder}")
                for f, size in files:
                    total_size += size
                    print(f"    {f} ({sizeof_fmt(size)})")
            print(f"  Combined Size for this title (all copies): {sizeof_fmt(total_size)}")

def main():
    folder_paths = []
    while True:
        path = input("Enter folder path to analyze: ").strip()
        if not path:
            print("No path entered. Exiting input loop.")
            break
        norm_path = normalize_path(path)
        if not os.path.isdir(norm_path):
            print(f"Error: '{norm_path}' is not a valid directory. Please try again.")
            continue
        folder_paths.append(norm_path)
        another = input("Do you want to enter another folder? (y/n): ").strip().lower()
        if another not in ("y", "yes"):
            break

    if not folder_paths:
        print("No valid folders entered. Exiting.")
        sys.exit(0)

    print("\nStarting analysis of each folder...")
    folder_data = {}  # Maps folder_path -> title dictionary
    for folder in folder_paths:
        print(f"\nProcessing folder: {folder}")
        title_dict = process_folder(folder)
        folder_data[folder] = title_dict
        analyze_folder(folder, title_dict)

    print("\nComparing titles across folders...")
    compare_across_folders(folder_data)

if __name__ == "__main__":
    main()
