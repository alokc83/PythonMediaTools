
import os
import shutil
from typing import List, Optional, Callable, Set, Tuple

class FileToDir:
    def __init__(self):
        self.files: List[str] = []

    def scan_directory(self, target_dir: str, exts: Set[str]) -> List[str]:
        self.files = []
        try:
            for name in os.listdir(target_dir):
                p = os.path.join(target_dir, name)
                if not os.path.isfile(p):
                    continue
                ext = os.path.splitext(name)[1].lstrip(".").lower()
                if ext in exts:
                    self.files.append(p)
        except Exception:
            pass
        self.files.sort()
        return self.files

    def execute_organize(self, target_dir: str, dry_run: bool = False, 
                        progress_callback: Optional[Callable[[int, int, str], None]] = None,
                        stop_check: Optional[Callable[[], bool]] = None) -> Tuple[int, int, int, int]:
        # returns moved, skipped_not_dir, skipped_dest_exists, errors
        moved = 0
        skipped_exists_not_dir = 0
        skipped_dest_exists = 0
        errors = 0
        total = len(self.files)

        for idx, src in enumerate(self.files, 1):
            if stop_check and stop_check():
                break

            if progress_callback:
                progress_callback(idx, total, src)
            
            name = os.path.basename(src)
            base = os.path.splitext(name)[0]
            folder = os.path.join(target_dir, base)

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
                
        return moved, skipped_exists_not_dir, skipped_dest_exists, errors
