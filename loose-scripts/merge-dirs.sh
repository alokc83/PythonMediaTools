#!/usr/bin/env bash
set -euo pipefail

# merge_mp3_sha256.sh
#
# Usage:
#   ./merge_mp3_sha256.sh "/path/to/dir1" "/path/to/dir2" "/path/to/outdir"
#
# Optional:
#   DRYRUN=1 ./merge_mp3_sha256.sh ...   # print actions only
#
# Behavior:
#   - Recursively finds .mp3 files in dir1 and dir2
#   - Computes SHA-256 for each file
#   - First file for a given hash is moved to outdir
#   - Duplicates (same hash) are skipped
#   - For moved file, creates folder named after file base name and puts file inside it

DIR1="${1:-}"
DIR2="${2:-}"
OUT="${3:-}"

if [[ -z "$DIR1" || -z "$DIR2" || -z "$OUT" ]]; then
  echo "Usage: $0 <dir1> <dir2> <outdir>"
  exit 1
fi

if [[ ! -d "$DIR1" || ! -d "$DIR2" ]]; then
  echo "Error: dir1 and dir2 must be directories."
  exit 1
fi

mkdir -p "$OUT"
DRYRUN="${DRYRUN:-0}"

hash_file() {
  # macOS typically has shasum; many Linux distros have sha256sum
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    echo "Error: need shasum or sha256sum."
    exit 1
  fi
}

sanitize_folder_name() {
  # Folder name is based on file base name.
  # Remove path separators and trim leading/trailing spaces.
  local s="$1"
  s="${s//\//_}"
  while [[ "${s%" "}" != "$s" ]]; do s="${s%" "}"; done
  while [[ "${s#" "}" != "$s" ]]; do s="${s#" "}"; done
  printf '%s' "$s"
}

unique_dest_dir() {
  # If OUT/base exists, use OUT/base (2), OUT/base (3), ...
  local base="$1"
  local candidate="$OUT/$base"
  if [[ ! -e "$candidate" ]]; then
    printf '%s' "$candidate"
    return
  fi
  local n=2
  while :; do
    candidate="$OUT/$base ($n)"
    if [[ ! -e "$candidate" ]]; then
      printf '%s' "$candidate"
      return
    fi
    n=$((n + 1))
  done
}

# temp index of seen hashes
tmp_dir="$(mktemp -d)"
seen_file="$tmp_dir/seen.txt"
touch "$seen_file"
trap 'rm -rf "$tmp_dir"' EXIT

process_one() {
  local f="$1"
  [[ -f "$f" ]] || return

  local h
  h="$(hash_file "$f")"

  if grep -Fqx "$h" "$seen_file"; then
    echo "Duplicate (same SHA-256), skipping: $f"
    return
  fi

  echo "$h" >> "$seen_file"

  local filename base dest_dir
  filename="$(basename "$f")"
  base="${filename%.*}"
  base="$(sanitize_folder_name "$base")"
  dest_dir="$(unique_dest_dir "$base")"

  if [[ "$DRYRUN" == "1" ]]; then
    echo "Would move:"
    echo "  $f"
    echo "  -> $dest_dir/$filename"
    return
  fi

  mkdir -p "$dest_dir"
  mv -n -- "$f" "$dest_dir/$filename"
  echo "Moved: $f -> $dest_dir/$filename"
}

export -f process_one hash_file sanitize_folder_name unique_dest_dir
export OUT DRYRUN seen_file tmp_dir

# Find mp3s recursively in both dirs, handle spaces safely
while IFS= read -r -d '' f; do
  process_one "$f"
done < <(find "$DIR1" "$DIR2" -type f \( -iname "*.mp3" \) -print0)

echo "Done. Output: $OUT"
echo "Tip: run with DRYRUN=1 first if you want to preview."
