
import os
from typing import List, Dict, Set, Optional, Callable, Tuple

class FormatPruner:
    def __init__(self):
        self.to_delete: List[str] = []
        self.stats = {
            "dirs_scanned": 0,
            "mp3_seen": 0,
            "protect_seen": 0,
            "candidates": 0
        }

    def scan_directory(self, root_abs: str, 
                      progress_callback: Optional[Callable[[str], None]] = None,
                      stop_check: Optional[Callable[[], bool]] = None) -> List[str]:
        self.to_delete = []
        self.stats = {
            "dirs_scanned": 0,
            "mp3_seen": 0,
            "protect_seen": 0,
            "candidates": 0
        }
        
        for dirpath, _, filenames in os.walk(root_abs):
            if stop_check and stop_check():
                break

            self.stats["dirs_scanned"] += 1
            
            present: Dict[str, Set[str]] = {}
            for name in filenames:
                ext = os.path.splitext(name)[1].lstrip(".").lower()
                if ext not in {"mp3", "m4a", "m4b"}:
                    continue
                base = os.path.splitext(name)[0].lower()
                present.setdefault(base, set()).add(ext)

            for base, exts in present.items():
                if "mp3" in exts:
                    self.stats["mp3_seen"] += 1
                if "m4a" in exts or "m4b" in exts:
                    self.stats["protect_seen"] += 1

                if "mp3" in exts and ("m4a" in exts or "m4b" in exts):
                    pass 
            
            # Re-iterating to find valid files based on what we found presnet
            for name in filenames:
                 ext = os.path.splitext(name)[1].lstrip(".").lower()
                 if ext == "mp3":
                     base = os.path.splitext(name)[0].lower()
                     if base in present:
                         exts = present[base]
                         if "m4a" in exts or "m4b" in exts:
                             self.to_delete.append(os.path.join(dirpath, name))

            if progress_callback:
                progress_callback(f"Scanning dirs: {self.stats['dirs_scanned']}, Candidates: {len(self.to_delete)}")

        self.stats["candidates"] = len(self.to_delete)
        return self.to_delete

    def execute_prune(self, dry_run: bool = False, 
                     progress_callback: Optional[Callable[[int, int, str], None]] = None,
                     stop_check: Optional[Callable[[], bool]] = None) -> Tuple[int, int]:
        deleted = 0
        errors = 0
        total = len(self.to_delete)
        
        for idx, p in enumerate(self.to_delete, 1):
            if stop_check and stop_check():
                break

            if progress_callback:
                progress_callback(idx, total, p)
            
            try:
                if not dry_run:
                    os.remove(p)
                deleted += 1
            except Exception:
                errors += 1
        return deleted, errors
