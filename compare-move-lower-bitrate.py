import os
import shutil
from mutagen import File

def get_audio_metadata(filepath):
    """
    Reads the album metadata and bitrate for an audio file.
    For MP3 files, album is read from the TALB tag.
    For M4A files, album is read from the equivalent \xa9alb atom.
    Returns a tuple of (album, bitrate) where bitrate is in bits per second.
    """
    album = ""
    bitrate = 0
    ext = os.path.splitext(filepath)[1].lower()

    try:
        if ext == ".mp3":
            from mutagen.mp3 import MP3
            from mutagen.id3 import ID3NoHeaderError
            try:
                audio = MP3(filepath)
            except ID3NoHeaderError:
                audio = MP3(filepath, ID3=None)
            # MP3 album metadata is stored under the TALB tag.
            tag = audio.tags.get('TALB') if audio.tags else None
            if tag and hasattr(tag, 'text'):
                album = tag.text[0].strip() if tag.text else ""
            if hasattr(audio, 'info') and hasattr(audio.info, 'bitrate'):
                bitrate = audio.info.bitrate

        elif ext == ".m4a":
            from mutagen.mp4 import MP4
            audio = MP4(filepath)
            # M4A stores album metadata in the \xa9alb atom.
            album_list = audio.tags.get('\xa9alb') if audio.tags else None
            if album_list:
                album = album_list[0].strip() if album_list[0] else ""
            if hasattr(audio, 'info') and hasattr(audio.info, 'bitrate'):
                bitrate = audio.info.bitrate

        else:
            # Fallback for other file types.
            audio = File(filepath)
            if audio and audio.tags:
                album = str(audio.tags.get('TALB', "")).strip()
            if hasattr(audio, 'info') and hasattr(audio.info, 'bitrate'):
                bitrate = audio.info.bitrate

    except Exception as e:
        print(f"Error reading metadata from {filepath}: {e}")

    return album, bitrate

def main():
    # Prompt the user for the directory containing audio files.
    directory = input("Enter the directory containing audio files: ").strip()

    if not os.path.isdir(directory):
        print("Invalid directory. Exiting.")
        return

    # Create the 'toDelete' folder inside the input directory if it doesn't exist.
    to_delete_dir = os.path.join(directory, "toDelete")
    if not os.path.exists(to_delete_dir):
        os.makedirs(to_delete_dir)

    # Dictionary to group files by album.
    album_groups = {}
    album_list = set()

    # Process each file in the directory.
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        # Only process files and skip the 'toDelete' folder.
        if os.path.isfile(filepath) and "toDelete" not in filepath:
            album, bitrate = get_audio_metadata(filepath)
            # Convert bitrate from bits per second to kbps.
            bitrate_kbps = bitrate // 1000 if bitrate else 0
            if album:
                album_list.add(album)
                album_groups.setdefault(album, []).append((filepath, bitrate))
                print(f"Found file: '{filename}' | Album: '{album}' | Bitrate: {bitrate_kbps} kbps")
            else:
                print(f"File '{filename}' does not have album metadata; skipping.")

    # Display the unique albums found.
    if album_list:
        print("\nUnique albums found in the folder:")
        for alb in sorted(album_list):
            print(f" - {alb}")
    else:
        print("No album metadata found in any file.")

    # For each album with two or more files, move the file(s) with a lower bitrate.
    for album, files in album_groups.items():
        if len(files) > 1:
            # Determine the maximum bitrate in the group.
            max_bitrate = max(bitrate for _, bitrate in files)
            max_bitrate_kbps = max_bitrate // 1000 if max_bitrate else 0
            for filepath, bitrate in files:
                bitrate_kbps = bitrate // 1000 if bitrate else 0
                if bitrate < max_bitrate:
                    print(f"Moving '{filepath}' (Album: '{album}', bitrate: {bitrate_kbps} kbps, max: {max_bitrate_kbps} kbps) to {to_delete_dir}")
                    try:
                        shutil.move(filepath, to_delete_dir)
                    except Exception as e:
                        print(f"Error moving file '{filepath}': {e}")

if __name__ == '__main__':
    main()
