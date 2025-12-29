#!/usr/bin/env python3
import getpass
from plexapi.myplex import MyPlexAccount
from plexapi.exceptions import NotFound

def main():
    # Ask for user inputs interactively.
    library_name = input("Enter the Plex library name (e.g., 'Music'): ").strip()
    username = input("Enter your Plex username: ").strip()
    password = getpass.getpass("Enter your Plex password: ")
    server_name = input("Enter your Plex server name: ").strip()

    # Log in to Plex using your credentials.
    account = MyPlexAccount(username, password)
    plex = account.resource(server_name).connect()

    # Get the specified library.
    library = plex.library.section(library_name)

    # Build a mapping: genre -> list of items.
    genre_groups = {}
    for item in library.search():
        genres = item.genre
        if not genres:
            continue
        for g in genres:
            # Handle both Plex objects (with a 'tag' attribute) and strings.
            genre_name = g.tag if hasattr(g, 'tag') else str(g)
            genre_name = genre_name.strip()
            if genre_name:
                genre_groups.setdefault(genre_name, []).append(item)

    print("\nFound the following genre groups:")
    for genre, items in genre_groups.items():
        print(f"  {genre}: {len(items)} items")

    # Create or update collections for each genre.
    for genre, items in genre_groups.items():
        print(f"\nProcessing Genre: {genre} ({len(items)} items)")
        try:
            # Try to fetch an existing collection with this genre name.
            collection = library.collection(genre)
            print(f"  Updating existing collection: {genre}")
            existing_items = collection.items()  # Cache existing items.
            new_items = [i for i in items if i not in existing_items]
            if new_items:
                collection.addItems(new_items)
        except NotFound:
            # If not found, create a new collection.
            print(f"  Creating new collection: {genre}")
            library.createCollection(genre, items)

    print("\nDone! Plex collections based on Genre have been updated.")

if __name__ == '__main__':
    main()
