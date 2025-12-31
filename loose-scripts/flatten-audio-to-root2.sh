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
dups_report="${REPORT_DIR}/duplicates_found.txt"

: > "$moved_report"
: > "$skipped_report"
: > "$dups_report"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

files_list="${tmp_dir}/audio_files.bin"
title_index="${tmp_dir}/root_titles_norm.txt"
: > "$title_index"

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

get_title() {
  local f="$1"
  if command -v ffprobe >/dev/null 2>&1; then
    ffprobe -v error -show_entries format_tags=title -of default=nw=1:nk=1 "$f" 2>/dev/null | head -n 1
  else
    echo ""
  fi
}

sanitize_base() {
  local s="$1"
  s="$(printf '%s' "$s" | tr '\r\n' '  ')"
  s="$(printf '%s' "$s" | sed 's/[\/:]/ /g; s/[[:cntrl:]]//g; s/[[:space:]]\{1,\}/ /g; s/^ *//; s/ *$//')"
  [[ -z "$s" ]] && s="untitled"
  echo "$s"
}

normalize_title() {
  local s="$1"
  s="$(printf '%s' "$s" | tr '[:upper:]' '[:lower:]')"
  s="$(printf '%s' "$s" | sed 's/[_[:space:]]\{1,\}/ /g; s/[^a-z0-9 ]//g; s/^ *//; s/ *$//')"
  echo "$s"
}

dup_dest_path() {
  local dest_dir="$1"
  local base="$2"
  local ext_part="$3"

  local n=1
  local candidate=""
  while :; do
    candidate="${dest_dir}/${base}-dup-${n}${ext_part}"
    if [[ ! -e "$candidate" ]]; then
      echo "$candidate"
      return
    fi
    n=$((n + 1))
  done
}

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

# Build initial title index from files already in root (so Title duplicates are detected)
tmp_root_list="${tmp_dir}/root_audio.bin"
find "$root_abs" -maxdepth 1 -type f \( "${FIND_ARGS[@]}" \) -print0 > "$tmp_root_list"
while IFS= read -r -d '' f; do
  t="$(get_title "$f")"
  [[ -z "$t" ]] && t="$(basename "${f%.*}")"
  t="$(sanitize_base "$t")"
  nt="$(normalize_title "$t")"
  [[ -n "$nt" ]] && printf '%s\n' "$nt" >> "$title_index"
done < "$tmp_root_list"

# Phase 1: collect audio list from whole tree
progress_line "Scan" 0 1 "finding audio files"
find "$root_abs" -type f \( "${FIND_ARGS[@]}" \) -print0 > "$files_list"
total_files="$(tr -cd '\0' < "$files_list" | wc -c | tr -d ' ')"
[[ -z "$total_files" ]] && total_files=0
finish_phase "Scan done. Audio files found: $total_files"

# Phase 2: move to root, rename to Title.ext always
moved_count=0
skipped_count=0
dups_found=0
i=0

if [[ "$total_files" -gt 0 ]]; then
  while IFS= read -r -d '' src; do
    i=$((i + 1))
    progress_line "Move" "$i" "$total_files" "$src"

    parent_dir="$(cd "$(dirname "$src")" && pwd)"
    if [[ "$parent_dir" == "$root_abs" ]]; then
      printf '%s\n' "Already in root, skip: $src" >> "$skipped_report"
      skipped_count=$((skipped_count + 1))
      continue
    fi

    filename="$(basename "$src")"
    ext_part=""
    if [[ "$filename" == *.* ]]; then
      ext_part=".${filename##*.}"
    fi

    title="$(get_title "$src")"
    [[ -z "$title" ]] && title="${filename%.*}"
    title="$(sanitize_base "$title")"
    norm_title="$(normalize_title "$title")"
    [[ -z "$norm_title" ]] && norm_title="$(normalize_title "${filename%.*}")"

    # Candidate destination is always Title.ext
    candidate="${root_abs}/${title}${ext_part}"

    # Duplicate if:
    # 1) Title.ext already exists in root
    # 2) Another file in root already has the same Title tag (even if named differently)
    is_dup=0
    if [[ -e "$candidate" ]]; then
      is_dup=1
    elif [[ -n "$norm_title" ]] && grep -Fqx "$norm_title" "$title_index" 2>/dev/null; then
      is_dup=1
    fi

    if [[ "$is_dup" -eq 1 ]]; then
      dest="$(dup_dest_path "$root_abs" "$title" "$ext_part")"
      dups_found=$((dups_found + 1))
      printf '%s\n' "Dup: $src -> $dest" >> "$dups_report"
    else
      dest="$candidate"
    fi

    if [[ "$DRYRUN" == "1" ]]; then
      printf '%s\n' "Would move: $src -> $dest" >> "$moved_report"
    else
      mv -- "$src" "$dest"
      printf '%s\n' "Moved: $src -> $dest" >> "$moved_report"
    fi

    moved_count=$((moved_count + 1))

    # Update title index so future files detect duplicates by title
    if [[ -n "$norm_title" ]]; then
      printf '%s\n' "$norm_title" >> "$title_index"
    fi

  done < "$files_list"

  finish_phase "Move done. Moved: $moved_count  Dups found: $dups_found  Skipped: $skipped_count"
else
  finish_phase "Move skipped. No audio files found."
fi

echo "" >&2
echo "Summary" >&2
echo "Audio files found: $total_files" >&2
echo "Moved to root: $moved_count" >&2
echo "Duplicates found: $dups_found" >&2
echo "Skipped already in root: $skipped_count" >&2
echo "" >&2
echo "Reports" >&2
echo "Moved report: $moved_report" >&2
echo "Duplicates report: $dups_report" >&2
echo "Skipped report: $skipped_report" >&2
