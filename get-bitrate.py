#!/usr/bin/env python3
import os
import re
import sys
from mutagen.mp4 import MP4
from mutagen.mp3 import MP3

def unescape_path(path):
    # Remove all backslashes (assuming they're only used for escaping)
    return path.replace("\\", "")

def main():
    file_path = input("Enter the file path: ").strip()
    processed_path = unescape_path(file_path)
    print("Processed file path:", processed_path)
    if not os.path.exists(processed_path):
        print("File does not exist!")
        sys.exit(1)
    ext = os.path.splitext(processed_path)[1].lower()
    try:
        if ext in ['.m4a', '.mp4']:
            audio = MP4(processed_path)
        elif ext == '.mp3':
            audio = MP3(processed_path)
        else:
            print("Unsupported file type!")
            sys.exit(1)
        # The bitrate is typically given in bits per second.
        bitrate = audio.info.bitrate
        print(f"Bitrate: {bitrate/1000:.0f} kbps")
    except Exception as e:
        print(f"Error reading file: {e}")

if __name__ == "__main__":
    main()
