#!/usr/bin/env python3
import os
import time
import re
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp4 import MP4

# --- Helper Function to Normalize Paths ---

def normalize_path(p):
    """
    Normalizes a path by replacing shell escape sequences
    such as '\ ' with a space, '\(' with '(' and '\)' with ')'.
    """
    return p.replace("\\ ", " ").replace("\\(", "(").replace("\\)", ")")

# --- Extraction Functions ---

def extract_with_parentheses(file_path):
    """
    Extract using parentheses pattern:
      Expects a filename like: "Album Name (Artist Name)"
    Returns (artist, album) if matched, otherwise (None, None).
    """
    base_name = os.path.basename(file_path)
    name_without_ext, _ = os.path.splitext(base_name)
    pattern = r'^(.*?)\s*\(([^)]+)\)\s*$'
    match = re.match(pattern, name_without_ext)
    if match:
        album = match.group(1).strip()
        artist = match.group(2).strip()
        return artist, album
    else:
        return (None, None)

def extract_with_hyphen(file_path):
    """
    Extract using hyphen-separated pattern:
      Expects a filename like: "Artist Name - Album Name"
    Returns (artist, album) if hyphen is found, otherwise (None, None).
    """
    base_name = os.path.basename(file_path)
    name_without_ext, _ = os.path.splitext(base_name)
    hyphen_index = name_without_ext.find('-')
    if hyphen_index == -1:
        return (None, None)
    artist = name_without_ext[:hyphen_index].strip()
    album = name_without_ext[hyphen_index+1:].strip()
    return artist, album

def extract_with_both(file_path):
    """
    First attempts the parentheses extraction.
    If that fails, falls back to hyphen extraction.
    """
    artist, album = extract_with_parentheses(file_path)
    if artist is not None and album is not None:
        return artist, album
    return extract_with_hyphen(file_path)

# Global extraction function (set via menu)
extraction_method_func = None

# --- Update Functions ---

def update_mp3_metadata(file_path):
    """
    Loads the MP3 file's ID3 tags (or creates them if necessary),
    then extracts the artist and album from the filename (using the chosen extraction method).
    If the existing metadata matches the extracted values, the file is skipped.
    Otherwise, the metadata is updated and verified.
    Returns a tuple (status, reason).
    """
    print(f"\nProcessing MP3 file: {file_path}")
    base_name = os.path.basename(file_path)
    name_without_ext, _ = os.path.splitext(base_name)
    print(f"Filename without extension: '{name_without_ext}'")

    artist, album = extraction_method_func(file_path)
    if artist is None or album is None:
        msg = "No valid pattern found for extraction."
        print(f"Skipping '{file_path}': {msg}")
        return ("skipped", msg)

    print(f"Extracted artist: '{artist}'")
    print(f"Extracted album: '{album}'")

    try:
        print("Loading existing ID3 tags...")
        audio = EasyID3(file_path)
    except ID3NoHeaderError:
        print("No ID3 tag found. Creating a new tag.")
        try:
            audio = EasyID3()
            audio.save(file_path)
            audio = EasyID3(file_path)
        except Exception as e:
            msg = f"Failed to create ID3 tag: {e}"
            print(f"Error for '{file_path}': {msg}")
            return ("error", msg)
    except Exception as e:
        msg = f"Error loading ID3 tags: {e}"
        print(f"Error for '{file_path}': {msg}")
        return ("error", msg)

    # Check if existing metadata matches the extracted values
    existing_artist = audio.get('artist', [])
    existing_album = audio.get('album', [])
    current_artist = existing_artist[0].strip() if existing_artist and existing_artist[0] else ""
    current_album = existing_album[0].strip() if existing_album and existing_album[0] else ""
    if current_artist == artist and current_album == album:
        print("Existing metadata matches extracted values. Skipping update.")
        return ("skipped", "Metadata matches extracted values")
    else:
        if current_artist or current_album:
            print("Existing metadata does not match. Updating metadata.")

    print(f"Updating metadata: Artist='{artist}', Album='{album}'")
    audio['artist'] = artist
    audio['album'] = album
    try:
        audio.save()
        print("Tags saved. Verifying update...")
        audio_after = EasyID3(file_path)
        actual_artist = audio_after.get('artist', [None])[0]
        actual_album = audio_after.get('album', [None])[0]
        if actual_artist == artist and actual_album == album:
            print(f"MP3 metadata updated successfully for '{file_path}'.")
            return ("updated", None)
        else:
            msg = (f"Verification failed: Expected Artist='{artist}', Album='{album}', "
                   f"Got Artist='{actual_artist}', Album='{actual_album}'")
            print(msg)
            return ("error", "Verification failed")
    except Exception as e:
        msg = f"Error saving or verifying tags: {e}"
        print(f"Error for '{file_path}': {msg}")
        return ("error", msg)

def update_m4a_metadata(file_path):
    """
    Loads the M4A file's MP4 tags,
    then extracts the artist and album from the filename.
    Checks whether the existing metadata matches the extracted values;
    if not, it updates and verifies the tags.
    Returns a tuple (status, reason).
    """
    print(f"\nProcessing M4A file: {file_path}")
    artist, album = extraction_method_func(file_path)
    if artist is None or album is None:
        msg = "No valid pattern found for extraction."
        print(f"Skipping '{file_path}': {msg}")
        return ("skipped", msg)

    print(f"Extracted artist: '{artist}'")
    print(f"Extracted album: '{album}'")

    try:
        print("Loading existing MP4 tags...")
        audio = MP4(file_path)
    except Exception as e:
        msg = f"Error loading MP4 tags: {e}"
        print(f"Error for '{file_path}': {msg}")
        return ("error", msg)

    existing_artist = audio.get("\xa9ART", [])
    existing_album = audio.get("\xa9alb", [])
    current_artist = existing_artist[0].strip() if existing_artist and existing_artist[0] else ""
    current_album = existing_album[0].strip() if existing_album and existing_album[0] else ""
    if current_artist == artist and current_album == album:
        print("Existing metadata matches extracted values. Skipping update.")
        return ("skipped", "Metadata matches extracted values")
    else:
        if current_artist or current_album:
            print("Existing metadata does not match. Updating metadata.")

    print(f"Updating metadata: Artist='{artist}', Album='{album}'")
    audio["\xa9ART"] = [artist]
    audio["\xa9alb"] = [album]
    try:
        audio.save()
        print("Tags saved. Verifying update...")
        audio_after = MP4(file_path)
        actual_artist = audio_after.get("\xa9ART", [None])[0]
        actual_album = audio_after.get("\xa9alb", [None])[0]
        if actual_artist == artist and actual_album == album:
            print(f"M4A metadata updated successfully for '{file_path}'.")
            return ("updated", None)
        else:
            msg = (f"Verification failed: Expected Artist='{artist}', Album='{album}', "
                   f"Got Artist='{actual_artist}', Album='{actual_album}'")
            print(msg)
            return ("error", "Verification failed")
    except Exception as e:
        msg = f"Error saving or verifying tags: {e}"
        print(f"Error for '{file_path}': {msg}")
        return ("error", msg)

# --- Processing Functions ---

def process_single_file(file_path):
    file_lower = file_path.lower()
    if file_lower.endswith('.mp3'):
        return update_mp3_metadata(file_path)
    elif file_lower.endswith('.m4a'):
        return update_m4a_metadata(file_path)
    else:
        print(f"File '{file_path}' is not a supported format (MP3/M4A). Skipping.")
        return ("skipped", "Unsupported format")

def process_directory(directory):
    total_files = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    skipped_details = []
    error_details = []
    
    for root, dirs, files in os.walk(directory):
        print(f"\nEntering directory: {root}")
        for file in files:
            file_lower = file.lower()
            file_path = os.path.join(root, file)
            if file_lower.endswith('.mp3') or file_lower.endswith('.m4a'):
                total_files += 1
                if file_lower.endswith('.mp3'):
                    status, reason = update_mp3_metadata(file_path)
                else:
                    status, reason = update_m4a_metadata(file_path)
                if status == "updated":
                    updated_count += 1
                elif status == "skipped":
                    skipped_count += 1
                    skipped_details.append((file_path, reason))
                elif status == "error":
                    error_count += 1
                    error_details.append((file_path, reason))
            else:
                print(f"Skipping unsupported file: {file} in {root}")
    return total_files, updated_count, skipped_count, error_count, skipped_details, error_details

# --- Main Menu and Program Execution ---

def main():
    global extraction_method_func

    # Menu: choose extraction method
    print("Select the method to extract album and artist from the filename:")
    print("1. Use parentheses format (e.g. 'Album Name (Artist Name)')")
    print("2. Use hyphen-separated format (e.g. 'Artist Name - Album Name')")
    print("3. Use both (parentheses priority, fallback to hyphen)")
    print("0. Exit")
    choice = input("Enter your choice [0/1/2/3]: ").strip()
    if choice == "0":
        print("Exiting.")
        return
    elif choice == "1":
        extraction_method_func = extract_with_parentheses
    elif choice == "2":
        extraction_method_func = extract_with_hyphen
    elif choice == "3":
        extraction_method_func = extract_with_both
    else:
        print("Invalid choice. Defaulting to option 3 (both).")
        extraction_method_func = extract_with_both

    # Menu: choose processing mode (single file vs directory)
    print("\nDo you want to process a single file or a directory recursively?")
    print("1. Single file")
    print("2. Directory (recursive)")
    print("0. Exit")
    mode_choice = input("Enter your choice [0/1/2]: ").strip()
    
    if mode_choice == "0":
        print("Exiting.")
        return
    elif mode_choice == "1":
        path = input("Enter the full path to the file: ").strip()
        path = normalize_path(path)
        if not os.path.isfile(path):
            print(f"Error: '{path}' is not a valid file.")
            return
        start_time = time.time()
        status, reason = process_single_file(path)
        end_time = time.time()
        print(f"\nProcessing complete for single file.")
        print(f"Status: {status}, Reason: {reason if reason else 'None'}")
        print(f"Total time taken: {end_time - start_time:.2f} seconds")
    elif mode_choice == "2":
        path = input("Enter the directory path: ").strip()
        path = normalize_path(path)
        if not os.path.isdir(path):
            print(f"Error: '{path}' is not a valid directory.")
            return
        start_time = time.time()
        total_files, updated_count, skipped_count, error_count, skipped_details, error_details = process_directory(path)
        end_time = time.time()
        print("\nProcessing complete.")
        print(f"Total MP3/M4A files processed: {total_files}")
        print(f"Files updated successfully: {updated_count}")
        print(f"Files skipped: {skipped_count}")
        if skipped_count > 0:
            print("Skipped files details:")
            for f, reason in skipped_details:
                print(f"  {f}: {reason}")
        print(f"Files with errors: {error_count}")
        if error_count > 0:
            print("Error files details:")
            for f, reason in error_details:
                print(f"  {f}: {reason}")
        print(f"Total time taken: {end_time - start_time:.2f} seconds")
    else:
        print("Invalid choice. Exiting.")

if __name__ == "__main__":
    main()
