#!/usr/bin/env python3
import os
import sys
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError

def update_mp3_metadata(file_path):
    """
    Update the artist and album metadata of the given MP3 file based on its filename.
    The filename (without extension) is split at the first '-' character.
    Everything before the first '-' is considered the artist and everything after is the album.
    """
    print(f"\nProcessing file: {file_path}")
    base_name = os.path.basename(file_path)
    # Remove the .mp3 extension
    name_without_ext, ext = os.path.splitext(base_name)
    print(f"Filename without extension: '{name_without_ext}'")

    # Find the first occurrence of the hyphen ('-')
    hyphen_index = name_without_ext.find('-')
    if hyphen_index == -1:
        print(f"Skipping '{file_path}': No hyphen ('-') found in the filename.")
        return

    # Extract artist and album names
    artist = name_without_ext[:hyphen_index].strip()
    album = name_without_ext[hyphen_index+1:].strip()
    print(f"Extracted artist: '{artist}'")
    print(f"Extracted album: '{album}'")

    try:
        print("Attempting to load existing ID3 tags.")
        audio = EasyID3(file_path)
    except ID3NoHeaderError:
        print("No existing ID3 tag found. Creating a new tag.")
        try:
            # Create a new tag and save it to the file
            audio = EasyID3()
            audio.save(file_path)
            audio = EasyID3(file_path)
        except Exception as e:
            print(f"Failed to create a new ID3 tag for '{file_path}': {e}")
            return
    except Exception as e:
        print(f"Error loading ID3 tags for '{file_path}': {e}")
        return

    # Update metadata fields
    print(f"Updating metadata: Artist='{artist}', Album='{album}'")
    audio['artist'] = artist
    audio['album'] = album
    try:
        audio.save()
        print(f"Successfully updated metadata for '{file_path}'.")
    except Exception as e:
        print(f"Failed to save updated tags for '{file_path}': {e}")

def main(directory):
    """
    Recursively process all MP3 files in the given directory.
    """
    print(f"Starting recursive processing in directory: {directory}")
    
    if not os.path.isdir(directory):
        print(f"Error: '{directory}' is not a valid directory.")
        sys.exit(1)

    for root, dirs, files in os.walk(directory):
        print(f"\nEntering directory: {root}")
        for file in files:
            if file.lower().endswith('.mp3'):
                file_path = os.path.join(root, file)
                update_mp3_metadata(file_path)
            else:
                print(f"Skipping non-MP3 file: {file} in {root}")
    
    print("\nProcessing complete.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_mp3_metadata.py <directory>")
        sys.exit(1)
    main(sys.argv[1])
