#!/bin/bash
set -euo pipefail

# Flatten audio files into ROOT, renaming everything to Title.ext
# Duplicates get -dup-1, -dup-2, ...
#
# Enhancements added:
# 1) Clean Title to only alphanumeric + spaces. Use that as filename.
# 2) Write the cleaned Title back into the file metadata (Title tag) before naming/moving.
# 3) After all moves, delete any directories under ROOT (excluding ROOT itself) that contain no audio files.
#    This also removes empty or non audio folders that may remain.

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
root_rename_report="${REPORT_DIR}/root_renamed_files.txt"
deleted_dirs_report="${REPORT_DIR}/deleted_no_audio_dirs.txt"
title_fix_report="${REPORT_DIR}/title_sanitized_and_written.txt"

: > "$moved_report"
: > "$skipped_report"
: > "$dups_report"
: > "$root_rename_report"
: > "$deleted_dirs_report"
: > "$title_fix_report"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

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

# Clean title to only alphanumeric + spaces, collapse spaces, trim.
clean_title_alnum_space() {
  local s="$1"
  s="$(printf '%s' "$s" | tr '\r\n' '  ')"
  s="$(printf '%s' "$s" | tr '[:upper:]' '[:lower:]')"
  s="$(printf '%s' "$s" | sed 's/[^a-z0-9 ]/ /g; s/[[:space:]]\{1,\}/ /g; s/^ *//; s/ *$//')"
  [[ -z "$s" ]] && s="untitled"
  echo "$s"
}

# For the title index, normalize similarly (already lowercase alnum space)
normalize_title() {
  clean_title_alnum_space "$1"
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

# Write the cleaned title back into the file metadata.
# Uses ffmpeg and makes a temp file with the same extension so muxer is happy.
write_title_tag() {
  local f="$1"
  local new_title="$2"

  if ! command -v ffmpeg >/dev/null 2>&1; then
    return 0
  fi

  local dir base ext tmp
  dir="$(dirname "$f")"
  base="$(basename "$f")"

  ext=""
  if [[ "$base" == *.* ]]; then
    ext="${base##*.}"
  fi
  [[ -z "$ext" ]] && ext="mp3"

  tmp="${dir}/.${base}.tmp.$$.$ext"

  if [[ "$DRYRUN" == "1" ]]; then
    printf '%s\n' "Would write title tag: $f => $new_title" >> "$title_fix_report"
    return 0
  fi

  # Stream copy, only update title
  ffmpeg -hide_banner -loglevel error -y \
    -i "$f" \
    -map 0 \
    -c copy \
    -metadata title="$new_title" \
    "$tmp"

  mv -- "$tmp" "$f"
  printf '%s\n' "Wrote title tag: $f => $new_title" >> "$title_fix_report"
}

# Delete directory if it contains NO audio files anywhere inside it.
cleanup_no_audio_upwards() {
  local start_dir="$1"
  local d="$start_dir"

  while :; do
    [[ "$d" == "$root_abs" ]] && break
    [[ -d "$d" ]] || break

    if find "$d" -type f \( "${FIND_ARGS[@]}" \) -print -quit 2>/dev/null | grep -q .; then
      break
    fi

    if [[ "$DRYRUN" == "1" ]]; then
      printf '%s\n' "Would delete (no audio): $d" >> "$deleted_dirs_report"
      break
    else
      rm -rf -- "$d"
      printf '%s\n' "Deleted (no audio): $d" >> "$deleted_dirs_report"
    fi

    d="$(dirname "$d")"
  done
}

# Final sweep: delete any subdirectory under ROOT that has no audio anywhere inside.
# Deepest first to avoid issues.
final_sweep_delete_no_audio_dirs_under_root() {
  local list="${tmp_dir}/dirs_under_root.txt"
  find "$root_abs" -type d -print0 > "${list}.bin"

  # Convert to newline list, exclude root itself
  : > "$list"
  while IFS= read -r -d '' d; do
    [[ "$d" == "$root_abs" ]] && continue
    printf '%s\n' "$d" >> "$list"
  done < "${list}.bin"

  # Deepest first
  local sorted="${tmp_dir}/dirs_under_root_sorted.txt"
  awk '{ depth=gsub(/\//,"/"); print depth "\t" $0 }' "$list" | LC_ALL=C sort -nr | cut -f2- > "$sorted"

  local total
  total="$(wc -l < "$sorted" | tr -d ' ')"
  [[ -z "$total" ]] && total=0

  local i=0
  while IFS= read -r d; do
    i=$((i + 1))
    progress_line "RootCleanup" "$i" "$total" "$d"

    [[ -d "$d" ]] || continue

    # If no audio in this directory subtree, delete it
    if ! find "$d" -type f \( "${FIND_ARGS[@]}" \) -print -quit 2>/dev/null | grep -q .; then
      if [[ "$DRYRUN" == "1" ]]; then
        printf '%s\n' "Would delete (no audio): $d" >> "$deleted_dirs_report"
      else
        rm -rf -- "$d"
        printf '%s\n' "Deleted (no audio): $d" >> "$deleted_dirs_report"
      fi
    fi
  done < "$sorted"

  finish_phase "Root cleanup done."
}

build_find_args

echo "Root: $root_abs" >&2
echo "Audio extensions: $AUDIO_EXTS" >&2
echo "Report dir: $REPORT_DIR" >&2
if [[ "$DRYRUN" == "1" ]]; then
  echo "Mode: dry run (no moves/renames/deletes)" >&2
else
  echo "Mode: move + rename + title sanitize + delete dirs without audio" >&2
fi
echo "" >&2

if ! command -v ffprobe >/dev/null 2>&1; then
  echo "Warning: ffprobe not found. Title metadata reads will be limited." >&2
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Warning: ffmpeg not found. Title metadata will not be written back." >&2
fi

# ---- Phase A: Rename files already in ROOT to CleanTitle.ext first ----
root_list="${tmp_dir}/root_audio.bin"
find "$root_abs" -maxdepth 1 -type f \( "${FIND_ARGS[@]}" \) -print0 > "$root_list"
root_total="$(tr -cd '\0' < "$root_list" | wc -c | tr -d ' ')"
[[ -z "$root_total" ]] && root_total=0

title_index="${tmp_dir}/root_titles_norm.txt"
: > "$title_index"

root_renamed_count=0
root_dups_found=0
root_title_fixed=0
i=0

if [[ "$root_total" -gt 0 ]]; then
  while IFS= read -r -d '' f; do
    i=$((i + 1))
    progress_line "RootRename" "$i" "$root_total" "$f"

    filename="$(basename "$f")"
    ext_part=""
    if [[ "$filename" == *.* ]]; then
      ext_part=".${filename##*.}"
    fi

    raw_title="$(get_title "$f")"
    [[ -z "$raw_title" ]] && raw_title="${filename%.*}"

    clean_title="$(clean_title_alnum_space "$raw_title")"

    # Write cleaned title back into metadata if it changed
    if [[ "$clean_title" != "$(clean_title_alnum_space "$raw_title")" ]]; then
      : # no op, kept for clarity
    fi

    # Always ensure metadata title equals clean title (safe and consistent)
    write_title_tag "$f" "$clean_title"
    root_title_fixed=$((root_title_fixed + 1))

    norm_title="$(normalize_title "$clean_title")"
    desired="${root_abs}/${clean_title}${ext_part}"

    if [[ "$f" != "$desired" ]]; then
      dest="$desired"
      if [[ -e "$desired" ]]; then
        dest="$(dup_dest_path "$root_abs" "$clean_title" "$ext_part")"
        root_dups_found=$((root_dups_found + 1))
        printf '%s\n' "Root dup: $f -> $dest" >> "$dups_report"
      fi

      if [[ "$DRYRUN" == "1" ]]; then
        printf '%s\n' "Would rename in root: $f -> $dest" >> "$root_rename_report"
      else
        mv -- "$f" "$dest"
        printf '%s\n' "Renamed in root: $f -> $dest" >> "$root_rename_report"
      fi

      root_renamed_count=$((root_renamed_count + 1))
      f="$dest"
    fi

    [[ -n "$norm_title" ]] && printf '%s\n' "$norm_title" >> "$title_index"
  done < "$root_list"

  finish_phase "Root rename done. Renamed: $root_renamed_count  Root dups: $root_dups_found"
else
  finish_phase "Root rename skipped. No audio files directly under root."
fi

# Rebuild root title index from current root state
: > "$title_index"
root_list2="${tmp_dir}/root_audio2.bin"
find "$root_abs" -maxdepth 1 -type f \( "${FIND_ARGS[@]}" \) -print0 > "$root_list2"
while IFS= read -r -d '' f; do
  t="$(get_title "$f")"
  [[ -z "$t" ]] && t="$(basename "${f%.*}")"
  t="$(clean_title_alnum_space "$t")"
  nt="$(normalize_title "$t")"
  [[ -n "$nt" ]] && printf '%s\n' "$nt" >> "$title_index"
done < "$root_list2"

# ---- Phase B: Traverse tree, move into ROOT, always name CleanTitle.ext ----
files_list="${tmp_dir}/audio_files.bin"
progress_line "Scan" 0 1 "finding audio files"
find "$root_abs" -type f \( "${FIND_ARGS[@]}" \) -print0 > "$files_list"
total_files="$(tr -cd '\0' < "$files_list" | wc -c | tr -d ' ')"
[[ -z "$total_files" ]] && total_files=0
finish_phase "Scan done. Audio files found: $total_files"

moved_count=0
skipped_count=0
dups_found=0
i=0

if [[ "$total_files" -gt 0 ]]; then
  while IFS= read -r -d '' src; do
    i=$((i + 1))
    progress_line "Move" "$i" "$total_files" "$src"

    src_dir="$(cd "$(dirname "$src")" && pwd)"
    if [[ "$src_dir" == "$root_abs" ]]; then
      printf '%s\n' "Already in root, skip: $src" >> "$skipped_report"
      skipped_count=$((skipped_count + 1))
      continue
    fi

    filename="$(basename "$src")"
    ext_part=""
    if [[ "$filename" == *.* ]]; then
      ext_part=".${filename##*.}"
    fi

    raw_title="$(get_title "$src")"
    [[ -z "$raw_title" ]] && raw_title="${filename%.*}"

    clean_title="$(clean_title_alnum_space "$raw_title")"

    # Write cleaned title into metadata before moving/renaming
    write_title_tag "$src" "$clean_title"

    norm_title="$(normalize_title "$clean_title")"
    candidate="${root_abs}/${clean_title}${ext_part}"

    is_dup=0
    if [[ -e "$candidate" ]]; then
      is_dup=1
    elif [[ -n "$norm_title" ]] && grep -Fqx "$norm_title" "$title_index" 2>/dev/null; then
      is_dup=1
    fi

    if [[ "$is_dup" -eq 1 ]]; then
      dest="$(dup_dest_path "$root_abs" "$clean_title" "$ext_part")"
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
    [[ -n "$norm_title" ]] && printf '%s\n' "$norm_title" >> "$title_index"

    # Delete source directory tree if it has no audio (and then parent, etc.)
    cleanup_no_audio_upwards "$src_dir"
  done < "$files_list"

  finish_phase "Move done. Moved: $moved_count  Dups found: $dups_found  Skipped: $skipped_count"
else
  finish_phase "Move skipped. No audio files found."
fi

# ---- Phase C: Ensure no deletable folders remain under ROOT ----
final_sweep_delete_no_audio_dirs_under_root

deleted_dirs_count="$(grep -c '^Deleted (no audio):' "$deleted_dirs_report" 2>/dev/null || true)"

echo "" >&2
echo "Summary" >&2
echo "Audio files found: $total_files" >&2
echo "Renamed in root: $root_renamed_count" >&2
echo "Root duplicates found: $root_dups_found" >&2
echo "Moved to root: $moved_count" >&2
echo "Duplicates found while moving: $dups_found" >&2
echo "Total duplicates found: $((root_dups_found + dups_found))" >&2
echo "Dirs deleted (no audio): $deleted_dirs_count" >&2
echo "Skipped already in root: $skipped_count" >&2
echo "" >&2
echo "Reports" >&2
echo "Root rename report: $root_rename_report" >&2
echo "Title fix report: $title_fix_report" >&2
echo "Moved report: $moved_report" >&2
echo "Duplicates report: $dups_report" >&2
echo "Deleted dirs report: $deleted_dirs_report" >&2
echo "Skipped report: $skipped_report" >&2
