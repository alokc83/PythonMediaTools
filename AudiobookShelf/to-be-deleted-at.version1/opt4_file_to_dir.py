import os
import shutil

from common import (
  finish_phase,
  progress_line,
  prompt_exts,
  prompt_yes_no,
  safe_input,
)


def run() -> int:
  target_dir = safe_input("Enter directory to process (current level only): ")
  if target_dir is None:
    return 1
  target_dir = target_dir.strip()
  if not target_dir:
    print("Directory is required.")
    return 2
  target_abs = os.path.abspath(target_dir)
  if not os.path.isdir(target_abs):
    print("Directory does not exist.")
    return 2

  exts = prompt_exts()
  dry_run = prompt_yes_no("Dry run", default_no=True)

  print("")
  print("Plan")
  print(f"Directory: {target_abs}")
  print(f"Extensions: {', '.join(sorted(exts))}")
  print(f"Dry run: {dry_run}")
  ans = safe_input("Type yes to proceed: ")
  if ans is None:
    return 1
  if ans.strip().lower() != "yes":
    print("Aborted. Nothing changed.")
    return 0

  files = []
  for name in os.listdir(target_abs):
    p = os.path.join(target_abs, name)
    if not os.path.isfile(p):
      continue
    ext = os.path.splitext(name)[1].lstrip(".").lower()
    if ext in exts:
      files.append(p)

  files.sort()
  finish_phase(f"FileToDir scan done. Files found: {len(files)}")

  moved = 0
  skipped_exists_not_dir = 0
  skipped_dest_exists = 0
  errors = 0

  for idx, src in enumerate(files, 1):
    progress_line("FileToDir", idx, max(1, len(files)), src)
    name = os.path.basename(src)
    base = os.path.splitext(name)[0]
    folder = os.path.join(target_abs, base)

    try:
      if os.path.exists(folder) and not os.path.isdir(folder):
        skipped_exists_not_dir += 1
        continue

      dest = os.path.join(folder, name)
      if os.path.exists(dest):
        skipped_dest_exists += 1
        continue

      if not dry_run:
        os.makedirs(folder, exist_ok=True)
        shutil.move(src, dest)
      moved += 1
    except Exception:
      errors += 1

  finish_phase("FileToDir done.")
  print("")
  print("Done")
  print(f"Moved: {moved}")
  print(f"Skipped (base exists and is not a directory): {skipped_exists_not_dir}")
  print(f"Skipped (destination exists): {skipped_dest_exists}")
  print(f"Errors: {errors}")
  if dry_run:
    print("Dry run enabled. Nothing changed.")
  return 0