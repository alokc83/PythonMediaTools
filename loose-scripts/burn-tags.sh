#!/usr/bin/env bash
set -euo pipefail

# Usage
#   ./burn-tags-genre.sh /path/to/root
#
# Optional
#   DRYRUN=1 ./burn-tags-genre.sh /path/to/root
#   TAG_KEY=TAGS ./burn-tags-genre.sh /path/to/root

ROOT="${1:-}"
if [[ -z "$ROOT" || ! -d "$ROOT" ]]; then
  echo "Usage: $0 /path/to/root"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found in PATH"
  exit 1
fi

DRYRUN="${DRYRUN:-0}"
TAG_KEY="${TAG_KEY:-TAGS}"

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

make_list_from_parent() {
  local parent_name="$1"
  local out="" part
  IFS=',' read -r -a parts <<<"$parent_name"

  for part in "${parts[@]}"; do
    part="$(trim "$part")"
    [[ -n "$part" ]] || continue
    if [[ -z "$out" ]]; then
      out="$part"
    else
      out="${out};${part}"
    fi
  done

  printf '%s' "$out"
}

files_total=0
files_updated=0

while IFS= read -r -d '' f; do
  files_total=$((files_total + 1))

  parent_dir="$(basename "$(dirname "$f")")"
  value_list="$(make_list_from_parent "$parent_dir")"

  if [[ -z "$value_list" ]]; then
    echo "Skip (empty parent name): $f"
    continue
  fi

  if [[ "$DRYRUN" == "1" ]]; then
    echo "Would set for: $f"
    echo "  genre = $value_list"
    echo "  $TAG_KEY = $value_list"
    continue
  fi

  dir_path="$(dirname "$f")"
  base_name="$(basename "$f")"
  tmp_file="${dir_path}/.${base_name}.tmp.$$"

  ffmpeg -hide_banner -loglevel error -y \
    -i "$f" \
    -map 0:a -c copy \
    -map_metadata 0 \
    -id3v2_version 3 \
    -write_id3v1 1 \
    -metadata "genre=$value_list" \
    -metadata "${TAG_KEY}=$value_list" \
    -f mp3 \
    "$tmp_file"

  mv -f -- "$tmp_file" "$f"
  files_updated=$((files_updated + 1))

done < <(find "$ROOT" -type f -iname "*.mp3" -print0)

echo ""
echo "Done"
echo "MP3 files found: $files_total"
echo "MP3 files updated: $files_updated"
echo "Custom tag key used: $TAG_KEY"
