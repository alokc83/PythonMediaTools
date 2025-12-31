#!/bin/bash
set -u -o pipefail

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
errors_report="${REPORT_DIR}/errors.txt"

: > "$moved_report"
: > "$skipped_report"
: > "$dups_report"
: > "$root_rename_report"
: > "$deleted_dirs_report"
: > "$title_fix_report"
: > "$errors_report"

tmp_dir="$(mktemp -d)"
cleanup_tmp() { rm -rf "$tmp_dir" >/dev/null 2>&1 || true; }
trap cleanup_tmp EXIT

root_abs="$(cd "$ROOT" && pwd -P)"
report_abs="$(cd "$REPORT_DIR" && pwd -P)"
pwd_abs="$(pwd -P)"

log_err() { printf '%s\n' "$*" >> "$errors_report"; }

term_cols() {
  local c="${COLUMNS:-}"
  if [[ -z "$c" ]]; then c="$(tput cols 2>/dev/null || true)"; fi
  [[ -z "$c" ]] && c=120
  echo "$c"
}

progress_line() {
  local phase="$1" current="$2" total="$3" item="$4"
  local cols width percent filled empty bar prefix max_item short line

  cols="$(term_cols)"
  width=28
  percent=0
  if [[ "$total" -gt 0 ]]; then percent=$(( current * 100 / total )); fi

  filled=$(( percent * width / 100 ))
  empty=$(( width - filled ))
  bar="$(printf '%*s' "$filled" '' | tr ' ' '#')$(printf '%*s' "$empty" '' | tr ' ' '.')"

  prefix="[$phase] [$bar] $(printf '%3d' "$percent")% $(printf '%d/%d' "$current" "$total") "
  max_item=$(( cols - ${#prefix} - 1 ))
  if [[ "$max_item" -lt 10 ]]; then max_item=10; fi

  short="$item"
  if [[ ${#short} -gt "$max_item" ]]; then
    short="...${short: -$((max_item - 3))}"
  fi

  line="${prefix}${short}"
  printf '\r\033[2K%-*s' "$cols" "$line" >&2
}

finish_phase() {
  local msg="$1" cols
  cols="$(term_cols)"
  printf '\r\033[2K%-*s\n' "$cols" "$msg" >&2
}

# Pure bash dirname and basename (safe with spaces and special chars)
path_dirname() {
  local p="$1"
  p="${p%/}"
  if [[ "$p" == */* ]]; then
    printf '%s\n' "${p%/*}"
  else
    printf '%s\n' "."
  fi
}

path_basename() {
  local p="$1"
  p="${p%/}"
  printf '%s\n' "${p##*/}"
}

build_find_args() {
  FIND_ARGS=()
  local first=1 IFS=',' exts_arr ext
  read -r -a exts_arr <<< "$AUDIO_EXTS"

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

# Keep casing, only allow A Z a z 0 9 and spaces, collapse spaces, trim
clean_title_display() {
  local s="$1"
  s="$(printf '%s' "$s" | tr '\r\n' '  ')"
  s="$(printf '%s' "$s" | sed 's/[^A-Za-z0-9 ]/ /g; s/[[:space:]]\{1,\}/ /g; s/^ *//; s/ *$//')"
  [[ -z "$s" ]] && s="Untitled"
  echo "$s"
}

normalize_title() {
  local s="$1"
  s="$(printf '%s' "$s" | tr '[:upper:]' '[:lower:]')"
  s="$(printf '%s' "$s" | sed 's/[^a-z0-9 ]/ /g; s/[[:space:]]\{1,\}/ /g; s/^ *//; s/ *$//')"
  [[ -z "$s" ]] && s="untitled"
  echo "$s"
}

dup_dest_path() {
  local dest_dir="$1" base="$2" ext_part="$3"
  local n=1 candidate=""
  while :; do
    candidate="${dest_dir}/${base}-dup-${n}${ext_part}"
    if [[ ! -e "$candidate" ]]; then
      echo "$candidate"
      return
    fi
    n=$((n + 1))
  done
}

write_title_tag() {
  local f="$1" new_title="$2"

  command -v ffmpeg >/dev/null 2>&1 || return 0

  local dir base ext tmp
  dir="$(path_dirname "$f")"
  base="$(path_basename "$f")"

  ext="mp3"
  if [[ "$base" == *.* ]]; then ext="${base##*.}"; fi
  tmp="${dir}/.${base}.tmp.$$.$ext"

  if [[ "$DRYRUN" == "1" ]]; then
    printf '%s\n' "Would write title tag: $f => $new_title" >> "$title_fix_report"
    return 0
  fi

  if ! ffmpeg -hide_banner -loglevel error -y \
      -i "$f" -map 0 -c copy \
      -metadata title="$new_title" \
      "$tmp" 2>>"$errors_report"; then
    rm -f "$tmp" >/dev/null 2>&1 || true
    log_err "ffmpeg failed writing title for: $f"
    return 0
  fi

  if ! mv -- "$tmp" "$f" 2>>"$errors_report"; then
    rm -f "$tmp" >/dev/null 2>&1 || true
    log_err "mv failed replacing file after title write: $f"
    return 0
  fi

  printf '%s\n' "Wrote title tag: $f => $new_title" >> "$title_fix_report"
}

dir_has_audio() {
  local d="$1"
  find "$d" -type f \( "${FIND_ARGS[@]}" \) -print -quit 2>/dev/null | grep -q .
}

is_prefix_path() {
  local a="$1" b="$2"
  [[ "$b" == "$a" ]] && return 0
  [[ "$b" == "$a/"* ]] && return 0
  return 1
}

is_protected_dir() {
  local d="$1"
  [[ "$d" == "$root_abs" ]] && return 0

  if is_prefix_path "$root_abs" "$pwd_abs"; then
    if is_prefix_path "$d" "$pwd_abs"; then return 0; fi
  fi

  if is_prefix_path "$root_abs" "$report_abs"; then
    if is_prefix_path "$d" "$report_abs"; then return 0; fi
  fi

  return 1
}

final_sweep_delete_no_audio_dirs_under_root() {
  local list="${tmp_dir}/dirs_under_root.txt"
  local sorted="${tmp_dir}/dirs_under_root_sorted.txt"

  find "$root_abs" -type d -print0 > "${list}.bin"

  : > "$list"
  while IFS= read -r -d '' d; do
    [[ "$d" == "$root_abs" ]] && continue
    printf '%s\n' "$d" >> "$list"
  done < "${list}.bin"

  awk '{ depth=gsub(/\//,"/"); print depth "\t" $0 }' "$list" | LC_ALL=C sort -nr | cut -f2- > "$sorted"

  local total i d
  total="$(wc -l < "$sorted" | tr -d ' ')"
  [[ -z "$total" ]] && total=0

  i=0
  while IFS= read -r d; do
    i=$((i + 1))
    progress_line "Cleanup" "$i" "$total" "$d"
    [[ -d "$d" ]] || continue

    if is_protected_dir "$d"; then
      continue
    fi

    if ! dir_has_audio "$d"; then
      if [[ "$DRYRUN" == "1" ]]; then
        printf '%s\n' "Would delete (no audio): $d" >> "$deleted_dirs_report"
      else
        rm -rf -- "$d" 2>>"$errors_report" || log_err "rm failed: $d"
        printf '%s\n' "Deleted (no audio): $d" >> "$deleted_dirs_report"
      fi
    fi
  done < "$sorted"

  finish_phase "Cleanup done."
}

build_find_args

echo "Root: $root_abs" >&2
echo "Audio extensions: $AUDIO_EXTS" >&2
echo "Report dir: $report_abs" >&2
echo "Working dir: $pwd_abs" >&2
if [[ "$DRYRUN" == "1" ]]; then
  echo "Mode: dry run" >&2
else
  echo "Mode: move and cleanup" >&2
fi
echo "" >&2

# Phase A: rename audio already in root
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

    filename="$(path_basename "$f")"
    ext_part=""
    if [[ "$filename" == *.* ]]; then ext_part=".${filename##*.}"; fi

    raw_title="$(get_title "$f")"
    [[ -z "$raw_title" ]] && raw_title="${filename%.*}"

    clean_title="$(clean_title_display "$raw_title")"
    write_title_tag "$f" "$clean_title"

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
        mv -- "$f" "$dest" 2>>"$errors_report" || { log_err "mv failed: $f -> $dest"; continue; }
        printf '%s\n' "Renamed in root: $f -> $dest" >> "$root_rename_report"
      fi

      root_renamed_count=$((root_renamed_count + 1))
      f="$dest"
    fi

    nt="$(normalize_title "$clean_title")"
    [[ -n "$nt" ]] && printf '%s\n' "$nt" >> "$title_index"
  done < "$root_list"

  finish_phase "Root rename done. Renamed: $root_renamed_count  Root dups: $root_dups_found"
else
  finish_phase "Root rename skipped."
fi

# Rebuild title index from current root state
: > "$title_index"
root_list2="${tmp_dir}/root_audio2.bin"
find "$root_abs" -maxdepth 1 -type f \( "${FIND_ARGS[@]}" \) -print0 > "$root_list2"
while IFS= read -r -d '' f; do
  t="$(get_title "$f")"
  [[ -z "$t" ]] && t="$(path_basename "${f%.*}")"
  t="$(clean_title_display "$t")"
  nt="$(normalize_title "$t")"
  [[ -n "$nt" ]] && printf '%s\n' "$nt" >> "$title_index"
done < "$root_list2"

# Phase B: traverse and move
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

    src_dir="$(path_dirname "$src")"
    if ! src_dir="$(cd "$src_dir" 2>>"$errors_report" && pwd -P)"; then
      log_err "cd failed for src dir: $src_dir   file: $src"
      continue
    fi

    if [[ "$src_dir" == "$root_abs" ]]; then
      printf '%s\n' "Already in root, skip: $src" >> "$skipped_report"
      skipped_count=$((skipped_count + 1))
      continue
    fi

    filename="$(path_basename "$src")"
    ext_part=""
    if [[ "$filename" == *.* ]]; then ext_part=".${filename##*.}"; fi

    raw_title="$(get_title "$src")"
    [[ -z "$raw_title" ]] && raw_title="${filename%.*}"

    clean_title="$(clean_title_display "$raw_title")"
    write_title_tag "$src" "$clean_title"

    nt="$(normalize_title "$clean_title")"
    candidate="${root_abs}/${clean_title}${ext_part}"

    is_dup=0
    if [[ -e "$candidate" ]]; then
      is_dup=1
    elif [[ -n "$nt" ]] && grep -Fqx "$nt" "$title_index" 2>/dev/null; then
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
      mv -- "$src" "$dest" 2>>"$errors_report" || { log_err "mv failed: $src -> $dest"; continue; }
      printf '%s\n' "Moved: $src -> $dest" >> "$moved_report"
    fi

    moved_count=$((moved_count + 1))
    [[ -n "$nt" ]] && printf '%s\n' "$nt" >> "$title_index"
  done < "$files_list"

  finish_phase "Move done. Moved: $moved_count  Dups: $dups_found  Skipped: $skipped_count"
else
  finish_phase "Move skipped."
fi

# Phase C: cleanup sweep
final_sweep_delete_no_audio_dirs_under_root

deleted_dirs_count="$(grep -c '^Deleted (no audio):' "$deleted_dirs_report" 2>/dev/null || true)"

echo "" >&2
echo "Summary" >&2
echo "Moved: $moved_count" >&2
echo "Root renamed: $root_renamed_count" >&2
echo "Duplicates in root rename: $root_dups_found" >&2
echo "Duplicates while moving: $dups_found" >&2
echo "Total duplicates: $((root_dups_found + dups_found))" >&2
echo "Dirs deleted (no audio): $deleted_dirs_count" >&2
echo "Skipped: $skipped_count" >&2
echo "" >&2
echo "Reports" >&2
echo "Root rename report: $root_rename_report" >&2
echo "Title fix report: $title_fix_report" >&2
echo "Moved report: $moved_report" >&2
echo "Duplicates report: $dups_report" >&2
echo "Deleted dirs report: $deleted_dirs_report" >&2
echo "Errors report: $errors_report" >&2
echo "Skipped report: $skipped_report" >&2
