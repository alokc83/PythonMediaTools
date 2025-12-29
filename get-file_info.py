#!/usr/bin/env python3
import os
import sys

def count_files(folder, extensions):
    count = 0
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.lower().endswith(extensions):
                count += 1
    return count

def main():
    folder = input("Enter the source folder path: ").strip()
    if not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a valid directory.")
        sys.exit(1)
    
    mp3_count = count_files(folder, ('.mp3',))
    m4a_count = count_files(folder, ('.m4a',))
    
    print(f"Number of MP3 files found: {mp3_count}")
    print(f"Number of M4A files found: {m4a_count}")

if __name__ == "__main__":
    main()
