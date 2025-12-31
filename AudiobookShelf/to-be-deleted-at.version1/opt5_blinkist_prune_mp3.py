import os
import sys
from typing import Dict, List, Set, Tuple

from common import (
  finish_phase,
  progress_line,
  progress_line_unknown,
  prompt_yes_no,
  safe_input,
)


def run() -> int:
  root_dir = safe_input("Enter Blinkist root directory to prune mp3: ")
  if root_dir is None:
    return 1
  root_dir = root_dir.strip()
  if not root_dir:
    print("Root directory is required.")
    return 2
  root_abs = os.path.abspath(root_dir)
  if not os.path.isdir(root_abs):
    print("Root directory does not exist.")
    return 2

  dry_run = prompt_yes_no("Dry run", default_no=True)

  print("")
  print("Plan")
  print(f"Root: {root_abs}")
  print("Rule: delete mp3 only if same base name exists as m4a or m4b in the same directory")
  print(f"Dry run: {dry_run}")
  ans = safe_input("Type yes to proceed: ")
  if ans is None:
    return 1
  if ans.strip().lower() != "yes":
    print("Aborted. Nothing changed.")
    return 0

  to_delete: List[str] = []
  dirs_scanned = 0
  mp3_seen = 0
  protect_seen = 0

  for dirpath, _dirnames, filenames in os.walk(root_abs):
    dirs_scanned += 1

    present: Dict[str, Set[str]] = {}
    for name in filenames:
      ext = os.path.splitext(name)[1].lstrip(".").lower()
      if ext not in {"mp3", "m4a", "m4b"}:
        continue
      base = os.path.splitext(name)[0].lower()
      present.setdefault(base, set()).add(ext)

    for base, exts in present.items():
      if "mp3" in exts:
        mp3_seen += 1
      if "m4a" in exts or "m4b" in exts:
        protect_seen += 1

      if "mp3" in exts and ("m4a" in exts or "m4b" in exts):
        mp3_path = os.path.join(dirpath, base + ".mp3")
        if os.path.isfile(mp3_path):
          to_delete.append(mp3_path)

    progress_line_unknown(
      "ScanPrune",
      f"dirs={dirs_scanned} delete_candidates={len(to_delete)} {dirpath}",
    )

  finish_phase(f"ScanPrune done. Candidates to delete: {len(to_delete)}")

  if not to_delete:
    print("Nothing to delete.")
    return 0

  print("")
  print("Summary")
  print(f"Directories scanned: {dirs_scanned}")
  print(f"mp3 base names seen: {mp3_seen}")
  print(f"m4a or m4b base names seen: {protect_seen}")
  print(f"mp3 files that will be deleted: {len(to_delete)}")

  show_n = min(20, len(to_delete))
  print("")
  print(f"Sample (first {show_n})")
  for p in to_delete[:show_n]:
    print(p)

  ans2 = safe_input("Type yes to delete these mp3 files: ")
  if ans2 is None:
    return 1
  if ans2.strip().lower() != "yes":
    print("Aborted. Nothing changed.")
    return 0

  deleted = 0
  errors = 0
  to_delete.sort()

  for idx, p in enumerate(to_delete, 1):
    progress_line("DeleteMP3", idx, len(to_delete), p)
    try:
      if not dry_run:
        os.remove(p)
      deleted += 1
    except Exception as e:
      errors += 1
      sys.stderr.write("\n")
      sys.stderr.write(f"Delete failed: {p}\nReason: {e}\n")

  finish_phase("DeleteMP3 done.")
  print("")
  print("Done")
  print(f"Deleted: {deleted}")
  print(f"Errors: {errors}")
  if dry_run:
    print("Dry run enabled. Nothing changed.")
  return 0