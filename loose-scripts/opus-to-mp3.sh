#!/bin/bash

# Display encoding mode menu
echo "Select encoding mode:"
echo "1) Constant Bitrate (CBR)"
echo "2) Variable Bitrate (VBR)"
read -p "Enter your choice (1-2): " mode

if [ "$mode" -eq 1 ]; then
  # CBR mode: choose a fixed bitrate value
  echo "Select CBR bitrate setting:"
  echo "1) 16k"
  echo "2) 32k"
  echo "3) 48k"
  read -p "Enter your choice (1-3): " cbr_choice

  case "$cbr_choice" in
    1)
      bitrate="16k"
      ;;
    2)
      bitrate="32k"
      ;;
    3)
      bitrate="48k"
      ;;
    *)
      echo "Invalid selection. Exiting."
      exit 1
      ;;
  esac

  # Set target folder and create it if needed
  target_folder="$bitrate"
  mkdir -p "$target_folder"

  for file in *.opus; do
    # Skip if no matching file exists
    [ -e "$file" ] || continue

    output_file="${file%.opus}.mp3"
    target_path="$target_folder/$output_file"
    # Check if the MP3 file already exists in the target folder
    if [ -f "$target_path" ]; then
      echo "MP3 file '$target_path' already exists, skipping conversion for $file."
      continue
    fi

    echo "Converting $file to MP3 at constant bitrate $bitrate..."
    ffmpeg -i "$file" -c:a libmp3lame -b:a "$bitrate" "$output_file"

    if [ $? -eq 0 ]; then
      echo "Conversion successful. Moving $output_file to folder $target_folder."
      mv "$output_file" "$target_folder/"
    else
      echo "Conversion failed for $file."
    fi
  done

elif [ "$mode" -eq 2 ]; then
  # VBR mode: prompt for VBR quality value
  echo "Enter VBR quality value (0 is best quality, 9 is worst):"
  read -p "VBR quality (0-9): " vbr_quality

  # Validate that vbr_quality is a single digit 0-9
  if ! [[ "$vbr_quality" =~ ^[0-9]$ ]]; then
    echo "Invalid VBR quality value. Exiting."
    exit 1
  fi

  target_folder="vbr-$vbr_quality"
  mkdir -p "$target_folder"

  for file in *.opus; do
    [ -e "$file" ] || continue

    output_file="${file%.opus}.mp3"
    target_path="$target_folder/$output_file"
    if [ -f "$target_path" ]; then
      echo "MP3 file '$target_path' already exists, skipping conversion for $file."
      continue
    fi

    echo "Converting $file to MP3 using VBR quality $vbr_quality..."
    ffmpeg -i "$file" -c:a libmp3lame -q:a "$vbr_quality" "$output_file"

    if [ $? -eq 0 ]; then
      echo "Conversion successful. Moving $output_file to folder $target_folder."
      mv "$output_file" "$target_folder/"
    else
      echo "Conversion failed for $file."
    fi
  done

else
  echo "Invalid selection. Exiting."
  exit 1
fi