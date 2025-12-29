#!/usr/bin/env python3
import argparse
from plexapi.myplex import MyPlexAccount
from plexapi.exceptions import NotFound

def main():
    # Define command-line arguments.
    parser = argparse.ArgumentParser(
        description="Update Plex Collections based on Genre from a specified library."
    )
    parser.add_argument("library", help="The name of the Plex library (e.g., 'Music')")
    parser.add_argument("--username", required=True, help="Your Plex username")
    parser.add_argument("--password", required=True, help="Your Plex password")
    parser.add_argument("--server", required=True, help="Name of your Plex server")
    args = parser.parse_args()

    # Log in to Plex using your credentials.
    account = MyPlexAccount(args.username, args.password)
    plex = account.resource(args.server).connect()

    # Get the specified library.
    library = plex.library.section(args.library)

    # Build a mapping: genre -> list of items.
    genre_groups = {}
    for item in library.search():
        genres = item.genre
        if not genres:
            continue
        for g in genres:
            # Check if it's a Plex object (with a 'tag' attribute) or a string.
            genre_name = g.tag if hasattr(g, 'tag') else str(g)
            genre_name = genre_name.strip()
            if genre_name:
                genre_groups.setdefault(genre_name, []).append(item)

    print("Found the following genre groups:")
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
