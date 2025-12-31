
import os
import shutil
import hashlib
from typing import List, Dict, Tuple, Optional, Callable, Set
from .common import (
    AudioFile,
    choose_keep,
    make_unique_path_with_dup,
    safe_basename_from_title,
    run_ffprobe_title,
    clean_title_display,
    scan_for_audio_files
)

class DuplicateMethod:
    TITLE = "title"
    HASH = "hash"
    FILENAME = "filename"

class DuplicatesFinder:
    def __init__(self):
        self.groups: Dict[str, List[AudioFile]] = {}
        self.keep_plan: List[Tuple[str, AudioFile, List[AudioFile]]] = []
        self.current_method = DuplicateMethod.TITLE
    
    def calculate_file_hash(self, path: str, chunk_size=8192) -> str:
        """Calculate MD5 hash of a file."""
        md5 = hashlib.md5()
        try:
            with open(path, 'rb') as f:
                while chunk := f.read(chunk_size):
                    md5.update(chunk)
            return md5.hexdigest()
        except Exception:
            return ""

    def build_groups(self, all_paths: List[str], method: str, 
                    progress_callback: Optional[Callable[[int, int, str], None]],
                    stop_check: Optional[Callable[[], bool]] = None) -> Dict[str, List[AudioFile]]:
        """
        Group files based on the selected method.
        """
        groups: Dict[str, List[AudioFile]] = {}
        total = len(all_paths)
        
        for idx, p in enumerate(all_paths):
            if stop_check and stop_check():
                break

            if progress_callback:
                progress_callback(idx, total, f"Analyzing: {os.path.basename(p)}")
            
            key = ""
            # Basic info
            ext = os.path.splitext(p)[1].lstrip(".").lower()
            size = os.path.getsize(p)
            audio_f = AudioFile(path=p, filename=os.path.basename(p), size=size, ext=ext)

            if method == DuplicateMethod.TITLE:
                # Metadata Title
                raw_title = run_ffprobe_title(p)
                if raw_title:
                    audio_f.title_tag = raw_title
                    audio_f.title_display = clean_title_display(raw_title)
                    key = audio_f.title_display.lower()
                else:
                    # Skip files with no title metadata in Title mode
                    continue

            elif method == DuplicateMethod.HASH:
                # Content Hash
                h = self.calculate_file_hash(p)
                if h:
                    key = h
                    audio_f.title_display = f"Hash: {h[:8]}..." 
                else:
                    continue

            elif method == DuplicateMethod.FILENAME:
                # Filename (case-insensitive)
                key = audio_f.filename.lower()
                audio_f.title_display = audio_f.filename

            if key:
                if key not in groups:
                    groups[key] = []
                groups[key].append(audio_f)
        
        # Filter groups with only 1 item (no duplicates)
        return {k: v for k, v in groups.items() if len(v) > 1}

    def scan_and_get_groups(self, input_dirs: List[str], method: str = DuplicateMethod.TITLE, 
                           progress_callback: Optional[Callable[[int, int, str], None]] = None,
                           stop_check: Optional[Callable[[], bool]] = None) -> Dict[str, List[AudioFile]]:
        self.current_method = method
        all_paths = []
        for d in input_dirs:
            if stop_check and stop_check():
                break
            _, paths = scan_for_audio_files(d)
            all_paths.extend(paths)
        
        self.groups = self.build_groups(all_paths, method, progress_callback, stop_check)
        return self.groups

    def auto_plan_keep(self) -> List[Tuple[str, AudioFile, List[AudioFile]]]:
        """
        Automatically decide which file to keep in each group.
        Returns a list of tuples: (group_key, keep_file, move_files)
        """
        files_to_move = []
        
        # Sort groups by key for stable order
        sorted_keys = sorted(self.groups.keys())
        
        for key in sorted_keys:
            files = self.groups[key]
            # Use common helper to choose 'best' file to keep
            keep_file, move_subset = choose_keep(files)
            files_to_move.append((key, keep_file, move_subset))
            
        self.keep_plan = files_to_move
        return self.keep_plan

    def execute_move(self, dest_dir: str, dry_run: bool = False, 
                    progress_callback: Optional[Callable[[int, int, str], None]] = None,
                    stop_check: Optional[Callable[[], bool]] = None) -> Tuple[int, int]:
        count = 0
        errors = 0
        total_groups = len(self.keep_plan)
        
        if not os.path.exists(dest_dir) and not dry_run:
            os.makedirs(dest_dir)
            
        for idx, (key, keep, move_list) in enumerate(self.keep_plan):
            if stop_check and stop_check():
                break
                
            if progress_callback:
                progress_callback(idx, total_groups, f"Processing group: {key}")
                
            for f in move_list:
                try:
                    target_name = make_unique_path_with_dup(dest_dir, f.filename)
                    if not dry_run:
                        shutil.move(f.path, target_name)
                    count += 1
                except Exception as e:
                    print(f"Error moving {f.path}: {e}")
                    errors += 1
                    
        return count, errors
