#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil

# For MP3 metadata copying via mutagen
try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TCON, TRCK, TDRC, ID3NoHeaderError
    from mutagen.mp4 import MP4
except ImportError:
    print("Mutagen is not installed. Please install it via 'pip install mutagen'")
    sys.exit(1)

def run_command(command, text=True):
    """Run a command and return (returncode, stdout, stderr)."""
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)
    return result.returncode, result.stdout, result.stderr

def get_bitrate(filename):
    """
    Use ffprobe to retrieve the bitrate (in kbps) of the first audio stream.
    Falls back to overall file bitrate if needed.
    Returns None if it cannot be determined.
    """
    # Try audio stream bitrate first
    command = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=bit_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filename
    ]
    ret, out, err = run_command(command)
    if ret == 0 and out.strip():
        try:
            bitrate_bps = int(out.strip())
            return bitrate_bps / 1000.0
        except Exception:
            pass

    # Fallback: use overall file bitrate
    command = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=bit_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filename
    ]
    ret, out, err = run_command(command)
    if ret == 0 and out.strip():
        try:
            bitrate_bps = int(out.strip())
            return bitrate_bps / 1000.0
        except Exception as e:
            print(f"Error parsing format bitrate for '{filename}': {e}")
            return None
    return None

def copy_metadata_to_mp3(source_file, target_file):
    """
    Copy textual metadata and cover art from source_file to target_file,
    converting from source type (MP3 or M4A) to MP3's ID3 tags.
    Returns True if successful, False otherwise.
    """
    try:
        src = MutagenFile(source_file, easy=True)
    except Exception as e:
        print(f"Error reading source metadata from '{source_file}': {e}")
        src = None

    try:
        target_tags = ID3(target_file)
    except ID3NoHeaderError:
        target_tags = ID3()

    if src is not None and src.tags:
        mapping = {
            "title": TIT2,
            "artist": TPE1,
            "album": TALB,
            "genre": TCON,
            "tracknumber": TRCK,
            "date": TDRC,
        }
        for tag, frame_class in mapping.items():
            if tag in src:
                val = src[tag][0]
                target_tags.delall(frame_class.__name__)
                target_tags.add(frame_class(encoding=3, text=val))

    cover_data = None
    cover_mime = None
    ext = os.path.splitext(source_file)[1].lower()
    if ext == ".mp3":
        try:
            src_id3 = ID3(source_file)
            apic_frames = src_id3.getall("APIC")
            if apic_frames:
                cover_data = apic_frames[0].data
                cover_mime = apic_frames[0].mime
        except Exception as e:
            print(f"Error reading cover art from '{source_file}': {e}")
    elif ext == ".m4a":
        try:
            src_mp4 = MP4(source_file)
            if 'covr' in src_mp4:
                cover_data = src_mp4['covr'][0]
                cover_mime = "image/jpeg"
        except Exception as e:
            print(f"Error reading cover art from '{source_file}': {e}")
    
    if cover_data is not None and cover_mime is not None:
        target_tags.delall("APIC")
        target_tags.add(APIC(encoding=3, mime=cover_mime, type=3, desc="Cover", data=cover_data))
    
    try:
        target_tags.save(target_file)
        print("Metadata copied using mutagen.")
        return True
    except Exception as e:
        print(f"Error saving metadata to '{target_file}': {e}")
        return False

def main():
    target_dir = input("Enter the folder path where the MP3/M4A files are located: ").strip()
    # Remove any backslashes (if the path was copied with escapes)
    target_dir = target_dir.replace("\\", "")
    
    if not os.path.isdir(target_dir):
        print(f"Directory '{target_dir}' does not exist. Exiting.")
        sys.exit(1)
    
    os.chdir(target_dir)
    
    print("Select output file type:")
    print("1) 64kbps MP3")
    print("2) 64kbps M4A")
    choice = input("Enter 1 or 2: ").strip()
    
    if choice == "1":
        codec = "libmp3lame"
        out_ext = ".mp3"
        use_mutagen = True
    elif choice == "2":
        codec = "aac"
        out_ext = ".m4a"
        use_mutagen = False  # For M4A, we'll skip metadata copy in this example.
    else:
        print("Invalid selection. Exiting.")
        sys.exit(1)
    
    # Create output folders.
    conv_folder = "64k"         # Destination for all converted files (our success folder).
    failed_folder = "failed"      # Files with errors.
    converted_folder = "converted"  # Original files that were successfully converted.
    os.makedirs(conv_folder, exist_ok=True)
    os.makedirs(failed_folder, exist_ok=True)
    os.makedirs(converted_folder, exist_ok=True)
    
    # Gather all files with .mp3 or .m4a extension.
    audio_files = [f for f in os.listdir('.') if f.lower().endswith(('.mp3', '.m4a'))]
    if not audio_files:
        print("No MP3 or M4A files found in the specified directory.")
        sys.exit(0)
    
    threshold = 70  # kbps threshold
    
    for file in audio_files:
        current_bitrate = get_bitrate(file)
        if current_bitrate is not None:
            print(f"Determined bitrate for '{file}': {current_bitrate:.2f} kbps")
            if current_bitrate <= threshold:
                print(f"File '{file}' is at or below {threshold} kbps; skipping conversion.")
                continue
        else:
            print(f"Could not determine bitrate for '{file}'; proceeding with conversion.")
        
        base_name, _ = os.path.splitext(file)
        output_file = f"{base_name}{out_ext}"
        
        print(f"Converting '{file}' to 64kbps {out_ext.upper()}...")
        ffmpeg_command = [
            "ffmpeg", "-nostdin", "-i", file, "-vn",
            "-c:a", codec, "-b:a", "64k",
            output_file
        ]
        ret, out, err = run_command(ffmpeg_command)
        conversion_success = (ret == 0)
        if not conversion_success:
            print(f"Error converting '{file}':")
            print(err)
        
        metadata_success = True
        if conversion_success and use_mutagen:
            print(f"Copying metadata from '{file}' to '{output_file}' using mutagen...")
            metadata_success = copy_metadata_to_mp3(file, output_file)
        elif conversion_success:
            print("Skipping metadata copy for M4A output.")
        
        overall_success = conversion_success and metadata_success
        
        # If a converted file exists, move it into conv_folder.
        if os.path.exists(output_file):
            conv_dest = os.path.join(conv_folder, output_file)
            shutil.move(output_file, conv_dest)
            print(f"Converted file moved to '{conv_folder}' folder.")
        else:
            conv_dest = None
        
        if overall_success and conv_dest is not None:
            # Move the original file to the converted_folder.
            orig_dest = os.path.join(converted_folder, file)
            shutil.move(file, orig_dest)
            print(f"Original file '{file}' moved to '{converted_folder}' folder.")
        else:
            # If conversion failed, move the converted file (if it exists) to failed_folder.
            if conv_dest is not None:
                failed_dest = os.path.join(failed_folder, os.path.basename(conv_dest))
                shutil.move(conv_dest, failed_dest)
                print(f"Converted file moved to '{failed_folder}' folder due to errors.")
            else:
                print(f"No converted file available for '{file}'.")

if __name__ == '__main__':
    main()
