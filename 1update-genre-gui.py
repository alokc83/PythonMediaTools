#!/usr/bin/env python3
import os
import sys
import re
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QProgressBar, QLabel
)
from PyQt5.QtCore import QThread, pyqtSignal

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

def unescape_path(path):
    # Remove backslashes used for escaping (e.g., spaces, parentheses)
    return re.sub(r'\\(.)', r'\1', path)

class GenreUpdaterWorker(QThread):
    progressChanged = pyqtSignal(int)
    consoleMessage = pyqtSignal(str)
    finished = pyqtSignal()
    
    def __init__(self, folder, override_genre=None, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.override_genre = override_genre
        self._isRunning = True
        
    def run(self):
        self.consoleMessage.emit(f"Scanning folder: {self.folder}")
        files = []
        for root, dirs, f_list in os.walk(self.folder):
            for file in f_list:
                if file.lower().endswith(('.mp3', '.m4a')):
                    files.append(os.path.join(root, file))
        total = len(files)
        self.consoleMessage.emit(f"Found {total} audio files.")
        for i, file_path in enumerate(files):
            if not self._isRunning:
                self.consoleMessage.emit("Process cancelled.")
                break
            # Determine genre: use override if provided; otherwise use immediate parent folder name.
            genre = self.override_genre.strip() if self.override_genre.strip() else os.path.basename(os.path.dirname(file_path))
            try:
                ext = os.path.splitext(file_path)[1].lower()
                if ext == ".mp3":
                    self.update_mp3_genre(file_path, genre)
                elif ext == ".m4a":
                    self.update_m4a_genre(file_path, genre)
                self.consoleMessage.emit(f"Updated '{file_path}' with genre: {genre}")
            except Exception as e:
                self.consoleMessage.emit(f"Error updating '{file_path}': {str(e)}")
            progress = int(((i+1) / total) * 100)
            self.progressChanged.emit(progress)
        self.finished.emit()
        
    def update_mp3_genre(self, file_path, genre):
        try:
            audio = EasyID3(file_path)
        except Exception:
            audio = EasyID3()  # Create new tag if none exists
        audio["genre"] = genre
        audio.save(file_path)
    
    def update_m4a_genre(self, file_path, genre):
        try:
            audio = MP4(file_path)
        except Exception as e:
            raise Exception(f"Error reading M4A file: {str(e)}")
        # In MP4/M4A files, genre is stored under the key '©gen'
        audio["\xa9gen"] = [genre]
        audio.save(file_path)
    
    def stop(self):
        self._isRunning = False

class GenreUpdaterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audiobook Genre Updater")
        self.resize(600, 400)
        self.worker = None
        self.initUI()
    
    def initUI(self):
        layout = QVBoxLayout()
        
        # Folder selection
        folder_layout = QHBoxLayout()
        folder_label = QLabel("Folder:")
        self.folder_edit = QLineEdit()
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_folder)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(browse_button)
        layout.addLayout(folder_layout)
        
        # Genre override
        genre_layout = QHBoxLayout()
        genre_label = QLabel("Override Genre (optional):")
        self.genre_edit = QLineEdit()
        genre_layout.addWidget(genre_label)
        genre_layout.addWidget(self.genre_edit)
        layout.addLayout(genre_layout)
        
        # Start/Cancel button
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.toggle_process)
        layout.addWidget(self.start_button)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # Console output (text area)
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)
        
        self.setLayout(layout)
    
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", "")
        if folder:
            self.folder_edit.setText(folder)
    
    def toggle_process(self):
        if self.worker is None:
            folder = self.folder_edit.text().strip()
            folder = unescape_path(folder)
            if not folder or not os.path.isdir(folder):
                self.log("Invalid folder!")
                return
            override_genre = self.genre_edit.text().strip()
            self.worker = GenreUpdaterWorker(folder, override_genre)
            self.worker.progressChanged.connect(self.progress_bar.setValue)
            self.worker.consoleMessage.connect(self.log)
            self.worker.finished.connect(self.process_finished)
            self.start_button.setText("Cancel")
            self.worker.start()
        else:
            self.log("Cancelling process...")
            self.worker.stop()
            self.start_button.setText("Start")
            self.worker = None
    
    def process_finished(self):
        self.log("Processing complete.")
        self.start_button.setText("Start")
        self.worker = None
    
    def log(self, message):
        self.console.append(message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GenreUpdaterApp()
    window.show()
    sys.exit(app.exec_())
