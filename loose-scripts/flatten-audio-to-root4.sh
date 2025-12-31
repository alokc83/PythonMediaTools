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
root_rename_report="${REPORT_DIR}/root_renamed_files.txt"
deleted_dirs_report="${REPORT_DIR}/deleted_source_dirs.txt"

: > "$moved_report"
: > "$skipped_report"
: > "$dups_report"
: > "$root_rename_report"
: > "$deleted_dirs_report"

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

# Delete a directory if it contains NO audio files anywhere inside.
# Then move to its parent and repeat until root.
cleanup_no_audio_upwards() {
  local start_dir="$1"
  local d="$start_dir"

  while :; do
    [[ "$d" == "$root_abs" ]] && break
    [[ -d "$d" ]] || break

    # If directory (recursively) contains any audio file, stop
    if find "$d" -type f \( "${FIND_ARGS[@]}" \) -print -quit 2>/dev/null | grep -q .; then
      break
    fi

    if [[ "$DRYRUN" == "1" ]]; then
      printf '%s\n' "Would delete (no audio): $d" >> "$deleted_dirs_report"
      # In dryrun, do not actually remove, and stop to avoid pretending parent has changed
      break
    else
      rm -rf -- "$d"
      printf '%s\n' "Deleted (no audio): $d" >> "$deleted_dirs_report"
    fi

    d="$(dirname "$d")"
  done
}

build_find_args

echo "Root: $root_abs" >&2
echo "Audio extensions: $AUDIO_EXTS" >&2
echo "Report dir: $REPORT_DIR" >&2
if [[ "$DRYRUN" == "1" ]]; then
  echo "Mode: dry run (no moves/renames/deletes)" >&2
else
  echo "Mode: move + rename + delete dirs without audio" >&2
fi
echo "" >&2

# ---- Phase A: Rename files already in ROOT to Title.ext first ----
root_list="${tmp_dir}/root_audio.bin"
find "$root_abs" -maxdepth 1 -type f \( "${FIND_ARGS[@]}" \) -print0 > "$root_list"
root_total="$(tr -cd '\0' < "$root_list" | wc -c | tr -d ' ')"
[[ -z "$root_total" ]] && root_total=0

title_index="${tmp_dir}/root_titles_norm.txt"
: > "$title_index"

root_renamed_count=0
root_dups_found=0
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

    title="$(get_title "$f")"
    [[ -z "$title" ]] && title="${filename%.*}"
    title="$(sanitize_base "$title")"
    norm_title="$(normalize_title "$title")"

    desired="${root_abs}/${title}${ext_part}"

    if [[ "$f" != "$desired" ]]; then
      dest="$desired"
      if [[ -e "$desired" ]]; then
        dest="$(dup_dest_path "$root_abs" "$title" "$ext_part")"
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
  t="$(sanitize_base "$t")"
  nt="$(normalize_title "$t")"
  [[ -n "$nt" ]] && printf '%s\n' "$nt" >> "$title_index"
done < "$root_list2"

# ---- Phase B: Traverse tree, move into ROOT, always name Title.ext ----
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

    title="$(get_title "$src")"
    [[ -z "$title" ]] && title="${filename%.*}"
    title="$(sanitize_base "$title")"
    norm_title="$(normalize_title "$title")"
    [[ -z "$norm_title" ]] && norm_title="$(normalize_title "${filename%.*}")"

    candidate="${root_abs}/${title}${ext_part}"

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
    [[ -n "$norm_title" ]] && printf '%s\n' "$norm_title" >> "$title_index"

    # Delete source directory if it has no audio (and then parent, etc.)
    cleanup_no_audio_upwards "$src_dir"
  done < "$files_list"

  finish_phase "Move done. Moved: $moved_count  Dups found: $dups_found  Skipped: $skipped_count"
else
  finish_phase "Move skipped. No audio files found."
fi

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
echo "Moved report: $moved_report" >&2
echo "Duplicates report: $dups_report" >&2
echo "Deleted dirs report: $deleted_dirs_report" >&2
echo "Skipped report: $skipped_report" >&2
