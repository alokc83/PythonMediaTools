
import os
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple, Set

AUDIO_EXTS_DEFAULT = {"mp3", "m4a", "m4b"}
EXT_PRIORITY = {"m4b": 3, "m4a": 2, "mp3": 1}
MAX_BASENAME_LEN = 180

@dataclass(frozen=True)
class AudioFile:
    path: str
    ext: str
    size: int
    title_raw: str
    title_norm: str
    title_display: str

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

def choose_keep(files: List[AudioFile]) -> AudioFile:
    def key(f: AudioFile) -> Tuple[int, int, str]:
        return (EXT_PRIORITY.get(f.ext, 0), f.size, f.path)
    return sorted(files, key=key, reverse=True)[0]

def scan_for_audio_files(directory: str, extensions: Set[str] = AUDIO_EXTS_DEFAULT) -> Tuple[int, List[str]]:
    """
    Recursively scan a directory for audio files.
    Returns (count, list_of_paths).
    """
    paths = []
    count = 0
    try:
        for root, _, files in os.walk(directory):
            for name in files:
                if name.startswith("._"): # Skip Mac resource forks
                    continue
                ext = os.path.splitext(name)[1].lstrip(".").lower()
                if ext in extensions:
                    paths.append(os.path.join(root, name))
                    count += 1
    except Exception:
        pass
    return count, paths

