#!/usr/bin/env bash
set -euo pipefail

# Move each audio file into a folder named after the file (without extension).
# Example: "My Book.m4b" -> "My Book/My Book.m4b"

shopt -s nullglob

extensions=(mp3 MP3 m4a M4A m4b M4B)

for ext in "${extensions[@]}"; do
  for f in *."$ext"; do
    [[ -f "$f" ]] || continue

    base="${f%.*}"

    # If a file exists with the folder name, do not clobber it
    if [[ -e "$base" && ! -d "$base" ]]; then
      echo "Skip: '$f' because '$base' exists and is not a directory" >&2
      continue
    fi

    mkdir -p -- "$base"
    mv -n -- "$f" "$base/"
  done
done
