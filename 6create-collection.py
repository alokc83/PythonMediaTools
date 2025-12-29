#!/usr/bin/env python3
import os
import getpass
from mutagen import File as MutagenFile
from plexapi.myplex import MyPlexAccount
from plexapi.exceptions import NotFound
from tqdm import tqdm

def scan_audio_files(root_dir):
    """
    Recursively scan the given directory for MP3 and M4A files.
    """
    audio_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(('.mp3', '.m4a')):
                audio_files.append(os.path.join(dirpath, filename))
    return audio_files

def extract_genre(file_path):
    """
    Use Mutagen to extract genre metadata from an audio file.
    Returns a list of genre strings if found, otherwise an empty list.
    """
    try:
        audio = MutagenFile(file_path, easy=True)
        if audio is not None:
            return audio.get("genre", [])
    except Exception as e:
        print(f"Error reading metadata from '{file_path}': {e}")
    return []

def build_file_to_item_mapping(library):
    """
    Build a mapping from the absolute file path of each media part in the Plex library
    to its corresponding Plex item.
    """
    file_to_item = {}
    plex_items = list(library.search())
    for item in plex_items:
        try:
            for media in item.media:
                for part in media.parts:
                    file_path = os.path.abspath(part.file)
                    file_to_item[file_path] = item
        except Exception as e:
            print(f"Error processing Plex item '{item.title}': {e}")
    return file_to_item

def create_or_update_collections(library, genre_to_items):
    """
    Create or update Plex collections based on the mapping of genres to Plex items.
    """
    # Get existing collections in the library.
    existing_collections = {col.title: col for col in library.collections()}
    
    for genre, items in tqdm(genre_to_items.items(), desc="Updating collections", unit="genre"):
        # Remove duplicate Plex items.
        items = list(set(items))
        if genre in existing_collections:
            collection = existing_collections[genre]
            # Get existing items in the collection.
            existing_items = collection.items()
            new_items = [i for i in items if i not in existing_items]
            if new_items:
                collection.addItems(new_items)
                print(f"Updated collection '{genre}' with {len(new_items)} new items.")
        else:
            library.createCollection(genre, items)
            print(f"Created new collection '{genre}' with {len(items)} items.")

def main():
    print("=== Filesystem Genre Scanner & Plex Collection Creator ===")
    
    # Step 1: Scan filesystem for audio files.
    root_dir = input("Enter the root directory for audio files: ").strip()
    use_fallback = input("If genre is missing, mark it as 'Unknown'? (Y/n): ").strip().lower() or 'y'
    
    print("\nScanning for audio files...")
    audio_files = scan_audio_files(root_dir)
    print(f"Found {len(audio_files)} audio files.")
    
    # Build mapping of genre -> list of file paths.
    genre_to_files = {}
    for file in tqdm(audio_files, desc="Extracting genres", unit="file"):
        genres = extract_genre(file)
        if not genres and use_fallback.startswith('y'):
            genres = ["Unknown"]
        for genre in genres:
            genre = genre.strip()
            if genre:
                genre_to_files.setdefault(genre, []).append(os.path.abspath(file))
    
    print("\nGenres found from files:")
    for genre, files in genre_to_files.items():
        print(f"  {genre}: {len(files)} files")
    
    # Step 2: Connect to Plex.
    plex_username = input("\nEnter your Plex username: ").strip()
    plex_password = getpass.getpass("Enter your Plex password: ")
    plex_server_name = input("Enter your Plex server name (friendly name): ").strip()
    plex_library_name = input("Enter the Plex library name where collections should be created: ").strip()
    
    print("\nConnecting to Plex...")
    try:
        account = MyPlexAccount(plex_username, plex_password)
        plex = account.resource(plex_server_name).connect()
    except Exception as e:
        print(f"Error connecting to Plex: {e}")
        return
    
    try:
        library = plex.library.section(plex_library_name)
    except NotFound:
        print(f"Plex library '{plex_library_name}' not found.")
        return
    
    # Step 3: Build file-to-Plex item mapping.
    print("Building file-to-Plex item mapping...")
    file_to_item = build_file_to_item_mapping(library)
    print(f"Mapped {len(file_to_item)} files to Plex items.")
    
    # Step 4: Map genres (from filesystem) to Plex items.
    genre_to_items = {}
    for genre, files in genre_to_files.items():
        for file in files:
            if file in file_to_item:
                item = file_to_item[file]
                genre_to_items.setdefault(genre, []).append(item)
            else:
                print(f"Warning: File '{file}' not found in Plex library.")
    
    # Step 5: Create or update Plex collections based on genres.
    create_or_update_collections(library, genre_to_items)
    
    print("\nDone creating/updating Plex collections.")

if __name__ == '__main__':
    main()
