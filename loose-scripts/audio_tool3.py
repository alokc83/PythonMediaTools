#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set

AUDIO_EXTS_DEFAULT = {"mp3", "m4a", "m4b"}
EXT_PRIORITY = {"m4b": 3, "m4a": 2, "mp3": 1}

MAX_BASENAME_LEN = 180
BAR_WIDTH = 28


@dataclass(frozen=True)
class AudioFile:
  path: str
  ext: str
  size: int
  title_raw: str
  title_norm: str
  title_display: str


def term_cols() -> int:
  try:
    env_cols = os.environ.get("COLUMNS")
    if env_cols:
      return int(env_cols)
    return int(subprocess.check_output(["tput", "cols"], text=True).strip())
  except Exception:
    return 120


def truncate_middle(s: str, max_len: int) -> str:
  if max_len < 10:
    return s[:max_len]
  if len(s) <= max_len:
    return s
  keep = max_len - 3
  left = keep // 2
  right = keep - left
  return s[:left] + "..." + s[-right:]


def progress_line(phase: str, cur: int, total: int, item: str) -> None:
  cols = term_cols()
  pct = int(cur * 100 / total) if total else 0
  filled = int(pct * BAR_WIDTH / 100)
  empty = BAR_WIDTH - filled
  bar = "#" * filled + "." * empty

  prefix = f"[{phase}] [{bar}] {pct:3d}% {cur}/{total} "
  max_item = max(10, cols - len(prefix) - 1)
  item2 = truncate_middle(item, max_item)
  sys.stderr.write("\r\033[2K" + (prefix + item2)[:cols])
  sys.stderr.flush()


def progress_line_unknown(phase: str, msg: str) -> None:
  cols = term_cols()
  prefix = f"[{phase}] "
  max_msg = max(10, cols - len(prefix) - 1)
  msg2 = truncate_middle(msg, max_msg)
  sys.stderr.write("\r\033[2K" + (prefix + msg2)[:cols])
  sys.stderr.flush()


def finish_phase(msg: str) -> None:
  cols = term_cols()
  sys.stderr.write("\r\033[2K" + msg[:cols] + "\n")
  sys.stderr.flush()


def safe_input(prompt: str) -> Optional[str]:
  try:
    return input(prompt)
  except KeyboardInterrupt:
    sys.stderr.write("\nCancelled.\n")
    return None


def run_ffprobe_title(path: str) -> str:
  try:
    res = subprocess.run(
      [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format_tags=title",
        "-of",
        "default=nw=1:nk=1",
        path,
      ],
      stdout=subprocess.PIPE,
      stderr=subprocess.DEVNULL,
      text=True,
      check=False,
    )
    for line in (res.stdout or "").splitlines():
      line = line.strip()
      if line:
        return line
    return ""
  except FileNotFoundError:
    return ""


def clean_title_display(title: str) -> str:
  s = title.replace("\r", " ").replace("\n", " ")
  s = re.sub(r"[^A-Za-z0-9 ]+", " ", s)
  s = re.sub(r"\s+", " ", s).strip()
  if not s:
    s = "Untitled"
  if len(s) > MAX_BASENAME_LEN:
    s = s[:MAX_BASENAME_LEN].rstrip()
  return s or "Untitled"


def normalize_title(title: str) -> str:
  s = title.lower()
  s = re.sub(r"[^a-z0-9 ]+", " ", s)
  s = re.sub(r"\s+", " ", s).strip()
  return s or "untitled"


def safe_basename_from_title(title_display: str, ext: str) -> str:
  base = clean_title_display(title_display)
  if len(base) > MAX_BASENAME_LEN:
    base = base[:MAX_BASENAME_LEN].rstrip()
  if not base:
    base = "Untitled"
  return f"{base}.{ext}"


def _fit_base_for_suffix(base: str, suffix: str) -> str:
  allowed = MAX_BASENAME_LEN - len(suffix)
  if allowed < 10:
    allowed = 10
  if len(base) > allowed:
    base = base[:allowed].rstrip()
  if not base:
    base = "Untitled"
  return base


def make_unique_path_with_dup(dest_dir: str, desired_name: str) -> str:
  # collision style: name--dup1.ext, name--dup2.ext
  base, ext = os.path.splitext(desired_name)
  candidate = os.path.join(dest_dir, desired_name)
  if not os.path.exists(candidate):
    return candidate

  n = 1
  while True:
    suffix = f"--dup{n}"
    b = _fit_base_for_suffix(base, suffix)
    cand_name = f"{b}{suffix}{ext}"
    cand = os.path.join(dest_dir, cand_name)
    if not os.path.exists(cand):
      return cand
    n += 1


def list_audio_files_in_dirs_flat(dirs: List[str], exts: set) -> List[str]:
  all_paths: List[str] = []
  for i, d in enumerate(dirs, 1):
    progress_line("ScanDirs", i, len(dirs), d)
    try:
      for name in os.listdir(d):
        p = os.path.join(d, name)
        if not os.path.isfile(p):
          continue
        ext = os.path.splitext(name)[1].lstrip(".").lower()
        if ext in exts:
          all_paths.append(p)
    except Exception:
      continue
  finish_phase(f"ScanDirs done. Audio files found: {len(all_paths)}")
  return all_paths


def list_audio_files_recursive(root: str, exts: set) -> List[str]:
  out: List[str] = []
  dirs_scanned = 0
  audio_found = 0

  for dirpath, _dirnames, filenames in os.walk(root):
    dirs_scanned += 1
    for name in filenames:
      ext = os.path.splitext(name)[1].lstrip(".").lower()
      if ext in exts:
        out.append(os.path.join(dirpath, name))
        audio_found += 1
    progress_line_unknown("ScanTree", f"dirs={dirs_scanned} audio={audio_found} {dirpath}")

  finish_phase(f"ScanTree done. Dirs scanned: {dirs_scanned} Audio files found: {len(out)}")
  return out


def build_groups_by_title(paths: List[str]) -> Tuple[Dict[str, List[AudioFile]], int]:
  groups: Dict[str, List[AudioFile]] = {}
  missing_title = 0

  for idx, p in enumerate(paths, 1):
    progress_line("MetaRead", idx, len(paths), p)

    ext = os.path.splitext(p)[1].lstrip(".").lower()
    try:
      size = os.path.getsize(p)
    except OSError:
      continue

    raw_title = run_ffprobe_title(p)
    if not raw_title:
      missing_title += 1
      raw_title = os.path.splitext(os.path.basename(p))[0]

    display = clean_title_display(raw_title)
    norm = normalize_title(display)

    af = AudioFile(
      path=p,
      ext=ext,
      size=size,
      title_raw=raw_title,
      title_norm=norm,
      title_display=display,
    )
    groups.setdefault(norm, []).append(af)

  finish_phase(f"MetaRead done. Titles grouped: {len(groups)}")
  return groups, missing_title


def choose_keep(files: List[AudioFile]) -> AudioFile:
  def key(f: AudioFile) -> Tuple[int, int, str]:
    return (EXT_PRIORITY.get(f.ext, 0), f.size, f.path)
  return sorted(files, key=key, reverse=True)[0]


def prompt_yes_no(msg: str, default_no: bool = True) -> bool:
  suffix = " [y/N]: " if default_no else " [Y/n]: "
  ans = safe_input(msg + suffix)
  if ans is None:
    raise SystemExit(1)
  ans = ans.strip().lower()
  if not ans:
    return not default_no
  return ans in {"y", "yes"}


def prompt_dirs_list() -> List[str]:
  raw = safe_input("Enter directories (separated by commas): ")
  if raw is None:
    raise SystemExit(1)
  parts = [p.strip() for p in raw.split(",") if p.strip()]
  dirs = [os.path.abspath(p) for p in parts]
  bad = [d for d in dirs if not os.path.isdir(d)]
  if bad:
    print("These are not valid directories:")
    for d in bad:
      print(f"  {d}")
    raise SystemExit(2)
  if not dirs:
    print("No directories provided.")
    raise SystemExit(2)
  return dirs


def prompt_exts() -> set:
  raw = safe_input("Enter extensions (comma separated) [default mp3,m4a,m4b]: ")
  if raw is None:
    raise SystemExit(1)
  raw = raw.strip()
  if not raw:
    return set(AUDIO_EXTS_DEFAULT)
  exts = {e.strip().lower() for e in raw.split(",") if e.strip()}
  return exts or set(AUDIO_EXTS_DEFAULT)


def prompt_out_dir() -> str:
  raw = safe_input("Enter output directory path: ")
  if raw is None:
    raise SystemExit(1)
  raw = raw.strip()
  if not raw:
    print("Output directory is required.")
    raise SystemExit(2)
  return os.path.abspath(raw)


def prompt_int(msg: str, default: int) -> int:
  raw = safe_input(f"{msg} [{default}]: ")
  if raw is None:
    raise SystemExit(1)
  raw = raw.strip()
  if not raw:
    return default
  try:
    return int(raw)
  except Exception:
    return default


def task_duplicates_and_move(dirs: List[str], exts: set, out_dir: str, show_groups: int, dry_run: bool) -> None:
  all_paths = list_audio_files_in_dirs_flat(dirs, exts)
  if not all_paths:
    print("No audio files found.")
    return

  groups, missing_title = build_groups_by_title(all_paths)

  total_files = sum(len(v) for v in groups.values())
  unique_titles = len(groups)
  dup_groups = [v for v in groups.values() if len(v) > 1]
  dup_group_count = len(dup_groups)
  dup_file_count = sum(len(v) - 1 for v in dup_groups)
  result_count = unique_titles

  keep_plan: List[Tuple[str, AudioFile, List[AudioFile]]] = []
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
    return
  if ans.strip().lower() != "yes":
    print("Aborted. Nothing changed.")
    return
  if dry_run:
    print("Dry run enabled. Nothing moved.")
    return

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


def task_rename_to_title(dirs: List[str], exts: set, dry_run: bool) -> None:
  paths = list_audio_files_in_dirs_flat(dirs, exts)
  if not paths:
    print("No audio files found.")
    return

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
    return
  if ans.strip().lower() != "yes":
    print("Aborted. Nothing changed.")
    return
  if dry_run:
    print("Dry run enabled. Nothing renamed.")
    return

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


def protected_prefixes(root_abs: str) -> List[str]:
  prefixes = []
  prefixes.append(os.path.abspath(os.getcwd()))
  try:
    prefixes.append(os.path.abspath(os.path.dirname(__file__)))
  except Exception:
    pass

  inside = []
  for p in prefixes:
    try:
      if os.path.commonpath([root_abs, p]) == root_abs:
        inside.append(p)
    except Exception:
      pass
  return inside


def is_protected_dir(dir_path: str, root_abs: str, protected: List[str]) -> bool:
  if os.path.abspath(dir_path) == root_abs:
    return True
  for p in protected:
    try:
      if os.path.commonpath([dir_path, p]) == os.path.abspath(dir_path):
        return True
    except Exception:
      continue
  return False


def build_all_subdirs(root_abs: str) -> List[str]:
  dirs_all: List[str] = []
  dirs_scanned = 0
  for dirpath, dirnames, _filenames in os.walk(root_abs):
    dirs_scanned += 1
    for dn in dirnames:
      dirs_all.append(os.path.join(dirpath, dn))
    progress_line_unknown("BuildDelList", f"dirs={dirs_scanned} found={len(dirs_all)} {dirpath}")
  finish_phase(f"BuildDelList done. Dirs collected: {len(dirs_all)}")
  return dirs_all


def task_flatten_to_root(root_dir: str, exts: set, dry_run: bool, cleanup_dirs: bool) -> None:
  root_abs = os.path.abspath(root_dir)
  if not os.path.isdir(root_abs):
    print("Root directory does not exist.")
    return

  prot = protected_prefixes(root_abs)

  # Phase 1: rename audio already in root using ONLY title tag
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

  # Phase 2: move all audio from subtree to root
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

  # Phase 3: cleanup directories with no audio anywhere in their subtree
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


def main() -> int:
  print("")
  print("Audio Tool Menu")
  print("1) Find duplicates by Title and move one per title into an output directory")
  print("2) Rename files in place to Title metadata (Title.ext)")
  print("3) Flatten audio to a root directory (recursive move to root, add --dupN on conflicts, optional cleanup)")
  print("q) Quit")
  print("")

  choice = safe_input("Choose an option: ")
  if choice is None:
    return 1
  choice = choice.strip().lower()

  if choice in {"q", "quit", "exit"}:
    return 0

  if choice == "1":
    dirs = prompt_dirs_list()
    exts = prompt_exts()
    dry_run = prompt_yes_no("Dry run", default_no=True)
    out_dir = prompt_out_dir()
    show_groups = prompt_int("How many duplicate groups to print in plan", 10)
    task_duplicates_and_move(dirs, exts, out_dir, show_groups, dry_run)
    return 0

  if choice == "2":
    dirs = prompt_dirs_list()
    exts = prompt_exts()
    dry_run = prompt_yes_no("Dry run", default_no=True)
    task_rename_to_title(dirs, exts, dry_run)
    return 0

  if choice == "3":
    root_dir = safe_input("Enter root directory to flatten: ")
    if root_dir is None:
      return 1
    root_dir = root_dir.strip()
    if not root_dir:
      print("Root directory is required for option 3.")
      return 2
    root_dir = os.path.abspath(root_dir)

    exts = prompt_exts()
    dry_run = prompt_yes_no("Dry run", default_no=True)
    cleanup = prompt_yes_no("Delete directories under root that contain no audio", default_no=False)

    print("")
    print("Plan")
    print(f"Root: {root_dir}")
    print(f"Extensions: {', '.join(sorted(exts))}")
    print(f"Dry run: {dry_run}")
    print(f"Cleanup dirs: {cleanup}")
    ans = safe_input("Type yes to proceed: ")
    if ans is None:
      return 1
    if ans.strip().lower() != "yes":
      print("Aborted. Nothing changed.")
      return 0

    task_flatten_to_root(root_dir, exts, dry_run, cleanup)
    return 0

  print("Unknown option.")
  return 2


if __name__ == "__main__":
  raise SystemExit(main())
