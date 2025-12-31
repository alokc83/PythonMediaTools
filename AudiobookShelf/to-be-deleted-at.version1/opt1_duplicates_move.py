import os
import shutil
import sys
from typing import List, Tuple

from common import (
  build_groups_by_title,
  choose_keep,
  finish_phase,
  make_unique_path_with_dup,
  prompt_dirs_list,
  prompt_exts,
  prompt_int,
  prompt_out_dir,
  prompt_yes_no,
  progress_line,
  safe_basename_from_title,
  safe_input,
  list_audio_files_in_dirs_flat,
)


def run() -> int:
  dirs = prompt_dirs_list()
  exts = prompt_exts()
  dry_run = prompt_yes_no("Dry run", default_no=True)
  out_dir = prompt_out_dir()
  show_groups = prompt_int("How many duplicate groups to print in plan", 10)

  all_paths = list_audio_files_in_dirs_flat(dirs, exts)
  if not all_paths:
    print("No audio files found.")
    return 0

  groups, missing_title = build_groups_by_title(all_paths)

  total_files = sum(len(v) for v in groups.values())
  unique_titles = len(groups)
  dup_groups = [v for v in groups.values() if len(v) > 1]
  dup_group_count = len(dup_groups)
  dup_file_count = sum(len(v) - 1 for v in dup_groups)
  result_count = unique_titles

  keep_plan: List[Tuple[str, object, list]] = []
  items = list(groups.items())
  for idx, (k, files) in enumerate(items, 1):
    progress_line("PickKeep", idx, len(items), files[0].title_display)
    keep_plan.append((k, choose_keep(files), files))
  finish_phase("PickKeep done.")

  keep_plan.sort(key=lambda x: x[1].title_display.lower())

  print("")
  print("Plan")
  print(f"Input directories: {len(dirs)}")
  for d in dirs:
    print(f"  {d}")
  print(f"Output directory: {out_dir}")
  print(f"Extensions: {', '.join(sorted(exts))}")
  print("")
  print(f"Files scanned: {total_files}")
  print(f"Titles found: {unique_titles}")
  print(f"Duplicate groups: {dup_group_count}")
  print(f"Duplicate files: {dup_file_count}")
  print(f"Result files in output: {result_count}")
  print(f"Files missing title tag (fell back to filename): {missing_title}")

  if dup_group_count > 0:
    print("")
    print("Sample duplicate groups")
    shown = 0
    for _, keep, files in keep_plan:
      if len(files) <= 1:
        continue
      shown += 1
      print("")
      print(f"Title: {keep.title_display}")
      print(f"Keep:  {keep.path}  ({keep.ext}  {keep.size} bytes)")
      for f in sorted(files, key=lambda x: x.path):
        if f.path == keep.path:
          continue
        print(f"Dup:   {f.path}  ({f.ext}  {f.size} bytes)")
      if shown >= show_groups:
        break

  print("")
  print("No files have been moved yet.")
  ans = safe_input("Type yes to proceed with moving the keep files into output directory: ")
  if ans is None:
    return 1
  if ans.strip().lower() != "yes":
    print("Aborted. Nothing changed.")
    return 0
  if dry_run:
    print("Dry run enabled. Nothing moved.")
    return 0

  os.makedirs(out_dir, exist_ok=True)

  moved = 0
  skipped = 0
  errors = 0
  for idx, (_, keep, _files) in enumerate(keep_plan, 1):
    progress_line("MoveOut", idx, len(keep_plan), keep.path)
    desired = safe_basename_from_title(keep.title_display, keep.ext)
    dest = make_unique_path_with_dup(out_dir, desired)

    try:
      if os.path.abspath(keep.path) == os.path.abspath(dest):
        skipped += 1
        continue
      shutil.move(keep.path, dest)
      moved += 1
    except Exception as e:
      errors += 1
      sys.stderr.write("\n")
      sys.stderr.write(f"Move failed: {keep.path} -> {dest}\nReason: {e}\n")

  finish_phase("MoveOut done.")
  print("")
  print("Done")
  print(f"Moved: {moved}")
  print(f"Skipped: {skipped}")
  print(f"Errors: {errors}")
  print("Note: duplicate copies are left in place.")
  return 0