from PyQt5.QtCore import QThread, pyqtSignal
import os
import subprocess
import shutil

class BitrateMoverWorker(QThread):
    progress_updated = pyqtSignal(int)
    log_message = pyqtSignal(str)
    finished = pyqtSignal()
    
    def __init__(self, source_folder, dest_folder):
        super().__init__()
        self.source_folder = source_folder
        self.dest_folder = dest_folder
        self._is_running = True
    
    def run(self):
        self.log_message.emit(f"Starting bitrate analysis in {self.source_folder}")
        
        # Scan for audio files
        audio_files = self.scan_audio_files(self.source_folder)
        if not audio_files:
            self.log_message.emit("No audio files found")
            self.finished.emit()
            return
        
        total_files = len(audio_files)
        processed_files = 0
        
        for file_path in audio_files:
            if not self._is_running:
                break
            
            try:
                # Get bitrate information using ffprobe
                bitrate = self.get_bitrate(file_path)
                if bitrate:
                    self.log_message.emit(f"File: {os.path.basename(file_path)}, Bitrate: {bitrate}kbps")
                    # Implement your bitrate-based moving logic here
                
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
    
    def get_bitrate(self, file_path):
        try:
            cmd = ['ffprobe', '-v', 'error', '-select_streams', 'a:0',
                   '-show_entries', 'stream=bit_rate', '-of', 'default=noprint_wrappers=1:nokey=1',
                   file_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.stdout.strip():
                return int(result.stdout.strip()) // 1000  # Convert to kbps
        except Exception as e:
            self.log_message.emit(f"Error getting bitrate: {str(e)}")
        return None
    
    def stop(self):
        self._is_running = False 