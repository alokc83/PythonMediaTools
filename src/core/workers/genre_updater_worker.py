from PyQt5.QtCore import QThread, pyqtSignal
import os
import time
import shutil
import requests
from mutagen import File as MutagenFile

class GenreUpdaterWorker(QThread):
    progress_updated = pyqtSignal(int)
    log_message = pyqtSignal(str)
    api_count_signal = pyqtSignal(int)
    finished = pyqtSignal()
    
    def __init__(self, folder, api_key, force_cover=False):
        super().__init__()
        self.folder = folder
        self.api_key = api_key
        self.force_cover = force_cover
        self._is_running = True
        self._paused = False
        self._cancelled = False
        self.api_count = 0
    
    def run(self):
        self.log_message.emit(f"Starting genre update in {self.folder}")
        
        # Scan for audio files
        files = self.scan_audio_files(self.folder)
        if not files:
            self.log_message.emit("No audio files found")
            self.finished.emit()
            return
        
        total_files = len(files)
        processed_files = 0
        self.progress_updated.emit(0)
        
        for file_path in files:
            if self._cancelled:
                break
                
            while self._paused:
                time.sleep(0.1)
                if self._cancelled:
                    break
            
            self.log_message.emit(f"Processing: {os.path.basename(file_path)}")
            
            try:
                # Process file and update genre
                # This is where you'd implement the actual genre updating logic
                # using the Google API and file metadata updates
                
                # Simulate API call and processing
                time.sleep(0.5)
                self.api_count += 1
                self.api_count_signal.emit(self.api_count)
                
                processed_files += 1
                progress = int((processed_files / total_files) * 100)
                self.progress_updated.emit(progress)
                
            except Exception as e:
                self.log_message.emit(f"Error processing {file_path}: {str(e)}")
        
        self.finished.emit()
    
    def scan_audio_files(self, folder):
        audio_files = []
        for root, _, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(('.mp3', '.m4a')):
                    audio_files.append(os.path.join(root, file))
        return audio_files
    
    def pause(self):
        self._paused = True
    
    def resume(self):
        self._paused = False
    
    def cancel(self):
        self._cancelled = True
        self._paused = False 