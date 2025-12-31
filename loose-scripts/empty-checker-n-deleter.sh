#!/usr/bin/env bash
set -euo pipefail

# Usage
#   DRYRUN=1 ./delete_dirs_without_audio.sh /path/to/root
#   ./delete_dirs_without_audio.sh /path/to/root
#
# Optional
#   AUDIO_EXTS="mp3,m4a,m4b,flac,wav,aac,ogg" ./delete_dirs_without_audio.sh /path/to/root
#   REPORT_DIR="/path/to/reports" ./delete_dirs_without_audio.sh /path/to/root

ROOT="${1:-}"
if [[ -z "${ROOT}" || ! -d "${ROOT}" ]]; then
  echo "Provide a root directory path." >&2
  exit 1
fi

DRYRUN="${DRYRUN:-0}"
AUDIO_EXTS="${AUDIO_EXTS:-mp3,m4a,m4b}"
REPORT_DIR="${REPORT_DIR:-$PWD}"

mkdir -p "$REPORT_DIR"

audio_files_report="${REPORT_DIR}/audio_files_found.txt"
dirs_to_delete_report="${REPORT_DIR}/dirs_to_delete.txt"
dirs_deleted_report="${REPORT_DIR}/dirs_deleted.txt"

: > "$audio_files_report"
: > "$dirs_to_delete_report"
: > "$dirs_deleted_report"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

audio_files_list="${tmp_dir}/audio_files_list.txt"
dirs_with_audio="${tmp_dir}/dirs_with_audio.txt"
dirs_with_audio_sorted="${tmp_dir}/dirs_with_audio_sorted.txt"
all_dirs_list="${tmp_dir}/all_dirs_list.txt"
all_dirs_sorted="${tmp_dir}/all_dirs_sorted.txt"
dirs_to_delete_sorted="${tmp_dir}/dirs_to_delete_sorted.txt"

: > "$audio_files_list"
: > "$dirs_with_audio"
: > "$all_dirs_list"

root_abs="$(cd "$ROOT" && pwd)"

progress_bar() {
  # progress_bar "Phase" current total "item"
  local phase="$1"
  local current="$2"
  local total="$3"
  local item="$4"

  local short="$item"
  if [[ ${#short} -gt 80 ]]; then
    short="…${short: -79}"
  fi

  local width=28
  local percent=0
  if [[ "$total" -gt 0 ]]; then
    percent=$(( current * 100 / total ))
  fi
  local filled=$(( percent * width / 100 ))
  local empty=$(( width - filled ))
  local bar
  bar="$(printf '%*s' "$filled" '' | tr ' ' '#')$(printf '%*s' "$empty" '' | tr ' ' '.')"

  printf '\r[%s] [%s] %3d%%  %d/%d  %s' "$phase" "$bar" "$percent" "$current" "$total" "$short" >&2
}

finish_progress() {
  printf '\n' >&2
}

build_find_audio_args() {
  # prints: -iname "*.mp3" -o -iname "*.m4a" ...
  local IFS=',' read -r -a exts_arr <<< "$AUDIO_EXTS"
  local first=1
  for ext in "${exts_arr[@]}"; do
    ext="$(echo "$ext" | tr -d '[:space:]')"
    [[ -z "$ext" ]] && continue
    if [[ "$first" -eq 1 ]]; then
      printf '%s' "-iname *.${ext}"
      first=0
    else
      printf '%s' " -o -iname *.${ext}"
    fi
  done
}

echo "Root: $root_abs" >&2
echo "Audio extensions: $AUDIO_EXTS" >&2
echo "Report dir: $REPORT_DIR" >&2
if [[ "$DRYRUN" == "1" ]]; then
  echo "Mode: dryrun (no deletes)" >&2
else
  echo "Mode: delete" >&2
fi
echo "" >&2

# Step 1: list audio files
echo "Scanning for audio files…" >&2

find_expr="$(build_find_audio_args)"

# shellcheck disable=SC2086
while IFS= read -r -d '' f; do
  printf '%s\n' "$f" >> "$audio_files_list"
  printf '%s\n' "$f" >> "$audio_files_report"
done < <(find "$root_abs" -type f \( $find_expr \) -print0)

audio_file_count="$(wc -l < "$audio_files_list" | tr -d ' ')"
echo "Audio files found: $audio_file_count" >&2

# Step 2: build directories that have audio (including all ancestors up to root)
echo "Building directory map…" >&2
processed=0
total="$audio_file_count"

if [[ "$total" -gt 0 ]]; then
  while IFS= read -r f; do
    processed=$((processed + 1))
    progress_bar "Dirs" "$processed" "$total" "$f"

    d="$(dirname "$f")"
    while :; do
      printf '%s\n' "$d" >> "$dirs_with_audio"
      if [[ "$d" == "$root_abs" ]]; then
        break
      fi
      d="$(dirname "$d")"
    done
  done < "$audio_files_list"
  finish_progress
else
  echo "No audio files found. Everything under root is eligible for delete except root." >&2
fi

LC_ALL=C sort -u "$dirs_with_audio" > "$dirs_with_audio_sorted"

# Step 3: list all directories
echo "Listing all directories…" >&2
while IFS= read -r -d '' d; do
  printf '%s\n' "$d" >> "$all_dirs_list"
done < <(find "$root_abs" -type d -print0)

LC_ALL=C sort -u "$all_dirs_list" | grep -Fvx "$root_abs" > "$all_dirs_sorted"

all_dir_count="$(wc -l < "$all_dirs_sorted" | tr -d ' ')"

# Step 4: directories to delete = all dirs minus dirs with audio
echo "Computing directories to delete…" >&2
# comm requires both sorted
LC_ALL=C comm -23 "$all_dirs_sorted" "$dirs_with_audio_sorted" > "$dirs_to_delete_report"

to_delete_count="$(wc -l < "$dirs_to_delete_report" | tr -d ' ')"

# Sort deepest first for safe delete
awk '
  {
    depth = gsub(/\//,"/")
    print depth "\t" $0
  }
' "$dirs_to_delete_report" | LC_ALL=C sort -nr | cut -f2- > "$dirs_to_delete_sorted"

# Step 5: delete with progress
echo "" >&2
echo "Directories to delete: $to_delete_count (directories without audio inside)" >&2

deleted_count=0
i=0
while IFS= read -r d; do
  i=$((i + 1))
  progress_bar "Delete" "$i" "$to_delete_count" "$d"

  if [[ "$DRYRUN" == "1" ]]; then
    continue
  fi

  if [[ -d "$d" ]]; then
    rm -rf -- "$d"
    deleted_count=$((deleted_count + 1))
    printf '%s\n' "$d" >> "$dirs_deleted_report"
  fi
done < "$dirs_to_delete_sorted"
finish_progress

echo "" >&2
echo "Summary" >&2
echo "Audio files found: $audio_file_count" >&2
echo "Directories scanned: $all_dir_count" >&2
echo "Directories without audio found: $to_delete_count" >&2
if [[ "$DRYRUN" == "1" ]]; then
  echo "Directories deleted: 0 (dryrun)" >&2
else
  echo "Directories deleted: $deleted_count" >&2
fi
echo "" >&2
echo "Reports" >&2
echo "Audio files list: $audio_files_report" >&2
echo "Directories to delete list: $dirs_to_delete_report" >&2
echo "Directories deleted list: $dirs_deleted_report" >&2
