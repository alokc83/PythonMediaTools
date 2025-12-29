#!/usr/bin/env python3
import os
import sys
import shutil
from mutagen.easyid3 import EasyID3
from mutagen.mp4 import MP4

def normalize_path(p):
    """
    Normalize a path by replacing shell escape sequences.
    For example, converts:
      /path/to/Folder\ Name\ \(2023\)
    to:
      /path/to/Folder Name (2023)
    """
    return p.replace("\\ ", " ").replace("\\(", "(").replace("\\)", ")")

def get_audio_title(file_path):
    """
    Reads metadata from an MP3 or M4A file.
    For MP3, it uses EasyID3 to get the "title" tag (falling back to "album" if missing).
    For M4A, it uses MP4 to get the "\xa9nam" tag (falling back to "\xa9alb").
    Returns the title (with surrounding whitespace stripped) or None.
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
    elif ext == ".m4a":
        try:
            audio = MP4(file_path)
            title = audio.get("\xa9nam", [None])[0]
            if not title or title.strip() == "":
                title = audio.get("\xa9alb", [None])[0]
        except Exception as e:
            sys.stdout.write(f"\nError reading M4A metadata for '{file_path}': {e}\n")
            return None
    else:
        return None
    return title.strip() if title else None

def process_destination(dest_folder):
    """
    Recursively scans the destination folder for MP3/M4A files and returns a set
    of titles found (as extracted from metadata).
    """
    dest_titles = set()
    for root, dirs, files in os.walk(dest_folder):
        for file in files:
            if file.lower().endswith((".mp3", ".m4a")):
                full_path = os.path.join(root, file)
                # Display progress on the same line:
                sys.stdout.write("\rScanning destination: " + full_path)
                sys.stdout.flush()
                title = get_audio_title(full_path)
                if title:
                    dest_titles.add(title)
    sys.stdout.write("\n")
    return dest_titles

def get_unique_dest_path(dest_folder, filename):
    """
    Returns a unique file path in dest_folder by appending a counter if necessary.
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

def process_source_and_copy(source_folder, dest_titles, dest_folder):
    """
    Recursively scans the source folder for MP3/M4A files.
    For each file, reads the metadata title.
    If the title is not in the set dest_titles, copies the file to the dest_folder.
    Returns the number of files copied.
    """
    files_copied = 0
    for root, dirs, files in os.walk(source_folder):
        for file in files:
            if file.lower().endswith((".mp3", ".m4a")):
                full_path = os.path.join(root, file)
                # Show progress on the same line:
                sys.stdout.write("\rScanning source: " + full_path)
                sys.stdout.flush()
                title = get_audio_title(full_path)
                if not title:
                    continue
                # If title is not present in destination, copy file.
                if title not in dest_titles:
                    # Determine a unique destination path.
                    dest_path = get_unique_dest_path(dest_folder, os.path.basename(full_path))
                    try:
                        shutil.copy2(full_path, dest_path)
                        sys.stdout.write(f"\nCopied '{full_path}' to '{dest_path}' (Title: {title})\n")
                        files_copied += 1
                    except Exception as e:
                        sys.stdout.write(f"\nError copying '{full_path}' to '{dest_path}': {e}\n")
    sys.stdout.write("\n")
    return files_copied

def main():
    print("=== Copy Missing Titles ===")
    dest_folder = input("Enter the destination folder path: ").strip()
    dest_folder = normalize_path(dest_folder)
    if not os.path.isdir(dest_folder):
        print(f"Error: '{dest_folder}' is not a valid directory.")
        sys.exit(1)
    source_folder = input("Enter the source folder path: ").strip()
    source_folder = normalize_path(source_folder)
    if not os.path.isdir(source_folder):
        print(f"Error: '{source_folder}' is not a valid directory.")
        sys.exit(1)
    
    print("\nProcessing destination folder to collect titles...")
    dest_titles = process_destination(dest_folder)
    print(f"Found {len(dest_titles)} title(s) in the destination folder.")
    
    print("\nProcessing source folder and copying files that have titles not in the destination folder...")
    copied = process_source_and_copy(source_folder, dest_titles, dest_folder)
    print(f"\nTotal files copied: {copied}")

if __name__ == "__main__":
    main()
