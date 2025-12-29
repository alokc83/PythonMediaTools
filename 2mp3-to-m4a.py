#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil
import json

def run_command(command, text=True):
    """Run a subprocess command; set text=False for binary output."""
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)
    return result.returncode, result.stdout, result.stderr

def get_filtered_metadata(filename):
    """Return a dictionary of metadata for the file, filtering out non-essential keys."""
    command = ["exiftool", "-j", filename]
    ret, out, err = run_command(command)
    if ret != 0:
        print(f"Error reading metadata from {filename}: {err}")
        return {}
    try:
        data = json.loads(out)[0]
    except Exception as e:
        print(f"Error parsing JSON metadata for {filename}: {e}")
        return {}
    # Keys to ignore for our comparison (container-specific or file-system tags)
    ignore_keys = {
        "SourceFile", "ExifToolVersion", "FileName", "Directory", "FileSize",
        "FileModifyDate", "FileAccessDate", "FileCreateDate", "FilePermissions",
        "MIMEType", "Warning", "ImageWidth", "ImageHeight"
    }
    filtered = {}
    for key, value in data.items():
        if key not in ignore_keys:
            filtered[key] = str(value).strip()
    return filtered

def metadata_matches(mp3_meta, m4a_meta):
    """
    Check if all keys/values in mp3_meta are present in m4a_meta.
    Comparison is done as strings.
    """
    for key, mp3_value in mp3_meta.items():
        m4a_value = m4a_meta.get(key, None)
        if m4a_value is None:
            # Key missing in M4A
            return False
        if str(m4a_value).strip() != mp3_value:
            # Value differs
            return False
    return True

def main():
    target_dir = input("Enter the folder path where the MP3 files are located: ").strip()
    if not os.path.isdir(target_dir):
        print(f"Directory '{target_dir}' does not exist. Exiting.")
        sys.exit(1)
    
    os.chdir(target_dir)
    os.makedirs("mp3", exist_ok=True)
    os.makedirs("m4a", exist_ok=True)
    
    mp3_files = [f for f in os.listdir('.') if f.lower().endswith('.mp3')]
    if not mp3_files:
        print("No MP3 files found in the directory.")
        return
    
    for file in mp3_files:
        base_name, _ = os.path.splitext(file)
        output_file = f"{base_name}.m4a"
        target_converted = os.path.join("m4a", output_file)
        target_original = os.path.join("mp3", file)
        
        # If the M4A already exists, compare metadata
        if os.path.exists(target_converted):
            print(f"M4A file '{target_converted}' exists. Comparing metadata...")
            mp3_meta = get_filtered_metadata(file)
            m4a_meta = get_filtered_metadata(target_converted)
            if metadata_matches(mp3_meta, m4a_meta):
                print(f"Metadata in '{target_converted}' matches '{file}'. Skipping conversion.")
                continue
            else:
                print(f"Metadata differs. Re-converting '{file}' to update metadata.")
        
        print(f"Converting '{file}' to M4A...")
        ffmpeg_command = [
            "ffmpeg",
            "-nostdin",            # Prevent ffmpeg from waiting for input
            "-i", file,
            "-vn",                 # disable video streams
            "-c:a", "aac",         # use AAC audio codec
            "-b:a", "16k",         # 16k bitrate (suitable for audiobooks)
            output_file
        ]
        ret, out, err = run_command(ffmpeg_command)
        if ret != 0:
            print(f"Conversion failed for {file}. Error:")
            print(err)
            continue
        
        # Copy metadata using exiftool
        print(f"Copying metadata from {file} to {output_file}...")
        exif_command = [
            "exiftool",
            "-overwrite_original",
            "-TagsFromFile", file,
            "-all:all",
            output_file
        ]
        ret, out, err = run_command(exif_command)
        if ret != 0:
            print(f"Metadata copying failed for {file}. Error:")
            print(err)
        else:
            print("Metadata copied.")
        
        # Extract and embed cover art using AtomicParsley
        cover_art = "cover.jpg"
        print(f"Extracting cover art from {file}...")
        extract_command = [
            "exiftool",
            "-b",
            "-Picture",
            file
        ]
        ret, cover_data, err = run_command(extract_command, text=False)
        if ret == 0 and cover_data:
            with open(cover_art, "wb") as f:
                f.write(cover_data)
            print("Embedding cover art into M4A using AtomicParsley...")
            atomic_command = [
                "AtomicParsley",
                output_file,
                "--artwork", cover_art,
                "--overWrite"
            ]
            ret, out, err = run_command(atomic_command)
            if ret != 0:
                print(f"AtomicParsley failed for {file}. Error:")
                print(err)
            else:
                print("Cover art embedded successfully.")
            os.remove(cover_art)
        else:
            print("No cover art found or extraction failed; skipping cover art embedding.")
        
        print("Moving files to respective folders.")
        shutil.move(file, target_original)
        shutil.move(output_file, target_converted)

if __name__ == "__main__":
    main()