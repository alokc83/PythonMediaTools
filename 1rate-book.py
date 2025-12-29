#!/usr/bin/env python3
import os
from mutagen import File as MutagenFile
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
    root_dir = input("Enter the root directory for audio files: ").strip()
    use_fallback = input("If genre is missing, mark it as 'Unknown'? (Y/n): ").strip().lower() or 'y'
    
    print("\nScanning for audio files...")
    audio_files = scan_audio_files(root_dir)
    print(f"Found {len(audio_files)} audio files.")
    
    # Build a mapping of genre -> list of file paths
    genre_to_files = {}
    for file in tqdm(audio_files, desc="Extracting genres", unit="file"):
        genres = extract_genre(file)
        if not genres and use_fallback.startswith('y'):
            genres = ["Unknown"]
        for genre in genres:
            genre = genre.strip()
            if genre:
                genre_to_files.setdefault(genre, []).append(file)
    
    print("\nGenres found from files:")
    for genre, files in genre_to_files.items():
        print(f"  {genre}: {len(files)} files")
    
    # Optional: Print the full list of files per genre.
    # for genre, files in genre_to_files.items():
    #     print(f"\nGenre: {genre}")
    #     for f in files:
    #         print(f"  {f}")

if __name__ == '__main__':
    main()
