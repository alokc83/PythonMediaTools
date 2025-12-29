#!/usr/bin/env python3
import os
import sys
import re
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

def unescape_path(path):
    # Remove any backslash that escapes a character (e.g., \ , \(, \))
    return re.sub(r'\\(.)', r'\1', path)

def update_mp3_genre(file_path, genre):
    try:
        audio = EasyID3(file_path)
    except Exception:
        audio = EasyID3()  # Create new tag if not present
    audio["genre"] = genre
    audio.save(file_path)

def update_m4a_genre(file_path, genre):
    try:
        audio = MP4(file_path)
    except Exception as e:
        print(f"Error reading M4A file '{file_path}': {e}")
        return
    # For MP4/M4A, genre is stored under the key '©gen'
    audio["\xa9gen"] = [genre]
    audio.save(file_path)

def process_folder(folder):
    file_count = 0
    for root, dirs, files in os.walk(folder):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ['.mp3', '.m4a']:
                file_path = os.path.join(root, file)
                # Use the immediate parent folder's name as the Genre.
                parent_folder = os.path.basename(root)
                try:
                    if ext == ".mp3":
                        update_mp3_genre(file_path, parent_folder)
                    elif ext == ".m4a":
                        update_m4a_genre(file_path, parent_folder)
                    print(f"Updated '{file_path}' with genre: {parent_folder}")
                    file_count += 1
                except Exception as e:
                    print(f"Error updating '{file_path}': {e}")
    return file_count

def main():
    folder = input("Enter the folder path where MP3/M4A files exist: ").strip()
    folder = unescape_path(folder)
    if not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a valid directory.")
        sys.exit(1)
    
    total = process_folder(folder)
    print(f"\nUpdated genre metadata for {total} files.")

if __name__ == "__main__":
    main()
