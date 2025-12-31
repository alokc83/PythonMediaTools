import os
import shutil
import sys
from typing import List, Set

from common import (
  build_all_subdirs,
  finish_phase,
  is_protected_dir,
  list_audio_files_recursive,
  make_unique_path_with_dup,
  progress_line,
  progress_line_unknown,
  prompt_exts,
  prompt_yes_no,
  protected_prefixes,
  run_ffprobe_title,
  safe_basename_from_title,
  safe_input,
  clean_title_display,
)


def run() -> int:
  root_dir = safe_input("Enter root directory to flatten: ")
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

  exts = prompt_exts()
  dry_run = prompt_yes_no("Dry run", default_no=True)
  cleanup_dirs = prompt_yes_no("Delete directories under root that contain no audio", default_no=False)

  print("")
  print("Plan")
  print(f"Root: {root_abs}")
  print(f"Extensions: {', '.join(sorted(exts))}")
  print(f"Dry run: {dry_run}")
  print(f"Cleanup dirs: {cleanup_dirs}")
  ans = safe_input("Type yes to proceed: ")
  if ans is None:
    return 1
  if ans.strip().lower() != "yes":
    print("Aborted. Nothing changed.")
    return 0

  prot = protected_prefixes(root_abs)

  root_files: List[str] = []
  try:
    for name in os.listdir(root_abs):
      p = os.path.join(root_abs, name)
      if not os.path.isfile(p):
        continue
      ext = os.path.splitext(name)[1].lstrip(".").lower()
      if ext in exts:
        root_files.append(p)
  except Exception:
    pass

  renamed_root = 0
  skipped_no_title = 0
  skipped_same = 0
  errors_root = 0

  for idx, p in enumerate(root_files, 1):
    progress_line("RootRename", idx, max(1, len(root_files)), p)
    ext = os.path.splitext(p)[1].lstrip(".").lower()

    raw_title = run_ffprobe_title(p)
    if not raw_title:
      skipped_no_title += 1
      continue

    display = clean_title_display(raw_title)
    desired_name = safe_basename_from_title(display, ext)
    desired_path = os.path.join(root_abs, desired_name)

    if os.path.abspath(p) == os.path.abspath(desired_path):
      skipped_same += 1
      continue

    desired_path = make_unique_path_with_dup(root_abs, desired_name)

    try:
      if not dry_run:
        os.rename(p, desired_path)
      renamed_root += 1
    except Exception as e:
      errors_root += 1
      sys.stderr.write("\n")
      sys.stderr.write(f"Root rename failed: {p} -> {desired_path}\nReason: {e}\n")

  finish_phase(
    f"RootRename done. Renamed: {renamed_root} Skipped(no title): {skipped_no_title} Skipped(same): {skipped_same} Errors: {errors_root}"
  )

  all_audio = list_audio_files_recursive(root_abs, exts)

  moved = 0
  already_in_root = 0
  errors = 0

  for idx, src in enumerate(all_audio, 1):
    progress_line("MoveToRoot", idx, max(1, len(all_audio)), src)

    src_dir = os.path.abspath(os.path.dirname(src))
    if src_dir == root_abs:
      already_in_root += 1
      continue

    ext = os.path.splitext(src)[1].lstrip(".").lower()
    raw_title = run_ffprobe_title(src)
    if raw_title:
      display = clean_title_display(raw_title)
      desired_name = safe_basename_from_title(display, ext)
    else:
      desired_name = os.path.basename(src)

    dest = make_unique_path_with_dup(root_abs, desired_name)

    try:
      if not dry_run:
        shutil.move(src, dest)
      moved += 1
    except Exception as e:
      errors += 1
      sys.stderr.write("\n")
      sys.stderr.write(f"Move failed: {src} -> {dest}\nReason: {e}\n")

  finish_phase("MoveToRoot done.")

  deleted_dirs = 0
  if cleanup_dirs:
    remaining_audio = set(list_audio_files_recursive(root_abs, exts))

    keep_dirs: Set[str] = set()
    rem_list = list(remaining_audio)
    for idx, ap in enumerate(rem_list, 1):
      progress_line("KeepMap", idx, max(1, len(rem_list)), ap)
      d = os.path.abspath(os.path.dirname(ap))
      while True:
        keep_dirs.add(d)
        if d == root_abs:
          break
        nd = os.path.abspath(os.path.dirname(d))
        if nd == d:
          break
        d = nd
    finish_phase("KeepMap done.")

    dirs_all = build_all_subdirs(root_abs)
    dirs_all.sort(key=lambda p: p.count(os.sep), reverse=True)

    for idx, d in enumerate(dirs_all, 1):
      progress_line("Cleanup", idx, max(1, len(dirs_all)), d)
      d_abs = os.path.abspath(d)

      if d_abs in keep_dirs:
        continue
      if is_protected_dir(d_abs, root_abs, prot):
        continue

      try:
        if not dry_run:
          shutil.rmtree(d_abs)
        deleted_dirs += 1
      except Exception:
        continue

    finish_phase("Cleanup done.")

  print("")
  print("Done")
  print(f"Root renamed: {renamed_root}")
  print(f"Moved to root: {moved}")
  print(f"Already in root: {already_in_root}")
  print(f"Move errors: {errors}")
  if cleanup_dirs:
    print(f"Dirs deleted: {deleted_dirs}")
  if dry_run:
    print("Dry run enabled. Nothing changed.")
  return 0