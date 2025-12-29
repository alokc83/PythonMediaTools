#!/usr/bin/env python3
import os
import sys
import re
import time
import shutil
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
    For MP3 files, uses EasyID3 (checks "title" and falls back to "album").
    For M4A files, uses MP4 (checks "\xa9nam" and falls back to "\xa9alb").
    For Opus files, uses OggOpus (if available).
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
    extensions .mp3, .m4a, or .opus. For each file, reads its metadata to
    extract the title. Files that do not yield a valid title are skipped.
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
    Analyzes the folder's title dictionary to determine:
      - Number of distinct titles.
      - Number of duplicate titles (titles with more than one file).
      - Total duplicate size (for each duplicate group: total size minus the smallest copy).
    Prints the results for the folder.
    """
    distinct_titles = len(title_dict)
    duplicate_titles = sum(1 for title, files in title_dict.items() if len(files) > 1)
    duplicate_size = 0
    for title, files in title_dict.items():
        if len(files) > 1:
            sizes = [size for (_, size) in files]
            duplicate_size += (sum(sizes) - min(sizes))
    print(f"\nFolder: {folder_path}")
    print(f"  Distinct Titles: {distinct_titles}")
    print(f"  Duplicate Titles (within folder): {duplicate_titles}")
    print(f"  Total Duplicate Size (within folder): {sizeof_fmt(duplicate_size)}")
    return distinct_titles, duplicate_titles, duplicate_size

def compare_across_folders(folder_data):
    """
    Given a dictionary mapping folder paths to title dictionaries, builds a
    cross-folder mapping of title -> {folder: list of (file_path, size)}.
    Then, prints the list of titles that appear in more than one folder along with
    details (file paths and sizes) and the combined size for that title.
    Returns the global mapping (for further processing).
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
    return cross_titles

def list_global_unique_files_by_folder(folder_data):
    """
    Computes the global uniqueness of titles across all folders.
    For each title that appears in only one folder, adds the count of files (in that folder)
    to that folder's unique file count.
    Prints, for each folder, the number of files with globally unique titles.
    """
    # Build a global mapping: title -> {folder: list of files}
    global_titles = {}
    for folder, title_dict in folder_data.items():
        for title, files in title_dict.items():
            if title not in global_titles:
                global_titles[title] = {}
            global_titles[title][folder] = files

    unique_files_count_by_folder = {}
    for title, folder_files in global_titles.items():
        if len(folder_files) == 1:
            for folder, files in folder_files.items():
                unique_files_count_by_folder[folder] = unique_files_count_by_folder.get(folder, 0) + len(files)

    print("\nGlobal Unique Files Count (titles that appear in only one folder):")
    if not unique_files_count_by_folder:
        print("  No unique files found across folders.")
    else:
        for folder, count in unique_files_count_by_folder.items():
            print(f"  {folder}: {count} file(s)")

def copy_smallest_files_to_dest(folder_data, dest_folder="AUG2023"):
    """
    Builds a global mapping of title -> list of (file_path, size) across all folders.
    For each title (whether duplicate or unique globally), selects the file with the smallest size
    and copies it to the destination folder (default "AUG2023").
    Prints details of the copy process and a summary.
    """
    global_mapping = {}
    for folder, title_dict in folder_data.items():
        for title, files in title_dict.items():
            if title not in global_mapping:
                global_mapping[title] = []
            global_mapping[title].extend(files)

    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder)

    files_copied = 0
    total_copied_size = 0
    print(f"\nCopying smallest file for each title to folder: {dest_folder}")
    for title, file_list in global_mapping.items():
        # Select the file with minimum size
        chosen = min(file_list, key=lambda x: x[1])
        src_file, size = chosen
        dest_file = os.path.join(dest_folder, os.path.basename(src_file))
        try:
            shutil.copy2(src_file, dest_file)
            print(f"Copied: {src_file} -> {dest_file} ({sizeof_fmt(size)})")
            files_copied += 1
            total_copied_size += size
        except Exception as e:
            print(f"Error copying file '{src_file}' to '{dest_file}': {e}")
    print(f"\nTotal files copied: {files_copied}")
    print(f"Total size of copied files: {sizeof_fmt(total_copied_size)}")

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
    
    # Global uniqueness (titles that appear in only one folder)
    list_global_unique_files_by_folder(folder_data)
    
    # Ask user whether to copy the chosen files to the destination folder.
    copy_choice = input("\nDo you want to copy the smallest file for each title to the 'AUG2023' folder? (y/n): ").strip().lower()
    if copy_choice in ("y", "yes"):
        copy_smallest_files_to_dest(folder_data, dest_folder="AUG2023")
    else:
        print("Skipping file copy.")

if __name__ == "__main__":
    main()
