import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

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


def prompt_exts() -> Set[str]:
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


def list_audio_files_in_dirs_flat(dirs: List[str], exts: Set[str]) -> List[str]:
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


def list_audio_files_recursive(root: str, exts: Set[str]) -> List[str]:
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


def protected_prefixes(root_abs: str) -> List[str]:
  prefixes: List[str] = []
  prefixes.append(os.path.abspath(os.getcwd()))
  try:
    prefixes.append(os.path.abspath(os.path.dirname(__file__)))
  except Exception:
    pass

  inside: List[str] = []
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