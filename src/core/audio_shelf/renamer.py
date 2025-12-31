
import os
import sys
from typing import List, Tuple, Optional, Callable, Dict, Set
from .common import (
    run_ffprobe_title,
    clean_title_display,
    safe_basename_from_title,
    make_unique_path_with_dup
)

class TitleRenamer:
    def __init__(self):
        self.paths: List[str] = []
        self.plan: List[Tuple[str, str]] = [] # (src, dst)
        self.missing_title_count = 0
        self.already_ok_count = 0

    def scan_directories(self, dirs: List[str], exts: Set[str], 
                        progress_callback: Optional[Callable[[str], None]] = None,
                        stop_check: Optional[Callable[[], bool]] = None) -> List[str]:
        self.paths = []
        for i, d in enumerate(dirs, 1):
            if stop_check and stop_check():
                break

            if progress_callback:
                progress_callback(f"Scanning directory {i}/{len(dirs)}: {d}")
            try:
                for name in os.listdir(d):
                    p = os.path.join(d, name)
                    if not os.path.isfile(p):
                        continue
                    ext = os.path.splitext(name)[1].lstrip(".").lower()
                    if ext in exts:
                        self.paths.append(p)
            except Exception:
                continue
        return self.paths

    def build_plan(self, progress_callback: Optional[Callable[[int, int, str], None]] = None,
                  stop_check: Optional[Callable[[], bool]] = None) -> None:
        self.plan = []
        self.missing_title_count = 0
        self.already_ok_count = 0

        total = len(self.paths)
        for idx, p in enumerate(self.paths, 1):
            if stop_check and stop_check():
                break

            if progress_callback:
                progress_callback(idx, total, p)
            
            ext = os.path.splitext(p)[1].lstrip(".").lower()
            raw_title = run_ffprobe_title(p)
            if not raw_title:
                self.missing_title_count += 1
                continue

            display = clean_title_display(raw_title)
            desired_name = safe_basename_from_title(display, ext)
            dir_path = os.path.dirname(p)
            desired_path = os.path.join(dir_path, desired_name)

            if os.path.abspath(p) == os.path.abspath(desired_path):
                self.already_ok_count += 1
                continue

            desired_path = make_unique_path_with_dup(dir_path, desired_name)
            self.plan.append((p, desired_path))

    def get_stats(self) -> Dict[str, int]:
        return {
            "scanned": len(self.paths),
            "will_rename": len(self.plan),
            "missing_title": self.missing_title_count,
            "already_ok": self.already_ok_count
        }

    def execute_rename(self, dry_run: bool = False, 
                      progress_callback: Optional[Callable[[int, int, str], None]] = None,
                      stop_check: Optional[Callable[[], bool]] = None) -> Tuple[int, int]:
        renamed = 0
        errors = 0
        total = len(self.plan)

        for idx, (src, dst) in enumerate(self.plan, 1):
            if stop_check and stop_check():
                break

            if progress_callback:
                progress_callback(idx, total, src)
            
            try:
                if not dry_run:
                    os.rename(src, dst)
                renamed += 1
            except Exception:
                errors += 1
        
        return renamed, errors
