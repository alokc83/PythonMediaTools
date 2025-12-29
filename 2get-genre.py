#!/usr/bin/env python3
import os
import time
import requests
from mutagen import File as MutagenFile
from tqdm import tqdm

def get_book_categories_google(book_title, api_key="abc1234", delay=1):
    """
    Query the Google Books API for a given book title and return the categories
    from the first result that has them. Uses the provided API key and adds a delay.
    """
    query = f"intitle:{book_title}"
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": query, "maxResults": 5, "key": api_key}

    # Delay to help avoid hitting rate limits.
    time.sleep(delay)
    
    response = requests.get(url, params=params)
    if response.status_code == 429:
        print(f"Error: Google Books API returned status code 429. Rate limit exceeded.")
        return None
    elif response.status_code == 403:
        print(f"Error: Google Books API returned status code 403. Check your API key and permissions.")
        return None
    elif response.status_code != 200:
        print(f"Error: Google Books API returned status code {response.status_code}")
        return None

    data = response.json()
    items = data.get("items", [])
    if not items:
        print("No results found on Google Books for the title.")
        return None

    # Look for the first result that has categories.
    for item in items:
        volume_info = item.get("volumeInfo", {})
        categories = volume_info.get("categories")
        if categories:
            return categories

    print("No category information found on Google Books for the book.")
    return None

def get_book_categories_openlibrary(book_title):
    """
    Query the OpenLibrary API for a given book title and return the subjects
    (as genre information) from the first result that has them.
    """
    url = "https://openlibrary.org/search.json"
    params = {"title": book_title, "limit": 5}
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"Error: OpenLibrary API returned status code {response.status_code}")
        return None

    data = response.json()
    docs = data.get("docs", [])
    if not docs:
        print("No results found on OpenLibrary for the title.")
        return None

    # Look for the first result that has subjects.
    for doc in docs:
        subjects = doc.get("subject")
        if subjects:
            return subjects

    print("No subject information found on OpenLibrary for the book.")
    return None

def extract_title_from_file(file_path):
    """
    Extract a title from an audio file's metadata.
    Prefer the 'album' tag over the 'title' tag.
    """
    try:
        audio = MutagenFile(file_path, easy=True)
        if audio is None:
            return None
        album = audio.get("album", [])
        if album:
            return album[0]
        title = audio.get("title", [])
        if title:
            return title[0]
    except Exception as e:
        print(f"Error reading metadata from '{file_path}': {e}")
    return None

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

def write_genre_to_file(file_path, genres):
    """
    Write the provided genres (a list of strings) into the audio file's metadata under the 'genre' tag.
    """
    try:
        audio = MutagenFile(file_path, easy=True)
        if audio is None:
            print(f"Error: Could not open file '{file_path}' for updating metadata.")
            return False
        # Set the genre tag to the provided genres.
        audio["genre"] = genres
        audio.save()
        print(f"Updated file '{file_path}' with genre: {genres}")
        return True
    except Exception as e:
        print(f"Error updating genre for file '{file_path}': {e}")
        return False

def main():
    print("=== Book Genre Retriever & Metadata Updater ===")
    user_input = input("Enter the book title (or press Enter to use a directory of audiobooks): ").strip()
    
    if user_input:
        # Single book title mode.
        book_title = user_input
        print(f"\nQuerying Google Books API for '{book_title}'...")
        categories = get_book_categories_google(book_title)
        if categories:
            print("\nCategories (genres) found via Google Books:")
            for cat in categories:
                print(f" - {cat}")
        else:
            print("\nNo categories found on Google Books. Trying OpenLibrary as backup...")
            categories = get_book_categories_openlibrary(book_title)
            if categories:
                print("\nSubjects (genres) found via OpenLibrary:")
                for subj in categories:
                    print(f" - {subj}")
            else:
                print("\nNo category/subject information found for the book.")
    else:
        # Directory mode: process all audiobook files.
        root_dir = input("Enter the root directory for audiobooks: ").strip()
        if not os.path.isdir(root_dir):
            print(f"Error: '{root_dir}' is not a valid directory.")
            return
        
        print(f"\nScanning directory '{root_dir}' for audiobook files...")
        audio_files = scan_audio_files(root_dir)
        if not audio_files:
            print("No audio files found in the directory.")
            return
        
        print(f"Found {len(audio_files)} audio files.\n")
        
        # Process each file.
        for file_path in tqdm(audio_files, desc="Processing files", unit="file"):
            query = extract_title_from_file(file_path)
            if not query:
                print(f"Skipping '{file_path}': No title metadata found.")
                continue
            
            print(f"\nProcessing file: {file_path}")
            print(f"Extracted title/album: {query}")
            
            # Try to get genre info via Google Books first.
            categories = get_book_categories_google(query)
            if not categories:
                print("No categories found on Google Books. Trying OpenLibrary as backup...")
                categories = get_book_categories_openlibrary(query)
            
            if categories:
                print("Genres found:")
                for cat in categories:
                    print(f" - {cat}")
                # Write the genre metadata back into the file.
                write_genre_to_file(file_path, categories)
            else:
                print("No category/subject information found for this file.")
                    
if __name__ == '__main__':
    main()
