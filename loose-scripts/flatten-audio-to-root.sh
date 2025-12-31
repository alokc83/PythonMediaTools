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

moved_report="${REPORT_DIR}/moved_audio_files.txt"
skipped_report="${REPORT_DIR}/skipped_audio_files.txt"
: > "$moved_report"
: > "$skipped_report"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

files_list="${tmp_dir}/audio_files.list"
: > "$files_list"

root_abs="$(cd "$ROOT" && pwd)"

term_cols() {
  local c="${COLUMNS:-}"
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

  local max_item=$(( cols - ${#prefix} - 1 ))
  if [[ "$max_item" -lt 10 ]]; then
    max_item=10
  fi

  local short="$item"
  if [[ ${#short} -gt "$max_item" ]]; then
    short="...${short: -$((max_item - 3))}"
  fi

  local line="${prefix}${short}"
  printf '\r\033[2K%-*s' "$cols" "$line" >&2
}

finish_phase() {
  local msg="$1"
  local cols
  cols="$(term_cols)"
  printf '\r\033[2K%-*s\n' "$cols" "$msg" >&2
}

build_find_args() {
  FIND_ARGS=()
  local first=1
  local IFS=','
  local exts_arr=()
  read -r -a exts_arr <<< "$AUDIO_EXTS"

  local ext=""
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

unique_dest_path() {
  local dest_dir="$1"
  local filename="$2"

  local base ext ext_part candidate n

  if [[ "$filename" == *.* ]]; then
    base="${filename%.*}"
    ext="${filename##*.}"
    ext_part=".${ext}"
  else
    base="$filename"
    ext_part=""
  fi

  candidate="${dest_dir}/${filename}"
  if [[ ! -e "$candidate" ]]; then
    echo "$candidate"
    return
  fi

  n=1
  while :; do
    candidate="${dest_dir}/${base}-dup-${n}${ext_part}"
    if [[ ! -e "$candidate" ]]; then
      echo "$candidate"
      return
    fi
    n=$((n + 1))
  done
}

FIND_ARGS=()
build_find_args

echo "Root: $root_abs" >&2
echo "Audio extensions: $AUDIO_EXTS" >&2
echo "Report dir: $REPORT_DIR" >&2
if [[ "$DRYRUN" == "1" ]]; then
  echo "Mode: dry run (no moves)" >&2
else
  echo "Mode: move" >&2
fi
echo "" >&2

# Phase 1: collect file list first (stable list while we move)
progress_line "Scan" 0 1 "finding audio files"
find "$root_abs" -type f \( "${FIND_ARGS[@]}" \) -print0 > "$files_list"

total_files="$(tr -cd '\0' < "$files_list" | wc -c | tr -d ' ')"
if [[ -z "$total_files" ]]; then total_files=0; fi
finish_phase "Scan done. Audio files found: $total_files"

# Phase 2: move into root, rename duplicates by filename
moved_count=0
renamed_count=0
skipped_count=0
i=0

if [[ "$total_files" -gt 0 ]]; then
  while IFS= read -r -d '' src; do
    i=$((i + 1))
    progress_line "Move" "$i" "$total_files" "$src"

    # If already directly under root, skip
    parent_dir="$(cd "$(dirname "$src")" && pwd)"
    if [[ "$parent_dir" == "$root_abs" ]]; then
      printf '%s\n' "Already in root, skip: $src" >> "$skipped_report"
      skipped_count=$((skipped_count + 1))
      continue
    fi

    filename="$(basename "$src")"
    dest="$(unique_dest_path "$root_abs" "$filename")"

    if [[ "$dest" != "${root_abs}/${filename}" ]]; then
      renamed_count=$((renamed_count + 1))
    fi

    if [[ "$DRYRUN" == "1" ]]; then
      printf '%s\n' "Would move: $src -> $dest" >> "$moved_report"
      moved_count=$((moved_count + 1))
      continue
    fi

    mkdir -p "$root_abs"
    mv -- "$src" "$dest"
    printf '%s\n' "Moved: $src -> $dest" >> "$moved_report"
    moved_count=$((moved_count + 1))
  done < "$files_list"

  finish_phase "Move done. Moved: $moved_count  Renamed as dup: $renamed_count  Skipped: $skipped_count"
else
  finish_phase "Move skipped. No audio files found."
fi

echo "" >&2
echo "Summary" >&2
echo "Audio files found: $total_files" >&2
echo "Moved to root: $moved_count" >&2
echo "Renamed with dup suffix: $renamed_count" >&2
echo "Skipped already in root: $skipped_count" >&2
echo "" >&2
echo "Reports" >&2
echo "Moved report: $moved_report" >&2
echo "Skipped report: $skipped_report" >&2
