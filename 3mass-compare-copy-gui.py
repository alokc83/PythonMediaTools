#!/usr/bin/env python3
import os
import sys
import re
import shutil
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QFileDialog, QTextEdit, QProgressBar, QLabel, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import QThread, pyqtSignal, QObject

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

# --- Helper Functions ---
def unescape_path(path):
    """Remove backslashes used for escaping characters."""
    return re.sub(r'\\(.)', r'\1', path)

def get_audio_metadata(file_path):
    """
    Extract title, genre, and bitrate from an MP3 or M4A file.
    For MP3:
      - Title: from "title" tag (fallback to "album" or file name)
      - Genre: from "genre"
      - Bitrate: from MP3.info.bitrate
    For M4A:
      - Title: from "\xa9nam" (fallback to "\xa9alb" or file name)
      - Genre: from "\xa9gen"
      - Bitrate: from MP4.info.bitrate
    """
    ext = os.path.splitext(file_path)[1].lower()
    title, genre, bitrate = None, None, 0
    if ext == ".mp3":
        try:
            audio = EasyID3(file_path)
            title = audio.get("title", [None])[0]
            if not title or title.strip() == "":
                title = audio.get("album", [None])[0]
            if not title:
                title = os.path.splitext(os.path.basename(file_path))[0]
            audio_full = MP3(file_path)
            bitrate = audio_full.info.bitrate
            genre = audio.get("genre", [None])[0]
        except Exception as e:
            print(f"Error reading MP3 metadata from '{file_path}': {e}")
    elif ext == ".m4a":
        try:
            audio = MP4(file_path)
            title = audio.get("\xa9nam", [None])[0]
            if not title or title.strip() == "":
                title = audio.get("\xa9alb", [None])[0]
            if not title:
                title = os.path.splitext(os.path.basename(file_path))[0]
            bitrate = audio.info.bitrate
            genres = audio.get("\xa9gen", [])
            if genres:
                genre = genres[0]
        except Exception as e:
            print(f"Error reading M4A metadata from '{file_path}': {e}")
    if title:
        title = title.strip()
    if genre:
        genre = genre.strip()
    return title, genre, bitrate

def scan_folder(folder):
    """
    Recursively scan a single folder for MP3 and M4A files.
    Returns a dictionary mapping each unique title to a tuple (file_path, genre, bitrate).
    In case of duplicates, the file with the highest bitrate is kept.
    """
    files_by_title = {}
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.lower().endswith(('.mp3', '.m4a')):
                full_path = os.path.join(root, file)
                title, genre, bitrate = get_audio_metadata(full_path)
                if not title:
                    continue
                if title in files_by_title:
                    if bitrate > files_by_title[title][2]:
                        files_by_title[title] = (full_path, genre, bitrate)
                else:
                    files_by_title[title] = (full_path, genre, bitrate)
    return files_by_title

def merge_dicts(dicts):
    """
    Merge multiple dictionaries mapping title -> (file_path, genre, bitrate).
    In case of duplicate titles, keep the one with the highest bitrate.
    """
    merged = {}
    for d in dicts:
        for title, meta in d.items():
            if title in merged:
                if meta[2] > merged[title][2]:
                    merged[title] = meta
            else:
                merged[title] = meta
    return merged

def process_source_folders(source_folders, progress_callback, console_callback):
    """
    Scan all source folders concurrently and return a merged dictionary mapping
    each unique title to (file_path, genre, bitrate).
    
    progress_callback is called with progress (0-50) based on folder completion.
    console_callback is used to log messages.
    """
    results = []
    total_folders = len(source_folders)
    console_callback(f"Scanning {total_folders} source folder(s)...")
    with ThreadPoolExecutor(max_workers=total_folders) as executor:
        future_to_folder = {executor.submit(scan_folder, folder): folder for folder in source_folders}
        completed = 0
        for future in as_completed(future_to_folder):
            folder = future_to_folder[future]
            try:
                folder_dict = future.result()
                results.append(folder_dict)
                console_callback(f"Finished scanning folder: {folder}")
            except Exception as e:
                console_callback(f"Error scanning folder {folder}: {e}")
            completed += 1
            progress = int((completed / total_folders) * 50)  # scanning phase = 0-50%
            progress_callback(progress)
    merged = merge_dicts(results)
    return merged

def copy_files_to_destination(files_by_title, dest_folder, progress_callback, console_callback):
    """
    Copy each selected file (highest bitrate per title) to the destination folder.
    Files are placed in a subfolder named by their genre (or "Unknown-Genre" if not available).
    progress_callback is called with progress (50-100%).
    """
    total = len(files_by_title)
    copied = 0
    for i, (title, (file_path, genre, bitrate)) in enumerate(files_by_title.items()):
        dest_subfolder = os.path.join(dest_folder, genre if genre and genre != "" else "Unknown-Genre")
        os.makedirs(dest_subfolder, exist_ok=True)
        dest_file = os.path.join(dest_subfolder, os.path.basename(file_path))
        try:
            shutil.copy2(file_path, dest_file)
            console_callback(f"Copied '{file_path}' ({bitrate/1000:.0f} kbps) to '{dest_subfolder}'")
            copied += 1
        except Exception as e:
            console_callback(f"Error copying '{file_path}': {e}")
        progress = 50 + int(((i + 1) / total) * 50)  # copying phase 50-100%
        progress_callback(progress)
    return copied

# --- Worker Thread ---
class UniqueFileCopier(QThread):
    progressChanged = pyqtSignal(int)
    consoleMessage = pyqtSignal(str)
    finished = pyqtSignal()
    
    def __init__(self, dest_folder, source_folders, parent=None):
        super().__init__(parent)
        self.dest_folder = dest_folder
        self.source_folders = source_folders
        self._isRunning = True
        
    def run(self):
        self.consoleMessage.emit("Starting scanning phase...")
        files_by_title = process_source_folders(self.source_folders, self.progressChanged.emit, self.consoleMessage.emit)
        self.consoleMessage.emit(f"Found {len(files_by_title)} unique title(s).")
        self.consoleMessage.emit("Starting copying phase...")
        copied = copy_files_to_destination(files_by_title, self.dest_folder, self.progressChanged.emit, self.consoleMessage.emit)
        self.consoleMessage.emit(f"Copied {copied} files to destination.")
        self.finished.emit()
    
    def stop(self):
        self._isRunning = False

# --- Main PyQt Application ---
class UniqueFileCopierApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unique Audio Copier")
        self.resize(700, 500)
        self.worker = None
        self.initUI()
    
    def initUI(self):
        layout = QVBoxLayout()
        
        # Destination folder selection
        dest_layout = QHBoxLayout()
        dest_label = QLabel("Destination Folder:")
        self.dest_edit = QLineEdit()
        dest_browse = QPushButton("Browse")
        dest_browse.clicked.connect(self.browse_dest)
        dest_layout.addWidget(dest_label)
        dest_layout.addWidget(self.dest_edit)
        dest_layout.addWidget(dest_browse)
        layout.addLayout(dest_layout)
        
        # Source folders list and add button
        src_layout = QHBoxLayout()
        src_label = QLabel("Source Folders:")
        self.src_list = QListWidget()
        add_src_btn = QPushButton("Add Source Folder")
        add_src_btn.clicked.connect(self.add_source_folder)
        src_layout.addWidget(src_label)
        src_layout.addWidget(self.src_list)
        src_layout.addWidget(add_src_btn)
        layout.addLayout(src_layout)
        
        # Optional Genre override (if provided, it may be used to force a specific genre folder)
        genre_layout = QHBoxLayout()
        genre_label = QLabel("Override Genre (optional):")
        self.genre_edit = QLineEdit()
        genre_layout.addWidget(genre_label)
        genre_layout.addWidget(self.genre_edit)
        layout.addLayout(genre_layout)
        
        # Start/Cancel button
        self.start_button = QPushButton("Start Process")
        self.start_button.clicked.connect(self.toggle_process)
        layout.addWidget(self.start_button)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # Console text area
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)
        
        self.setLayout(layout)
    
    def browse_dest(self):
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder", "")
        if folder:
            self.dest_edit.setText(folder)
    
    def add_source_folder(self):
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder", "")
        if folder:
            self.src_list.addItem(QListWidgetItem(folder))
    
    def toggle_process(self):
        if self.worker is None:
            dest_folder = self.dest_edit.text().strip()
            dest_folder = unescape_path(dest_folder)
            if not os.path.isdir(dest_folder):
                self.log("Error: Destination folder is invalid.")
                return
            self.source_folders = []
            for i in range(self.src_list.count()):
                folder = self.src_list.item(i).text().strip()
                folder = unescape_path(folder)
                if os.path.isdir(folder):
                    self.source_folders.append(folder)
                else:
                    self.log(f"Source folder invalid: {folder}")
            if not self.source_folders:
                self.log("No valid source folders provided.")
                return
            # Optionally, if a genre override is provided, you could use it in the worker.
            # In this example, our copying uses the file's metadata; you could modify that logic if desired.
            self.worker = UniqueFileCopier(dest_folder, self.source_folders)
            self.worker.progressChanged.connect(self.progress_bar.setValue)
            self.worker.consoleMessage.connect(self.log)
            self.worker.finished.connect(self.process_finished)
            self.start_button.setText("Cancel Process")
            self.worker.start()
        else:
            self.log("Cancelling process...")
            self.worker.stop()
            self.start_button.setText("Start Process")
            self.worker = None
    
    def process_finished(self):
        self.log("Processing complete.")
        self.start_button.setText("Start Process")
        self.worker = None
    
    def log(self, message):
        self.console.append(message)

if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = UniqueFileCopierApp()
    # Redirect STDOUT/STDERR to our console widget
    class EmittingStream(QObject):
        textWritten = pyqtSignal(str)
        def write(self, text):
            self.textWritten.emit(text)
        def flush(self):
            pass
    stdout_stream = EmittingStream()
    stdout_stream.textWritten.connect(window.log)
    sys.stdout = stdout_stream
    sys.stderr = stdout_stream
    window.show()
    sys.exit(app.exec_())
