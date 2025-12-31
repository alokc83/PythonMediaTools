#!/bin/bash
set -euo pipefail

ROOT="${1:-}"
if [[ -z "$ROOT" || ! -d "$ROOT" ]]; then
  echo "Usage: DRYRUN=1 $0 /path/to/root" >&2
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

# ----- progress (macOS Terminal friendly) -----
term_cols() {
  local c=""
  c="${COLUMNS:-}"
  if [[ -z "$c" ]]; then
    c="$(tput cols 2>/dev/null || true)"
  fi
  [[ -z "$c" ]] && c=120
  echo "$c"
}

progress_line() {
  local phase="$1"
  local current="$2"
  local total="$3"
  local item="$4"

  local cols
  cols="$(term_cols)"

  local width=28
  local percent=0
  if [[ "$total" -gt 0 ]]; then
    percent=$(( current * 100 / total ))
  fi

  local filled=$(( percent * width / 100 ))
  local empty=$(( width - filled ))
  local bar
  bar="$(printf '%*s' "$filled" '' | tr ' ' '#')$(printf '%*s' "$empty" '' | tr ' ' '.')"

  local prefix
  prefix="[$phase] [$bar] $(printf '%3d' "$percent")% $(printf '%d/%d' "$current" "$total") "

  # Leave room for prefix, truncate item so line never wraps
  local max_item=$(( cols - ${#prefix} - 1 ))
  if [[ "$max_item" -lt 10 ]]; then
    max_item=10
  fi

  local short="$item"
  if [[ ${#short} -gt "$max_item" ]]; then
    short="...${short: -$((max_item - 3))}"
  fi

  local line="${prefix}${short}"

  # Clear + redraw + pad to full width so it stays one line
  printf '\r\033[2K%-*s' "$cols" "$line" >&2
}

finish_phase() {
  local msg="$1"
  local cols
  cols="$(term_cols)"
  printf '\r\033[2K%-*s\n' "$cols" "$msg" >&2
}

# ----- build find args safely -----
FIND_ARGS=()
{
  IFS=',' read -r -a exts_arr <<< "$AUDIO_EXTS"
  first=1
  for ext in "${exts_arr[@]}"; do
    ext="$(echo "$ext" | tr -d '[:space:]')"
    [[ -z "$ext" ]] && continue
    if [[ "$first" -eq 1 ]]; then
      FIND_ARGS+=(-iname "*.${ext}")
      first=0
    else
      FIND_ARGS+=(-o -iname "*.${ext}")
    fi
  done
  if [[ "$first" -eq 1 ]]; then
    echo "No valid AUDIO_EXTS provided." >&2
    exit 1
  fi
}

echo "Root: $root_abs" >&2
echo "Audio extensions: $AUDIO_EXTS" >&2
echo "Report dir: $REPORT_DIR" >&2
if [[ "$DRYRUN" == "1" ]]; then
  echo "Mode: dry run (no deletes)" >&2
else
  echo "Mode: delete" >&2
fi
echo "" >&2

# Phase 1: scan audio files
progress_line "Scan" 0 1 "finding audio files"
while IFS= read -r -d '' f; do
  printf '%s\n' "$f" >> "$audio_files_list"
  printf '%s\n' "$f" >> "$audio_files_report"
done < <(find "$root_abs" -type f \( "${FIND_ARGS[@]}" \) -print0)

audio_file_count="$(wc -l < "$audio_files_list" | tr -d ' ')"
finish_phase "Scan done. Audio files found: $audio_file_count"

# Phase 2: map dirs with audio + ancestors
processed=0
total="$audio_file_count"

if [[ "$total" -gt 0 ]]; then
  while IFS= read -r f; do
    processed=$((processed + 1))
    progress_line "Map" "$processed" "$total" "$f"

    d="$(dirname "$f")"
    while :; do
      printf '%s\n' "$d" >> "$dirs_with_audio"
      [[ "$d" == "$root_abs" ]] && break
      d="$(dirname "$d")"
    done
  done < "$audio_files_list"
  finish_phase "Map done. Directory ancestry captured."
else
  finish_phase "Map skipped. No audio files found under root."
fi

LC_ALL=C sort -u "$dirs_with_audio" > "$dirs_with_audio_sorted"

# Phase 3: list all dirs
progress_line "List" 0 1 "listing directories"
while IFS= read -r -d '' d; do
  printf '%s\n' "$d" >> "$all_dirs_list"
done < <(find "$root_abs" -type d -print0)

LC_ALL=C sort -u "$all_dirs_list" | grep -Fvx "$root_abs" > "$all_dirs_sorted"
all_dir_count="$(wc -l < "$all_dirs_sorted" | tr -d ' ')"
finish_phase "List done. Directories scanned (excluding root): $all_dir_count"

# Phase 4: plan delete list
progress_line "Plan" 0 1 "computing delete list"
LC_ALL=C comm -23 "$all_dirs_sorted" "$dirs_with_audio_sorted" > "$dirs_to_delete_report"
to_delete_count="$(wc -l < "$dirs_to_delete_report" | tr -d ' ')"

awk '{ depth=gsub(/\//,"/"); print depth "\t" $0 }' "$dirs_to_delete_report" | LC_ALL=C sort -nr | cut -f2- > "$dirs_to_delete_sorted"
finish_phase "Plan done. Directories without audio: $to_delete_count"

# Phase 5: delete
deleted_count=0
i=0

if [[ "$to_delete_count" -gt 0 ]]; then
  while IFS= read -r d; do
    i=$((i + 1))
    progress_line "Del" "$i" "$to_delete_count" "$d"

    if [[ "$DRYRUN" == "1" ]]; then
      continue
    fi

    if [[ -d "$d" ]]; then
      rm -rf -- "$d"
      deleted_count=$((deleted_count + 1))
      printf '%s\n' "$d" >> "$dirs_deleted_report"
    fi
  done < "$dirs_to_delete_sorted"

  if [[ "$DRYRUN" == "1" ]]; then
    finish_phase "Delete done. Would delete: $to_delete_count"
  else
    finish_phase "Delete done. Deleted: $deleted_count"
  fi
else
  finish_phase "Delete skipped. Nothing to delete."
fi

echo "" >&2
echo "Summary" >&2
echo "Audio files found: $audio_file_count" >&2
echo "Directories scanned (excluding root): $all_dir_count" >&2
echo "Directories without audio found: $to_delete_count" >&2
if [[ "$DRYRUN" == "1" ]]; then
  echo "Directories deleted: 0 (dry run)" >&2
else
  echo "Directories deleted: $deleted_count" >&2
fi
echo "" >&2
echo "Reports" >&2
echo "Audio files list: $audio_files_report" >&2
echo "Dirs to delete list: $dirs_to_delete_report" >&2
echo "Dirs deleted list: $dirs_deleted_report" >&2
