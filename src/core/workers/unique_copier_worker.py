from PyQt5.QtCore import QThread, pyqtSignal
import os
import shutil

class UniqueCopierWorker(QThread):
    progress_updated = pyqtSignal(int)
    log_message = pyqtSignal(str)
    finished = pyqtSignal()
    
    def __init__(self, dest_folder, source_folders):
        super().__init__()
        self.dest_folder = dest_folder
        self.source_folders = source_folders
        self._is_running = True
    
    def run(self):
        self.log_message.emit("Starting unique file copy process...")
        
        # Scan all source folders
        all_files = {}  # path -> size mapping
        for folder in self.source_folders:
            self.scan_folder(folder, all_files)
        
        if not all_files:
            self.log_message.emit("No files found in source folders")
            self.finished.emit()
            return
        
        # Process files
        total_files = len(all_files)
        processed = 0
        
        for file_path, size in all_files.items():
            if not self._is_running:
                break
            
            try:
                dest_path = os.path.join(self.dest_folder, os.path.basename(file_path))
                if not os.path.exists(dest_path):
                    shutil.copy2(file_path, dest_path)
                    self.log_message.emit(f"Copied: {os.path.basename(file_path)}")
                else:
                    self.log_message.emit(f"Skipped (exists): {os.path.basename(file_path)}")
                
                processed += 1
                progress = int((processed / total_files) * 100)
                self.progress_updated.emit(progress)
                
            except Exception as e:
                self.log_message.emit(f"Error processing {file_path}: {str(e)}")
        
        self.finished.emit()
    
    def scan_folder(self, folder, files_dict):
        for root, _, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(('.mp3', '.m4a')):
                    full_path = os.path.join(root, file)
                    try:
                        size = os.path.getsize(full_path)
                        files_dict[full_path] = size
                    except Exception as e:
                        self.log_message.emit(f"Error scanning {full_path}: {str(e)}")
    
    def stop(self):
        self._is_running = False 