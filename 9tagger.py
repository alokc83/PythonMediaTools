#!/usr/bin/env python3
import os
import sys
import time
import re
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp4 import MP4

def extract_artist_album(file_path):
    """
    Extracts artist and album from the filename.
    
    Priority:
    - If the filename (without extension) ends with a parenthesized group, that group is considered the artist,
      and the preceding text is considered the album.
    - Otherwise, it splits the filename at the first '-' character:
         • Text before the hyphen is the artist.
         • Text after the hyphen is the album.
    
    Returns:
        (artist, album) tuple, or (None, None) if neither pattern is found.
    """
    base_name = os.path.basename(file_path)
    name_without_ext, _ = os.path.splitext(base_name)
    
    # Try to match the pattern: "album (artist)" at the end
    pattern = r'^(.*?)\s*\(([^)]+)\)\s*$'
    match = re.match(pattern, name_without_ext)
    if match:
        album = match.group(1).strip()
        artist = match.group(2).strip()
        return artist, album

    # Fallback to splitting by hyphen if no parenthesis pattern is found
    hyphen_index = name_without_ext.find('-')
    if hyphen_index == -1:
        return None, None
    artist = name_without_ext[:hyphen_index].strip()
    album = name_without_ext[hyphen_index+1:].strip()
    return artist, album

def update_mp3_metadata(file_path):
    """
    Updates metadata for an MP3 file using EasyID3.
    Checks if both artist and album tags already exist and are non-empty.
    If so, skips rewriting.
    
    Returns a tuple (status, reason) where status is one of:
      - "updated"  : tags updated and verified successfully.
      - "skipped"  : file was skipped (e.g., due to filename format or metadata already exists).
      - "error"    : an error occurred during processing.
    """
    print(f"\nProcessing MP3 file: {file_path}")
    base_name = os.path.basename(file_path)
    name_without_ext, _ = os.path.splitext(base_name)
    print(f"Filename without extension: '{name_without_ext}'")

    artist, album = extract_artist_album(file_path)
    if artist is None or album is None:
        msg = "No valid pattern found in the filename (expected 'artist - album' or 'album (artist)')"
        print(f"Skipping '{file_path}': {msg}.")
        return ("skipped", msg)

    print(f"Extracted artist: '{artist}'")
    print(f"Extracted album: '{album}'")

    try:
        print("Attempting to load existing ID3 tags...")
        audio = EasyID3(file_path)
    except ID3NoHeaderError:
        print("No existing ID3 tag found. Creating a new tag.")
        try:
            audio = EasyID3()
            audio.save(file_path)
            audio = EasyID3(file_path)
        except Exception as e:
            msg = f"Failed to create new ID3 tag: {e}"
            print(f"Error for '{file_path}': {msg}")
            return ("error", msg)
    except Exception as e:
        msg = f"Error loading ID3 tags: {e}"
        print(f"Error for '{file_path}': {msg}")
        return ("error", msg)

    # Check if metadata already exists
    existing_artist = audio.get('artist', [])
    existing_album = audio.get('album', [])
    if existing_artist and existing_album and existing_artist[0].strip() and existing_album[0].strip():
        print("Metadata already exists for this file. Skipping rewriting.")
        return ("skipped", "Metadata already exists")

    print(f"Updating metadata: Artist='{artist}', Album='{album}'")
    audio['artist'] = artist
    audio['album'] = album
    try:
        audio.save()
        print("Tags saved. Verifying tags...")
        audio_after = EasyID3(file_path)
        actual_artist = audio_after.get('artist', [None])[0]
        actual_album = audio_after.get('album', [None])[0]
        if actual_artist == artist and actual_album == album:
            print(f"Successfully updated MP3 metadata for '{file_path}'. Tagging successful. ✅")
            return ("updated", None)
        else:
            msg = (f"Tag verification failed. Expected Artist='{artist}' and Album='{album}', "
                   f"but found Artist='{actual_artist}' and Album='{actual_album}'")
            print(msg)
            return ("error", "Tag verification failed")
    except Exception as e:
        msg = f"Error saving or verifying tags: {e}"
        print(f"Error for '{file_path}': {msg}")
        return ("error", msg)

def update_m4a_metadata(file_path):
    """
    Updates metadata for an M4A file using MP4.
    Checks if both artist and album tags already exist and are non-empty.
    For M4A files, artist is stored under "\xa9ART" and album under "\xa9alb".
    
    Returns a tuple (status, reason) with similar status values as update_mp3_metadata.
    """
    print(f"\nProcessing M4A file: {file_path}")
    artist, album = extract_artist_album(file_path)
    if artist is None or album is None:
        msg = "No valid pattern found in the filename (expected 'artist - album' or 'album (artist)')"
        print(f"Skipping '{file_path}': {msg}.")
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

    # Check if metadata already exists
    existing_artist = audio.get("\xa9ART", [])
    existing_album = audio.get("\xa9alb", [])
    if (existing_artist and existing_album and
            existing_artist[0].strip() and existing_album[0].strip()):
        print("Metadata already exists for this file. Skipping rewriting.")
        return ("skipped", "Metadata already exists")

    print(f"Updating metadata: Artist='{artist}', Album='{album}'")
    audio["\xa9ART"] = [artist]
    audio["\xa9alb"] = [album]
    try:
        audio.save()
        print("Tags saved. Verifying tags...")
        audio_after = MP4(file_path)
        actual_artist = audio_after.get("\xa9ART", [None])[0]
        actual_album = audio_after.get("\xa9alb", [None])[0]
        if actual_artist == artist and actual_album == album:
            print(f"Successfully updated M4A metadata for '{file_path}'. Tagging successful. ✅")
            return ("updated", None)
        else:
            msg = (f"Tag verification failed. Expected Artist='{artist}', Album='{album}', "
                   f"but got Artist='{actual_artist}', Album='{actual_album}'")
            print(msg)
            return ("error", "Tag verification failed")
    except Exception as e:
        msg = f"Error saving or verifying tags: {e}"
        print(f"Error for '{file_path}': {msg}")
        return ("error", msg)

def main(directory):
    """
    Recursively processes all MP3 and M4A files in the given directory.
    At the end, prints a summary including:
      - Total files processed
      - Files updated successfully
      - Files skipped (with reasons)
      - Files with errors (with reasons)
      - Total time taken
    """
    print(f"Starting recursive processing in directory: {directory}")
    
    if not os.path.isdir(directory):
        print(f"Error: '{directory}' is not a valid directory.")
        sys.exit(1)

    total_files = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    skipped_details = []  # List of tuples: (file_path, reason)
    error_details = []    # List of tuples: (file_path, reason)

    start_time = time.time()

    for root, dirs, files in os.walk(directory):
        print(f"\nEntering directory: {root}")
        for file in files:
            file_lower = file.lower()
            file_path = os.path.join(root, file)
            if file_lower.endswith('.mp3'):
                total_files += 1
                status, reason = update_mp3_metadata(file_path)
                if status == "updated":
                    updated_count += 1
                elif status == "skipped":
                    skipped_count += 1
                    skipped_details.append((file_path, reason))
                elif status == "error":
                    error_count += 1
                    error_details.append((file_path, reason))
            elif file_lower.endswith('.m4a'):
                total_files += 1
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
                print(f"Skipping non-MP3/M4A file: {file} in {root}")

    elapsed_time = time.time() - start_time

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
    print(f"Total time taken: {elapsed_time:.2f} seconds")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_metadata.py <directory>")
        sys.exit(1)
    main(sys.argv[1])
