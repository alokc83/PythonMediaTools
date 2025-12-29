#!/usr/bin/env python3
import os
import re
import sys
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp4 import MP4

# For opus files:
try:
    from mutagen.oggopus import OggOpus
except ImportError:
    print("Warning: mutagen does not have OggOpus support. Make sure you have a recent version of mutagen installed.")
    OggOpus = None

def normalize_path(p):
    """
    Normalizes a path by replacing shell escape sequences
    such as '\ ' with a space, '\(' with '(' and '\)' with ')'.
    """
    return p.replace("\\ ", " ").replace("\\(", "(").replace("\\)", ")")

def sizeof_fmt(num, suffix='B'):
    """
    Convert a number of bytes to a human-readable string.
    For example, 3732932480 becomes "3.5 GB".
    """
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} Y{suffix}"

def get_audio_title(file_path):
    """
    Returns the title of the audio file by reading metadata.
    If the "title" field is missing or empty, it falls back to the "album" field.
    Supported file types: MP3, M4A, and Opus.
    If no metadata is found, returns None.
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
    Recursively walks through the folder (folder_path) and collects audio files with
    supported extensions. For each file, reads its metadata to extract the title.
    Returns a dictionary mapping title -> list of (file_path, file_size).
    Files that do not return a valid title (None) are skipped.
    """
    title_dict = {}
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith((".mp3", ".m4a", ".opus")):
                full_path = os.path.join(root, file)
                title = get_audio_title(full_path)
                if not title:
                    # If no metadata title is found, skip this file.
                    continue
                size = os.path.getsize(full_path)
                if title not in title_dict:
                    title_dict[title] = []
                title_dict[title].append((full_path, size))
    return title_dict

def analyze_folder(folder_path):
    """
    Analyzes a folder and prints:
      - Total number of unique titles
      - Number of duplicate titles (titles that appear more than once)
      - Total duplicate size (the sum of sizes for redundant copies in each duplicate group)
    """
    print(f"\nAnalyzing folder: {folder_path}")
    title_dict = process_folder(folder_path)
    unique_titles = len(title_dict)
    duplicate_titles = 0
    duplicate_size = 0

    for title, files in title_dict.items():
        if len(files) > 1:
            duplicate_titles += 1
            # Compute duplicate size as (sum of all sizes - size of one copy)
            sizes = [s for (_, s) in files]
            duplicate_size += (sum(sizes) - min(sizes))
    print(f"Unique Titles: {unique_titles}")
    print(f"Duplicate Titles: {duplicate_titles}")
    print(f"Total Duplicate Size: {sizeof_fmt(duplicate_size)}")
    return unique_titles, duplicate_titles, duplicate_size

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

    print("\nStarting analysis...")
    for folder in folder_paths:
        analyze_folder(folder)

if __name__ == "__main__":
    main()
