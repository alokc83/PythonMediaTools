#!/usr/bin/env python3
import os
import sys
from mutagen.easyid3 import EasyID3
from mutagen.mp4 import MP4

def normalize_path(p):
    """
    Normalize a path by replacing common shell escape sequences.
    E.g. converts:
      /path/to/Folder\ Name\ \(2023\)
    to:
      /path/to/Folder Name (2023)
    """
    return p.replace("\\ ", " ").replace("\\(", "(").replace("\\)", ")")

def get_audio_title(file_path):
    """
    Reads metadata from an MP3 or M4A file.
    For MP3, it uses EasyID3 to fetch the "title" tag and falls back to "album" if needed.
    For M4A, it uses MP4 to fetch the "\xa9nam" tag and falls back to "\xa9alb".
    Returns the title (stripped) or None if not found.
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
    else:
        return None

    return title.strip() if title else None

def process_folder(folder_path):
    """
    Recursively scans the given folder for MP3 and M4A files.
    Extracts the title (or album if title is missing) from each file.
    Returns a set of titles found in that folder.
    """
    titles = set()
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith((".mp3", ".m4a")):
                full_path = os.path.join(root, file)
                title = get_audio_title(full_path)
                if title:
                    titles.add(title)
    return titles

def main():
    print("=== Destination Folder ===")
    dest_folder = input("Enter the destination folder path: ").strip()
    dest_folder = normalize_path(dest_folder)
    if not os.path.isdir(dest_folder):
        print(f"Error: '{dest_folder}' is not a valid directory.")
        sys.exit(1)
    dest_titles = process_folder(dest_folder)
    print(f"Found {len(dest_titles)} unique title(s) in the destination folder.\n")
    
    source_folders = []
    while True:
        print("=== Source Folder ===")
        src = input("Enter a source folder path (or press Enter to finish): ").strip()
        if not src:
            break
        src = normalize_path(src)
        if not os.path.isdir(src):
            print(f"Error: '{src}' is not a valid directory. Please try again.")
            continue
        source_folders.append(src)
    
    if not source_folders:
        print("No source folders were entered. Exiting.")
        sys.exit(0)
    
    # Build a mapping: source folder -> set of titles from that folder.
    source_data = {}
    for folder in source_folders:
        titles = process_folder(folder)
        source_data[folder] = titles
        print(f"Source folder '{folder}' has {len(titles)} title(s).")
    
    # Build a global mapping for titles that are present in both destination and source(s).
    common_titles = {}
    for folder, titles in source_data.items():
        common = dest_titles.intersection(titles)
        for title in common:
            if title not in common_titles:
                common_titles[title] = []
            common_titles[title].append(folder)
    
    # Dump info to a text file.
    output_file = "comparison_result.txt"
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            if not common_titles:
                f.write("No common titles found between the destination and source folders.\n")
                print("\nNo common titles found between destination and source folders.")
            else:
                f.write("Common Titles and their Source Folders:\n\n")
                for title in sorted(common_titles.keys()):
                    folders = ", ".join(common_titles[title])
                    f.write(f"Title: {title}\nSource Folder(s): {folders}\n\n")
                print(f"\nComparison results have been written to '{output_file}'.")
    except Exception as e:
        print(f"Error writing output file '{output_file}': {e}")

if __name__ == "__main__":
    main()
