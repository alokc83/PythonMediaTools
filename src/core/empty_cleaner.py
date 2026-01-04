import os
import shutil
import logging

class JunkCleaner:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def scan_directory(self, root_path, junk_extensions):
        """
        Recursively scans a directory to identify files and folders to delete.
        
        Args:
            root_path (str): The root directory to start scanning.
            junk_extensions (set): A set of lowercase file extensions to consider as junk (e.g., {'.txt', '.nfo'}).
                                   Can also include full filenames like 'thumbs.db'.
        
        Returns:
            list: A list of operations. Each operation is a tuple ('type', 'path').
                  Types: 'file', 'dir'.
                  Order: Ordered correctly for execution (files first, then leaf folders, then parent folders).
        """
        operations = []
        self._scan_recursive(root_path, junk_extensions, operations)
        return operations

    def _scan_recursive(self, current_dir, junk_extensions, operations):
        """
        Helper method for recursive scanning.
        Returns True if the directory becomes empty (and is thus marked for deletion).
        """
        try:
            # Get list of entries, filtering out basic OS junk if necessary at scan time, 
            # but usually we rely on junk_extensions for explicit deletion.
            entries = os.listdir(current_dir)
        except OSError as e:
            self.logger.error(f"Error accessing directory {current_dir}: {e}")
            return False # Conservative: assume keeping it if we can't access it

        files = []
        subdirs = []
        for entry in entries:
            full_path = os.path.join(current_dir, entry)
            if os.path.isdir(full_path):
                subdirs.append(entry)
            else:
                files.append(entry)

        # 1. Recursively process subdirectories (Bottom-Up)
        kept_subdirs_count = 0
        for sd in subdirs:
            sd_path = os.path.join(current_dir, sd)
            # If child is fully cleaned/empty, it returns True
            is_child_empty = self._scan_recursive(sd_path, junk_extensions, operations)
            if not is_child_empty:
                kept_subdirs_count += 1

        # 2. Process Files in current directory
        kept_files_count = 0
        
        # Audio Safeguard: Check if this directory contains any audio files
        audio_extensions = {'.mp3', '.m4a', '.m4b', '.aac', '.flac', '.ogg', '.wav', '.opus', '.alac', '.aiff', '.wma'}
        has_audio = any(f.lower().endswith(tuple(audio_extensions)) for f in files)
        
        for f in files:
            name_lower = f.lower()
            _, ext = os.path.splitext(name_lower)
            
            # Check if extension match or exact filename match (for thumbs.db)
            is_junk = ext in junk_extensions or name_lower in junk_extensions
            
            if is_junk:
                if has_audio:
                    # SAFETY: If folder has audio, DO NOT delete junk (preserve metadata/artwork)
                    print(f"Skipping junk deletion in '{current_dir}' due to presence of audio files.")
                    kept_files_count += 1
                else:
                    operations.append(('file', os.path.join(current_dir, f)))
            else:
                kept_files_count += 1

        # 3. Process Current Directory
        # If no subdirectories remain AND no files remain, this directory is effectively empty.
        # But we don't delete the ROOT directory itself, usually? 
        # The user tool is "Empty Folder Cleaner". If the root becomes empty, maybe we should delete it?
        # Typically "Empty Folder Cleaner" cleans hierarchy.
        # Let's mark it. The UI can decide to filter out the root path if desired.
        
        if kept_subdirs_count == 0 and kept_files_count == 0:
            operations.append(('dir', current_dir))
            return True # It is now empty/deleted
        else:
            return False # It remains

    def delete_item(self, op_type, path):
        """
        Executes a single deletion operation.
        """
        try:
            if op_type == 'file':
                os.remove(path)
                return True
            elif op_type == 'dir':
                os.rmdir(path) # Use rmdir for safety (only deletes if empty)
                return True
        except Exception as e:
            self.logger.error(f"Failed to delete {path}: {e}")
            return False

    def execute_operations(self, operations, progress_callback=None):
        """
        Executes a list of operations.
        """
        total = len(operations)
        success_count = 0
        
        for idx, (op_type, path) in enumerate(operations):
            if self.delete_item(op_type, path):
                success_count += 1
            
            if progress_callback:
                progress_callback(idx + 1, total)
                
        return success_count, total
