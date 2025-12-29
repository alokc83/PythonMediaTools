#!/usr/bin/env python3
import os
import getpass
from plexapi.myplex import MyPlexAccount
from plexapi.exceptions import NotFound
from mutagen import File as MutagenFile
from tqdm import tqdm

def scan_audio_files(root_dir):
    """Recursively scan the given directory for MP3 and M4A files."""
    audio_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(('.mp3', '.m4a')):
                audio_files.append(os.path.join(dirpath, filename))
    return audio_files

def extract_genre(file_path):
    """
    Use mutagen to extract genre metadata from an audio file.
    Returns a list of genre strings if found, otherwise an empty list.
    """
    try:
        audio = MutagenFile(file_path, easy=True)
        if audio is not None:
            return audio.get("genre", [])
    except Exception as e:
        print(f"Error reading metadata from '{file_path}': {e}")
    return []

def main():
    # === User Inputs ===
    root_dir = input("Enter the root directory for audio files: ").strip()
    library_name = input("Enter the Plex library name (e.g., 'Music'): ").strip()
    username = input("Enter your Plex username: ").strip()
    password = getpass.getpass("Enter your Plex password: ")
    server_name = input("Enter your Plex server name (friendly name): ").strip()
    use_fallback = input("If genre is missing, mark it as 'Unknown'? (Y/n): ").strip().lower() or 'y'

    # === Step 1: Scan the file system for audio files ===
    print("\nScanning for audio files...")
    audio_files = scan_audio_files(root_dir)
    print(f"Found {len(audio_files)} audio files.")

    # === Step 2: Extract genres from each file ===
    file_genres = {}
    for file in tqdm(audio_files, desc="Extracting genres", unit="file"):
        genres = extract_genre(file)
        if not genres:
            # If no genre was found and fallback is enabled, mark as "Unknown"
            genres = ["Unknown"] if use_fallback.startswith('y') else []
        file_genres[file] = genres

    # Build a mapping: genre -> list of file paths
    genre_to_files = {}
    for file, genres in file_genres.items():
        for g in genres:
            genre_name = str(g).strip()
            if genre_name:
                genre_to_files.setdefault(genre_name, []).append(file)

    print("\nGenres found from files:")
    for genre, files in genre_to_files.items():
        print(f"  {genre}: {len(files)} files")

    # === Step 3: Connect to Plex and fetch the library ===
    print("\nConnecting to Plex...")
    account = MyPlexAccount(username, password)
    plex = account.resource(server_name).connect()
    library = plex.library.section(library_name)

    # Get all Plex items in the library
    plex_items = list(library.search())
    print(f"Found {len(plex_items)} items in Plex library '{library_name}'.")

    # Build a mapping: file path (absolute) -> Plex item
    file_to_item = {}
    for item in tqdm(plex_items, desc="Mapping Plex items", unit="item"):
        try:
            for media in item.media:
                for part in media.parts:
                    file_path = os.path.abspath(part.file)
                    file_to_item[file_path] = item
        except Exception as e:
            print(f"Error processing Plex item '{item.title}': {e}")

    # === Step 4: Map genres (from file system) to Plex items ===
    genre_to_items = {}
    for genre, files in genre_to_files.items():
        for file in files:
            abs_file = os.path.abspath(file)
            if abs_file in file_to_item:
                item = file_to_item[abs_file]
                genre_to_items.setdefault(genre, []).append(item)

    print("\nMapping of genres to Plex items:")
    for genre, items in genre_to_items.items():
        print(f"  {genre}: {len(items)} items")

    # === Step 5: Update or create Plex collections per genre ===
    existing_collections = {col.title: col for col in library.collections()}
    for genre, items in tqdm(genre_to_items.items(), desc="Updating collections", total=len(genre_to_items), unit="genre"):
        # Remove duplicate items (if any)
        items = list(set(items))
        if genre in existing_collections:
            collection = existing_collections[genre]
            existing_items = collection.items()
            new_items = [i for i in items if i not in existing_items]
            if new_items:
                collection.addItems(new_items)
                print(f"Updated collection '{genre}' with {len(new_items)} new items.")
        else:
            library.createCollection(genre, items)
            print(f"Created new collection '{genre}' with {len(items)} items.")

    print("\nDone updating Plex collections.")

if __name__ == '__main__':
    main()
