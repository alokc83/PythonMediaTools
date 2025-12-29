#!/usr/bin/env python3
import os
import sys
import shutil
from mutagen.easyid3 import EasyID3
from mutagen.mp4 import MP4

# Allowed audio formats for copying
ALLOWED_EXT = {".mp3", ".m4a"}

def normalize_path(p):
    """
    Normalize a path by replacing shell escape sequences.
    E.g. convert: /path/to/Folder\ Name\ \(2023\)
         to: /path/to/Folder Name (2023)
    """
    return p.replace("\\ ", " ").replace("\\(", "(").replace("\\)", ")")

def sizeof_fmt(num, suffix='B'):
    """
    Convert a byte count into a human-readable format.
    """
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} Y{suffix}"

def get_audio_title(file_path):
    """
    Reads metadata from an MP3 or M4A file.
    For MP3, it uses EasyID3 to get the "title" tag (falling back to "album").
    For M4A, it uses MP4 to get the "\xa9nam" tag (falling back to "\xa9alb").
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
    Recursively scans the destination folder for MP3/M4A files,
    extracting their titles and returning a set of titles.
    """
    dest_titles = set()
    for root, dirs, files in os.walk(dest_folder):
        for file in files:
            if file.lower().endswith(tuple(ALLOWED_EXT)):
                full_path = os.path.join(root, file)
                # Update progress on same line
                sys.stdout.write("\rScanning destination: " + full_path)
                sys.stdout.flush()
                title = get_audio_title(full_path)
                if title:
                    dest_titles.add(title)
    sys.stdout.write("\n")
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

def process_sources(source_folders, dest_titles):
    """
    Processes each source folder recursively.
    For files with allowed extensions (.mp3, .m4a), extracts the title.
    If the title is not in dest_titles, adds the file to a mapping:
      missing_map: title -> (file_path, file_size, source_folder)
    If the same title is found more than once across source folders, the smallest file is kept.
    Files with other formats are collected in a list for conversion.
    Returns (missing_map, to_convert)
    """
    missing_map = {}  # title -> (file_path, size, source_folder)
    to_convert = []   # list of file paths (non mp3/m4a)
    for folder in source_folders:
        for root, dirs, files in os.walk(folder):
            for file in files:
                full_path = os.path.join(root, file)
                ext = os.path.splitext(file)[1].lower()
                # Print progress on same line:
                sys.stdout.write("\rScanning source: " + full_path)
                sys.stdout.flush()
                if ext in ALLOWED_EXT:
                    title = get_audio_title(full_path)
                    if not title:
                        continue
                    if title in dest_titles:
                        continue  # skip if already in destination
                    size = os.path.getsize(full_path)
                    # If title not seen yet, add it; if seen, keep smaller file.
                    if title not in missing_map:
                        missing_map[title] = (full_path, size, folder)
                    else:
                        existing_path, existing_size, _ = missing_map[title]
                        if size < existing_size:
                            missing_map[title] = (full_path, size, folder)
                else:
                    # Not in allowed extension, record for conversion.
                    to_convert.append(full_path)
    sys.stdout.write("\n")
    return missing_map, to_convert

def copy_missing_files(missing_map, dest_folder):
    """
    Copies each file (one per title) from missing_map to dest_folder.
    If a file with the same name exists, a unique name is generated.
    Returns the number of files copied.
    """
    files_copied = 0
    for title, (src_path, size, src_folder) in missing_map.items():
        filename = os.path.basename(src_path)
        dest_path = get_unique_dest_path(dest_folder, filename)
        try:
            shutil.copy2(src_path, dest_path)
            sys.stdout.write(f"\nCopied '{src_path}' to '{dest_path}' (Title: {title}, Size: {sizeof_fmt(size)})")
            files_copied += 1
        except Exception as e:
            sys.stdout.write(f"\nError copying '{src_path}' to '{dest_path}': {e}\n")
    sys.stdout.write("\n")
    return files_copied

def write_conversion_list(to_convert, output_filename="needs to be converted.txt"):
    """
    Writes the list of files (with full paths) that are not in allowed formats to output_filename.
    """
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            if not to_convert:
                f.write("No files need to be converted.\n")
            else:
                f.write("Files that need to be converted (unsupported formats):\n\n")
                for file in to_convert:
                    f.write(file + "\n")
        sys.stdout.write(f"\nConversion list written to '{output_filename}'.\n")
    except Exception as e:
        sys.stdout.write(f"\nError writing conversion list: {e}\n")

def main():
    print("=== Copy Missing Titles from Source to Destination ===")
    dest_folder = input("Enter the destination folder path: ").strip()
    dest_folder = normalize_path(dest_folder)
    if not os.path.isdir(dest_folder):
        print(f"Error: '{dest_folder}' is not a valid directory.")
        sys.exit(1)
    # Input multiple source folders
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
    print(f"Identified {len(missing_map)} title(s) missing in destination.")
    
    # Copy the smallest file (per title) for each missing title
    print("\nCopying missing files to destination folder...")
    copied_count = copy_missing_files(missing_map, dest_folder)
    print(f"\nTotal files copied: {copied_count}")
    
    # Write out conversion list for files in non-allowed formats
    write_conversion_list(to_convert)

if __name__ == "__main__":
    main()
