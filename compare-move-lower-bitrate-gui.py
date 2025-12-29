#!/usr/bin/env python3
import os
import sys
import re
import shutil
import urllib.parse
import concurrent.futures

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QFileDialog, QTextEdit, QProgressBar, QLabel, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import QThread, pyqtSignal, QObject

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

# --- Helper Functions ---

def unescape_path(p):
    """Remove backslashes used for escaping characters (e.g., spaces, parentheses)."""
    return re.sub(r'\\(.)', r'\1', p)

def get_audio_metadata(filepath):
    """
    Reads the album metadata and bitrate for an audio file.
    For MP3, album is read from the TALB tag.
    For M4A, album is read from the '©alb' atom.
    Returns a tuple (album, bitrate) where bitrate is in bits per second.
    If album metadata is not found, returns ("", bitrate).
    """
    album = ""
    bitrate = 0
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".mp3":
            try:
                audio = EasyID3(filepath)
            except Exception:
                audio = EasyID3()  # Create new tag if none exists
            tag = audio.get("album", [None])[0]
            if tag:
                album = tag.strip()
            audio_full = MP3(filepath)
            if hasattr(audio_full.info, 'bitrate'):
                bitrate = audio_full.info.bitrate
        elif ext == ".m4a":
            audio = MP4(filepath)
            album_list = audio.tags.get("\xa9alb")
            if album_list:
                album = album_list[0].strip()
            if hasattr(audio.info, 'bitrate'):
                bitrate = audio.info.bitrate
        else:
            from mutagen import File
            audio = File(filepath)
            if audio and audio.tags:
                album = str(audio.tags.get("TALB", "")).strip()
            if hasattr(audio, 'info') and hasattr(audio.info, 'bitrate'):
                bitrate = audio.info.bitrate
    except Exception as e:
        print(f"Error reading metadata from {filepath}: {e}")
    return album, bitrate

def scan_folder(folder, progress_callback, total_files, counter_obj):
    """
    Recursively scans the given folder for MP3 and M4A files.
    Returns a dictionary mapping each album to a list of tuples: (filepath, bitrate).
    Files that do not have album metadata are skipped.
    After processing each file, progress_callback is called with progress (0-50%).
    """
    album_groups = {}
    for root, dirs, files in os.walk(folder):
        # Log folder being scanned.
        print(f"Scanning folder: {root}")
        for filename in files:
            if filename.lower().endswith(('.mp3', '.m4a')):
                filepath = os.path.join(root, filename)
                # Skip files in any "toDelete" folder.
                if "toDelete" in root:
                    continue
                album, bitrate = get_audio_metadata(filepath)
                if album:
                    album_groups.setdefault(album, []).append((filepath, bitrate))
                counter_obj['scanned'] += 1
                progress = int((counter_obj['scanned'] / total_files) * 50)
                progress_callback(progress)
    return album_groups

def merge_albums(album_groups):
    """
    For each album with multiple files, keep only the file with the highest bitrate.
    Returns a dictionary mapping album to (filepath, bitrate).
    """
    selected = {}
    for album, files in album_groups.items():
        if len(files) == 1:
            selected[album] = files[0]
        else:
            best = max(files, key=lambda x: x[1])
            selected[album] = best
    return selected

def move_lower_bitrate_files(album_groups, selected, to_delete_folder):
    """
    For each album with multiple files, move files not selected (i.e. lower bitrate) 
    into the 'toDelete' folder.
    """
    for album, files in album_groups.items():
        if len(files) > 1:
            best_filepath, best_bitrate = selected[album]
            for filepath, bitrate in files:
                if filepath != best_filepath:
                    print(f"Moving '{filepath}' (bitrate: {bitrate//1000} kbps) to {to_delete_folder}")
                    try:
                        shutil.move(filepath, to_delete_folder)
                    except Exception as e:
                        print(f"Error moving file '{filepath}': {e}")

def process_source_folders(source_folders, progress_callback, console_callback):
    """
    Scans all source folders concurrently for MP3/M4A files.
    Returns a merged dictionary mapping each unique album to (filepath, bitrate)
    (keeping the file with the highest bitrate among duplicates).
    Progress is updated from 0 to 50% based on total files scanned.
    """
    total_files = 0
    for folder in source_folders:
        for root, dirs, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(('.mp3', '.m4a')):
                    total_files += 1
    console_callback(f"Total files to scan: {total_files}")
    counter_obj = {'scanned': 0}
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_folder = {executor.submit(scan_folder, folder, progress_callback, total_files, counter_obj): folder for folder in source_folders}
        completed = 0
        for future in concurrent.futures.as_completed(future_to_folder):
            folder = future_to_folder[future]
            try:
                folder_dict = future.result()
                results.append(folder_dict)
                console_callback(f"Finished scanning folder: {folder}")
            except Exception as e:
                console_callback(f"Error scanning folder {folder}: {e}")
            completed += 1
    # Merge dictionaries.
    merged = {}
    for d in results:
        for album, files in d.items():
            if album in merged:
                merged[album].extend(files)
            else:
                merged[album] = files
    merged_single = merge_albums(merged)
    return merged_single

def copy_files_to_destination(files_by_album, dest_folder, progress_callback, console_callback):
    """
    Copies each selected file (highest bitrate per album) into the destination folder.
    Updates progress from 0 to 100 (copying phase).
    """
    total = len(files_by_album)
    copied = 0
    for i, (album, (filepath, bitrate)) in enumerate(files_by_album.items()):
        dest_file = os.path.join(dest_folder, os.path.basename(filepath))
        try:
            shutil.copy2(filepath, dest_file)
            console_callback(f"Copied '{filepath}' ({bitrate//1000} kbps) to '{dest_folder}'")
            copied += 1
        except Exception as e:
            console_callback(f"Error copying '{filepath}': {e}")
        progress = int(((i+1)/total) * 100)
        progress_callback(progress)
    return copied

# --- Worker Thread ---
class MassCompareWorker(QThread):
    progressChanged = pyqtSignal(int)
    consoleMessage = pyqtSignal(str)
    finished = pyqtSignal()
    
    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.folder = folder
        self._isRunning = True
    
    def run(self):
        self.consoleMessage.emit("Starting scanning phase...")
        # Create the 'toDelete' folder if it doesn't exist.
        to_delete_folder = os.path.join(self.folder, "toDelete")
        os.makedirs(to_delete_folder, exist_ok=True)
        
        # Scan source folders (here, a list with one folder).
        files_by_album = process_source_folders([self.folder], self.progressChanged.emit, self.consoleMessage.emit)
        self.consoleMessage.emit(f"Scanned folder; found {len(files_by_album)} album(s).")
        # Reset progress bar for move/copy phase.
        self.progressChanged.emit(0)
        
        # Rescan the folder (recursively) to get complete album groups (for moving duplicates).
        album_groups = {}
        for root, dirs, files in os.walk(self.folder):
            for file in files:
                if file.lower().endswith(('.mp3', '.m4a')) and "toDelete" not in root:
                    filepath = os.path.join(root, file)
                    album, bitrate = get_audio_metadata(filepath)
                    if album:
                        album_groups.setdefault(album, []).append((filepath, bitrate))
        move_lower_bitrate_files(album_groups, files_by_album, to_delete_folder)
        self.consoleMessage.emit("Moved lower-bitrate files to 'toDelete' folder.")
        
        # Copy selected files to a destination folder "Selected" inside the source folder.
        dest_folder = os.path.join(self.folder, "Selected")
        os.makedirs(dest_folder, exist_ok=True)
        copied = copy_files_to_destination(files_by_album, dest_folder, self.progressChanged.emit, self.consoleMessage.emit)
        self.consoleMessage.emit(f"Copied {copied} files to destination folder: {dest_folder}")
        self.progressChanged.emit(100)
        self.finished.emit()
    
    def stop(self):
        self._isRunning = False

# --- Main PyQt Application ---
class MassCompareApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mass Compare & Copy")
        self.resize(700, 500)
        self.worker = None
        self.initUI()
    
    def initUI(self):
        layout = QVBoxLayout()
        
        # Folder selection
        folder_layout = QHBoxLayout()
        folder_label = QLabel("Source Folder:")
        self.folder_edit = QLineEdit()
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_folder)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(browse_button)
        layout.addLayout(folder_layout)
        
        # Start/Cancel button
        self.start_button = QPushButton("Start Process")
        self.start_button.clicked.connect(self.toggle_process)
        layout.addWidget(self.start_button)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # Console output
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)
        
        self.setLayout(layout)
    
    def browse_folder(self):
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder", "")
        if folder:
            self.folder_edit.setText(folder)
    
    def toggle_process(self):
        if self.worker is None:
            folder = self.folder_edit.text().strip()
            folder = unescape_path(folder)
            if not os.path.isdir(folder):
                self.log("Error: Folder is invalid.")
                return
            self.worker = MassCompareWorker(folder)
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
    window = MassCompareApp()
    # Redirect STDOUT/STDERR to the GUI console:
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
