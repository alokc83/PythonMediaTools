#!/usr/bin/env python3
import getpass
import requests
from plexapi.myplex import MyPlexAccount
from plexapi.exceptions import NotFound
from tqdm import tqdm

def get_audio_file(item):
    """
    Check if the Plex item has at least one media part with a file ending in .mp3 or .m4a.
    """
    try:
        for media in item.media:
            for part in media.parts:
                if part.file.lower().endswith(('.mp3', '.m4a')):
                    return True
    except Exception as e:
        print(f"Error reading media parts for {item.title}: {e}")
    return False

def get_genre_from_openlibrary(query):
    """
    Query the Open Library API with the provided query (e.g., the item's title) and return a genre.
    This function uses the first subject from the first matching document as a fallback genre.
    """
    url = f"https://openlibrary.org/search.json?q={query}"
    try:
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Open Library API returned status code {response.status_code} for query: {query}")
            return None
        data = response.json()
        if data.get('docs'):
            # Use the first document's 'subject' field if available.
            subjects = data['docs'][0].get('subject', [])
            if subjects:
                return subjects[0]  # Use the first subject as the genre
    except Exception as e:
        print("Error contacting Open Library API:", e)
    return None

def main():
    # Ask for user inputs interactively.
    library_name = input("Enter the Plex library name (e.g., 'Music'): ").strip()
    username = input("Enter your Plex username: ").strip()
    password = getpass.getpass("Enter your Plex password: ")
    server_name = input("Enter your Plex server name (the friendly name as in your account): ").strip()
    use_openlibrary = input("Fetch genre info from Open Library if missing? (Y/n): ").strip().lower() or 'y'

    # Log in to Plex using your credentials.
    account = MyPlexAccount(username, password)
    plex = account.resource(server_name).connect()

    # Get the specified library.
    library = plex.library.section(library_name)

    # Fetch existing collections.
    existing_collections = {collection.title: collection for collection in library.collections()}
    print("\nExisting collections:")
    for title in existing_collections:
        print(f"  {title}")

    # Convert the library search results to a list so we can measure progress.
    all_items = list(library.search())
    print(f"\nFound {len(all_items)} items in the library.")

    # Build a mapping: genre -> list of items.
    genre_groups = {}
    for item in tqdm(all_items, desc="Processing audio items", unit="item"):
        # Only consider audio items (MP3/M4A).
        if not get_audio_file(item):
            continue

        # Attempt to retrieve genre metadata.
        genres = None
        if hasattr(item, 'genres'):
            genres = item.genres
        elif hasattr(item, 'genre'):
            genres = item.genre

        # If no genre metadata is found, try the Open Library API (if opted in).
        if not genres:
            if use_openlibrary.startswith('y'):
                genre_from_openlibrary = get_genre_from_openlibrary(item.title)
                if genre_from_openlibrary:
                    genres = [genre_from_openlibrary]
                else:
                    genres = []
            else:
                genres = []

        # Normalize and group by genre.
        for g in genres:
            # g might be an object with a 'tag' property or just a string.
            genre_name = g.tag if hasattr(g, 'tag') else str(g)
            genre_name = genre_name.strip()
            if genre_name:
                genre_groups.setdefault(genre_name, []).append(item)

    print("\nFound the following genre groups:")
    for genre, items in genre_groups.items():
        print(f"  {genre}: {len(items)} items")

    # Process each genre group with a progress bar.
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

    print("\nDone! Plex collections based on Genre have been updated.")

if __name__ == '__main__':
    main()
