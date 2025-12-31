import os
import sys
from typing import List, Tuple

from common import (
  finish_phase,
  make_unique_path_with_dup,
  prompt_dirs_list,
  prompt_exts,
  prompt_yes_no,
  progress_line,
  run_ffprobe_title,
  safe_basename_from_title,
  safe_input,
  list_audio_files_in_dirs_flat,
  clean_title_display,
)


def run() -> int:
  dirs = prompt_dirs_list()
  exts = prompt_exts()
  dry_run = prompt_yes_no("Dry run", default_no=True)

  paths = list_audio_files_in_dirs_flat(dirs, exts)
  if not paths:
    print("No audio files found.")
    return 0

  plan: List[Tuple[str, str]] = []
  missing_title = 0
  already_ok = 0

  for idx, p in enumerate(paths, 1):
    progress_line("PlanRename", idx, len(paths), p)
    ext = os.path.splitext(p)[1].lstrip(".").lower()

    raw_title = run_ffprobe_title(p)
    if not raw_title:
      missing_title += 1
      continue

    display = clean_title_display(raw_title)
    desired_name = safe_basename_from_title(display, ext)
    dir_path = os.path.dirname(p)
    desired_path = os.path.join(dir_path, desired_name)

    if os.path.abspath(p) == os.path.abspath(desired_path):
      already_ok += 1
      continue

    desired_path = make_unique_path_with_dup(dir_path, desired_name)
    plan.append((p, desired_path))

  finish_phase("PlanRename done.")

  print("")
  print("Plan")
  print(f"Files scanned: {len(paths)}")
  print(f"Will rename: {len(plan)}")
  print(f"Skipped (missing title tag): {missing_title}")
  print(f"Skipped (already matching title): {already_ok}")

  ans = safe_input("Type yes to proceed with renaming: ")
  if ans is None:
    return 1
  if ans.strip().lower() != "yes":
    print("Aborted. Nothing changed.")
    return 0
  if dry_run:
    print("Dry run enabled. Nothing renamed.")
    return 0

  renamed = 0
  errors = 0
  for idx, (src, dst) in enumerate(plan, 1):
    progress_line("Rename", idx, len(plan), src)
    try:
      os.rename(src, dst)
      renamed += 1
    except Exception as e:
      errors += 1
      sys.stderr.write("\n")
      sys.stderr.write(f"Rename failed: {src} -> {dst}\nReason: {e}\n")

  finish_phase("Rename done.")
  print("")
  print("Done")
  print(f"Renamed: {renamed}")
  print(f"Errors: {errors}")
  return 0