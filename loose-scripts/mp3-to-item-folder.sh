#!/usr/bin/env bash
set -euo pipefail

# Move each .mp3 into a folder named after the file (without extension).
# Example: "My Song.mp3" -> "My Song/My Song.mp3"

shopt -s nullglob

for f in *.mp3 *.MP3; do
  [[ -f "$f" ]] || continue

  base="${f%.*}"
  mkdir -p "$base"
  mv -n -- "$f" "$base/"
done
