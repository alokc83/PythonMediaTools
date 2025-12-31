
import os
import shutil
from typing import List, Optional, Callable, Dict, Set, Tuple
from .common import (
    run_ffprobe_title,
    clean_title_display,
    safe_basename_from_title,
    make_unique_path_with_dup
)

class FolderFlattener:
    def __init__(self):
        self.root_files: List[str] = []
        self.all_audio: List[str] = []
        self.to_move: List[str] = [] # subset of all_audio that are not in root
        self.cleanup_dirs_list: List[str] = []

    def scan_root_files(self, root_dir: str, exts: Set[str]) -> List[str]:
        self.root_files = []
        try:
            for name in os.listdir(root_dir):
                p = os.path.join(root_dir, name)
                if not os.path.isfile(p):
                    continue
                ext = os.path.splitext(name)[1].lstrip(".").lower()
                if ext in exts:
                    self.root_files.append(p)
        except Exception:
            pass
        return self.root_files

    def rename_root_files(self, root_dir: str, dry_run: bool = False, 
                         progress_callback: Optional[Callable[[int, int, str], None]] = None,
                         stop_check: Optional[Callable[[], bool]] = None) -> Tuple[int, int, int]:
        # returns renamed, skipped, errors
        renamed = 0
        skipped = 0
        errors = 0
        total = len(self.root_files)
        
        for idx, p in enumerate(self.root_files, 1):
            if stop_check and stop_check():
                break

            if progress_callback:
                progress_callback(idx, total, p)
            
            ext = os.path.splitext(p)[1].lstrip(".").lower()
            raw_title = run_ffprobe_title(p)
            if not raw_title:
                skipped += 1
                continue

            display = clean_title_display(raw_title)
            desired_name = safe_basename_from_title(display, ext)
            desired_path = os.path.join(root_dir, desired_name)

            if os.path.abspath(p) == os.path.abspath(desired_path):
                skipped += 1
                continue

            desired_path = make_unique_path_with_dup(root_dir, desired_name)
            
            try:
                if not dry_run:
                    os.rename(p, desired_path)
                renamed += 1
            except Exception:
                errors += 1
        
        return renamed, skipped, errors

    def scan_recursive(self, root_dir: str, exts: Set[str], 
                      progress_callback: Optional[Callable[[str], None]] = None,
                      stop_check: Optional[Callable[[], bool]] = None) -> List[str]:
        self.all_audio = []
        self.to_move = []
        dirs_scanned = 0
        
        for dirpath, _, filenames in os.walk(root_dir):
            if stop_check and stop_check():
                break

            dirs_scanned += 1
            if progress_callback:
                progress_callback(f"Scanning dirs: {dirs_scanned}, Found: {len(self.all_audio)}")
            
            for name in filenames:
                ext = os.path.splitext(name)[1].lstrip(".").lower()
                if ext in exts:
                    path = os.path.join(dirpath, name)
                    self.all_audio.append(path)
                    if os.path.abspath(dirpath) != os.path.abspath(root_dir):
                        self.to_move.append(path)
        
        return self.all_audio

    def execute_move_to_root(self, root_dir: str, dry_run: bool = False, 
                            progress_callback: Optional[Callable[[int, int, str], None]] = None,
                            stop_check: Optional[Callable[[], bool]] = None) -> Tuple[int, int]:
        moved = 0
        errors = 0
        total = len(self.to_move)

        for idx, src in enumerate(self.to_move, 1):
            if stop_check and stop_check():
                break

            if progress_callback:
                progress_callback(idx, total, src)

            ext = os.path.splitext(src)[1].lstrip(".").lower()
            raw_title = run_ffprobe_title(src)
            
            if raw_title:
                display = clean_title_display(raw_title)
                desired_name = safe_basename_from_title(display, ext)
            else:
                desired_name = os.path.basename(src)
            
            dest = make_unique_path_with_dup(root_dir, desired_name)
            
            try:
                if not dry_run:
                    shutil.move(src, dest)
                moved += 1
            except Exception:
                errors += 1
        
        return moved, errors

    def build_cleanup_list(self, root_dir: str, exts: Set[str]) -> List[str]:
        # Recalculate what audio files are left to decide which dirs to keep
        remaining_audio = set()
        for dirpath, _, filenames in os.walk(root_dir):
             for name in filenames:
                ext = os.path.splitext(name)[1].lstrip(".").lower()
                if ext in exts:
                    remaining_audio.add(os.path.join(dirpath, name))

        keep_dirs = set()
        for ap in remaining_audio:
            d = os.path.abspath(os.path.dirname(ap))
            while True:
                keep_dirs.add(d)
                if d == os.path.abspath(root_dir):
                    break
                nd = os.path.abspath(os.path.dirname(d))
                if nd == d:
                    break
                d = nd
        
        # Now find all subdirs and see if they are in keep_dirs
        self.cleanup_dirs_list = []
        for dirpath, dirnames, _ in os.walk(root_dir):
            for dn in dirnames:
                d_full = os.path.abspath(os.path.join(dirpath, dn))
                self.cleanup_dirs_list.append(d_full)
        
        # Sort by depth (deepest first) so we delete children before parents
        self.cleanup_dirs_list.sort(key=lambda p: p.count(os.sep), reverse=True)
        
        # Filter out those we must keep
        # Using a list comprehension to modify the list in place effectively
        # But here we just return a filtered list
        final_list = []
        root_abs = os.path.abspath(root_dir)
        
        # Need to handle protected dirs?
        # Assuming simple logic: if it's in keep_dirs, keep it.
        # Check against protected not implemented here fully but can be added if needed
        
        for d in self.cleanup_dirs_list:
            if d not in keep_dirs and d != root_abs:
                final_list.append(d)
        
        self.cleanup_dirs_list = final_list
        return final_list

    def execute_cleanup(self, dry_run: bool = False, 
                       progress_callback: Optional[Callable[[int, int, str], None]] = None,
                       stop_check: Optional[Callable[[], bool]] = None) -> Tuple[int, int]:
        deleted = 0
        errors = 0
        total = len(self.cleanup_dirs_list)
        
        for idx, d_abs in enumerate(self.cleanup_dirs_list, 1):
            if stop_check and stop_check():
                break

            if progress_callback:
                progress_callback(idx, total, d_abs)
            
            try:
                if not dry_run:
                    shutil.rmtree(d_abs)
                deleted += 1
            except Exception:
                errors += 1
        
        return deleted, errors
