#!/usr/bin/env python3
import os
import sys
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp4 import MP4

def extract_artist_album(file_path):
    """
    Extracts artist and album from the filename.
    The filename (without extension) is split at the first '-' character.
    Returns (artist, album) or (None, None) if '-' is not found.
    """
    base_name = os.path.basename(file_path)
    name_without_ext, _ = os.path.splitext(base_name)
    hyphen_index = name_without_ext.find('-')
    if hyphen_index == -1:
        return None, None
    artist = name_without_ext[:hyphen_index].strip()
    album = name_without_ext[hyphen_index + 1:].strip()
    return artist, album

def update_mp3_metadata(file_path):
    """
    Updates metadata for an MP3 file.
    Uses EasyID3 to update the 'artist' and 'album' tags.
    Verifies the tags after saving.
    """
    print(f"\nProcessing MP3 file: {file_path}")
    artist, album = extract_artist_album(file_path)
    if artist is None or album is None:
        print(f"Skipping '{file_path}': No hyphen ('-') found in the filename.")
        return

    print(f"Extracted artist: '{artist}', album: '{album}'")

    try:
        print("Loading existing ID3 tags...")
        audio = EasyID3(file_path)
    except ID3NoHeaderError:
        print("No ID3 tag found. Creating new ID3 tag...")
        try:
            audio = EasyID3()
            audio.save(file_path)
            audio = EasyID3(file_path)
        except Exception as e:
            print(f"Error creating new ID3 tag for '{file_path}': {e}")
            return
    except Exception as e:
        print(f"Error loading ID3 tags for '{file_path}': {e}")
        return

    print("Updating MP3 metadata...")
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
        else:
            print(f"Verification failed for '{file_path}'. Expected Artist='{artist}', Album='{album}', "
                  f"but got Artist='{actual_artist}', Album='{actual_album}'.")
    except Exception as e:
        print(f"Error saving or verifying tags for '{file_path}': {e}")

def update_m4a_metadata(file_path):
    """
    Updates metadata for an M4A file.
    Uses MP4 from mutagen to update the tags.
    The artist is stored under the key "©ART" and the album under "©alb".
    Verifies the tags after saving.
    """
    print(f"\nProcessing M4A file: {file_path}")
    artist, album = extract_artist_album(file_path)
    if artist is None or album is None:
        print(f"Skipping '{file_path}': No hyphen ('-') found in the filename.")
        return

    print(f"Extracted artist: '{artist}', album: '{album}'")

    try:
        print("Loading existing MP4 tags...")
        audio = MP4(file_path)
    except Exception as e:
        print(f"Error loading MP4 tags for '{file_path}': {e}")
        return

    print("Updating M4A metadata...")
    # Update the MP4 tags for artist and album
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
        else:
            print(f"Verification failed for '{file_path}'. Expected Artist='{artist}', Album='{album}', "
                  f"but got Artist='{actual_artist}', Album='{actual_album}'.")
    except Exception as e:
        print(f"Error saving or verifying tags for '{file_path}': {e}")

def main(directory):
    """
    Recursively processes all MP3 and M4A files in the given directory.
    """
    print(f"Starting recursive processing in directory: {directory}")
    
    if not os.path.isdir(directory):
        print(f"Error: '{directory}' is not a valid directory.")
        sys.exit(1)

    for root, dirs, files in os.walk(directory):
        print(f"\nEntering directory: {root}")
        for file in files:
            file_lower = file.lower()
            file_path = os.path.join(root, file)
            if file_lower.endswith('.mp3'):
                update_mp3_metadata(file_path)
            elif file_lower.endswith('.m4a'):
                update_m4a_metadata(file_path)
            else:
                print(f"Skipping non-MP3/M4A file: {file} in {root}")
    
    print("\nProcessing complete.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_metadata.py <directory>")
        sys.exit(1)
    main(sys.argv[1])
