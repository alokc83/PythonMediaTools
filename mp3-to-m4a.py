#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil

def main():
    target_dir = input("Enter the folder path where the MP3 files are located: ").strip()
    if not os.path.isdir(target_dir):
        print(f"Directory '{target_dir}' does not exist. Exiting.")
        sys.exit(1)
    
    # Change to the target directory
    os.chdir(target_dir)
    
    # Create the required subdirectories if they do not exist
    os.makedirs("mp3", exist_ok=True)
    os.makedirs("m4a", exist_ok=True)
    
    # Find all MP3 files in the current directory
    mp3_files = [f for f in os.listdir('.') if f.lower().endswith('.mp3')]
    if not mp3_files:
        print("No MP3 files found in the directory.")
        return
    
    for file in mp3_files:
        # Define the output filename with the .m4a extension
        base_name, _ = os.path.splitext(file)
        output_file = f"{base_name}.m4a"
        target_converted = os.path.join("m4a", output_file)
        target_original = os.path.join("mp3", file)
        
        # If the converted file already exists in the m4a folder, skip conversion
        if os.path.exists(target_converted):
            print(f"Converted file '{target_converted}' already exists. Skipping {file}.")
            continue
        
        print(f"Converting '{file}' to M4A...")
        # Build the ffmpeg command with metadata mapping and movflags for MP4 containers
        command = [
            "ffmpeg",
            "-i", file,
            "-vn",                    # disable video streams
            "-c:a", "aac",            # use AAC audio codec
            "-b:a", "16k",            # set audio bitrate to 16k (suitable for audiobooks)
            "-movflags", "use_metadata_tags",  # enable metadata tags for MP4 container
            "-map_metadata", "0",     # copy all metadata from input to output
            output_file
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print(f"Conversion successful for {file}.")
            print("Moving original MP3 to 'mp3' folder and converted M4A to 'm4a' folder.")
            shutil.move(file, target_original)
            shutil.move(output_file, target_converted)
        else:
            print(f"Conversion failed for {file}.")
            print("Error output:")
            print(result.stderr)

if __name__ == "__main__":
    main()
