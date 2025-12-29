#!/usr/bin/env python3
import getpass
import requests
from plexapi.myplex import MyPlexAccount
from plexapi.exceptions import NotFound
from tqdm import tqdm
from mutagen import File as MutagenFile

def is_audio_file(item):
    """
    Check if the Plex item contains at least one media part with a file ending in .mp3 or .m4a.
    """
    try:
        for media in item.media:
            for part in media.parts:
                if part.file.lower().endswith(('.mp3', '.m4a')):
                    return True
    except Exception as e:
        print(f"Error accessing media parts for {item.title}: {e}")
    return False

def extract_genre_from_file(item):
    """
    Use mutagen to read the genre metadata directly from the audio file.
    Returns a list of genre strings if available, or an empty list.
    """
    for media in item.media:
        for part in media.parts:
            if part.file.lower().endswith(('.mp3', '.m4a')):
                try:
                    audio = MutagenFile(part.file, easy=True)
                    if audio is not None:
                        # 'genre' might be stored as a list of strings
                        return audio.get("genre", [])
                except Exception as e:
                    print(f"Error reading file metadata for {item.title}: {e}")
    return []

def get_genre_from_openlibrary(query):
    """
    As a fallback, query the Open Library API using the item's title.
    Uses the first subject (if available) as a 'genre'.
    """
    url = f"https://openlibrary.org/search.json?q={query}"
    try:
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Open Library API returned status code {response.status_code} for query: {query}")
            return None
        data = response.json()
        if data.get('docs'):
            subjects = data['docs'][0].get('subject', [])
            if subjects:
                return subjects[0]  # Use the first subject as the fallback genre
    except Exception as e:
        print("Error contacting Open Library API:", e)
    return None

def main():
    # Get interactive inputs.
    library_name = input("Enter the Plex library name (e.g., 'Music'): ").strip()
    username = input("Enter your Plex username: ").strip()
    password = getpass.getpass("Enter your Plex password: ")
    server_name = input("Enter your Plex server name (friendly name as in your account): ").strip()
    use_openlibrary = input("If genre is missing, fetch info from Open Library? (Y/n): ").strip().lower() or 'y'

    # Login to Plex.
    account = MyPlexAccount(username, password)
    plex = account.resource(server_name).connect()

    # Access the desired library.
    library = plex.library.section(library_name)

    # Fetch existing collections from this library.
    existing_collections = {col.title: col for col in library.collections()}
    print("\nExisting collections:")
    for title in existing_collections:
        print(f"  {title}")

    # Get all items and filter only audio files.
    all_items = list(library.search())
    print(f"\nFound {len(all_items)} items in the library.")

    # Build a mapping: genre -> list of items.
    genre_groups = {}
    for item in tqdm(all_items, desc="Processing audio items", unit="item"):
        # Process only audio items (MP3/M4A).
        if not is_audio_file(item):
            continue

        # Always extract genre directly from the file.
        genres = extract_genre_from_file(item)

        # If no genre was found in the file and the user opted for a fallback,
        # query Open Library using the item's title.
        if (not genres) and use_openlibrary.startswith('y'):
            fallback_genre = get_genre_from_openlibrary(item.title)
            if fallback_genre:
                genres = [fallback_genre]
            else:
                genres = []

        # If we found any genres, group the item accordingly.
        for g in genres:
            # Ensure the genre is a string.
            genre_name = str(g).strip()
            if genre_name:
                genre_groups.setdefault(genre_name, []).append(item)

    # Report the genre groups found.
    print("\nFound the following genre groups:")
    for genre, items in genre_groups.items():
        print(f"  {genre}: {len(items)} items")

    # Process each genre group to update or create collections.
    for genre, items in tqdm(genre_groups.items(), desc="Processing genres", total=len(genre_groups), unit="genre"):
        tqdm.write(f"\nProcessing Genre: {genre} ({len(items)} items)")
        if genre in existing_collections:
            collection = existing_collections[genre]
            tqdm.write(f"  Updating existing collection: {genre}")
            existing_items = collection.items()  # Cache existing items.
            new_items = [i for i in items if i not in existing_items]
            if new_items:
                collection.addItems(new_items)
        else:
            tqdm.write(f"  Creating new collection: {genre}")
            new_collection = library.createCollection(genre, items)
            existing_collections[genre] = new_collection

    print("\nDone! Plex collections based on file-extracted Genre have been updated.")

if __name__ == '__main__':
    main()
