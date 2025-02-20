from PyQt5.QtCore import QThread, pyqtSignal
import os

class ProcessingWorker(QThread):
    progress_updated = pyqtSignal(int)
    log_message = pyqtSignal(str)
    finished = pyqtSignal()
    
    def __init__(self, source_folder):
        super().__init__()
        self.source_folder = source_folder
        self._is_running = True
    
    def run(self):
        self.log_message.emit(f"Starting processing in {self.source_folder}")
        
        # Add your processing logic here
        # This is just a placeholder example
        for i in range(100):
            if not self._is_running:
                break
            self.progress_updated.emit(i + 1)
            self.msleep(100)  # Simulate work
        
        self.finished.emit()
    
    def stop(self):
        self._is_running = False 