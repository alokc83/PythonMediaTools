#!/usr/bin/env python3
import os
import time
import shutil
import requests
from mutagen import File as MutagenFile
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog,
    QVBoxLayout, QWidget, QHBoxLayout
)
from PyQt5.QtCore import QThread, pyqtSignal

# Custom exception for rate limiting
class RateLimitException(Exception):
    pass

# -------------------------------
# API and Metadata Functions
# -------------------------------

def get_book_categories_google(book_title, api_key="abc1234", delay=1):
    """
    Query the Google Books API for a given book title and return the categories
    from the first result that has them.
    Raises RateLimitException if a 429 status is encountered.
    """
    query = f"intitle:{book_title}"
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": query, "maxResults": 5, "key": api_key}

    # Delay to help avoid hitting rate limits.
    time.sleep(delay)
    response = requests.get(url, params=params)
    
    if response.status_code == 429:
        raise RateLimitException("Google Books API rate limit exceeded.")
    elif response.status_code == 403:
        # Sometimes a 403 may indicate a rate limit or permission issue.
        raise RateLimitException("Google Books API returned 403. Check your API key and permissions.")
    elif response.status_code != 200:
        return None

    data = response.json()
    items = data.get("items", [])
    if not items:
        return None

    # Look for the first result that has categories.
    for item in items:
        volume_info = item.get("volumeInfo", {})
        categories = volume_info.get("categories")
        if categories:
            return categories

    return None

def get_book_categories_openlibrary(book_title):
    """
    Query the OpenLibrary API for a given book title and return the subjects
    (as genre information) from the first result that has them.
    """
    url = "https://openlibrary.org/search.json"
    params = {"title": book_title, "limit": 5}
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return None
    data = response.json()
    docs = data.get("docs", [])
    if not docs:
        return None
    for doc in docs:
        subjects = doc.get("subject")
        if subjects:
            return subjects
    return None

def extract_title_from_file(file_path):
    """
    Extract a title from an audio file's metadata.
    Prefer the 'album' tag over the 'title' tag.
    """
    try:
        audio = MutagenFile(file_path, easy=True)
        if audio is None:
            return None
        album = audio.get("album", [])
        if album:
            return album[0]
        title = audio.get("title", [])
        if title:
            return title[0]
    except Exception as e:
        print(f"Error reading metadata from '{file_path}': {e}")
    return None

def write_genre_to_file(file_path, genres):
    """
    Write the provided genres (a list of strings) into the audio file's metadata under the 'genre' tag.
    """
    try:
        audio = MutagenFile(file_path, easy=True)
        if audio is None:
            return False
        audio["genre"] = genres
        audio.save()
        return True
    except Exception as e:
        print(f"Error updating genre for file '{file_path}': {e}")
        return False

def scan_audio_files(root_dir):
    """
    Recursively scan the given directory for MP3 and M4A files.
    """
    audio_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(('.mp3', '.m4a')):
                audio_files.append(os.path.join(dirpath, filename))
    return audio_files

# -------------------------------
# Worker Thread for Processing
# -------------------------------

class WorkerThread(QThread):
    api_count_signal = pyqtSignal(int)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, folder):
        super().__init__()
        self.folder = folder
        self.api_count = 0

    def run(self):
        files = scan_audio_files(self.folder)
        total_files = len(files)
        self.log_signal.emit(f"Found {total_files} audio files.")
        for file_path in files:
            self.log_signal.emit(f"\nProcessing file: {file_path}")
            title = extract_title_from_file(file_path)
            if not title:
                self.log_signal.emit("No title metadata found, skipping.")
                continue
            self.log_signal.emit(f"Extracted title: {title}")

            try:
                # Try Google Books API first.
                categories = get_book_categories_google(title)
                self.api_count += 1
                self.api_count_signal.emit(self.api_count)
            except RateLimitException as e:
                self.log_signal.emit(f"Rate limit error: {e}. Stopping processing.")
                self.finished_signal.emit()
                return

            if not categories:
                self.log_signal.emit("No categories from Google Books, trying OpenLibrary...")
                try:
                    categories = get_book_categories_openlibrary(title)
                    self.api_count += 1
                    self.api_count_signal.emit(self.api_count)
                except Exception as e:
                    self.log_signal.emit(f"Error calling OpenLibrary: {e}")
                    categories = None

            if categories:
                self.log_signal.emit("Categories found: " + ", ".join(categories))
                # Write the genre metadata back into the file.
                if write_genre_to_file(file_path, categories):
                    self.log_signal.emit("File metadata updated with genre.")
                else:
                    self.log_signal.emit("Failed to update file metadata.")
                # Move file to appropriate genre folder (using first genre).
                genre_folder = os.path.join(self.folder, categories[0])
                if not os.path.exists(genre_folder):
                    os.makedirs(genre_folder)
                    self.log_signal.emit(f"Created folder: {genre_folder}")
                try:
                    dest_file = os.path.join(genre_folder, os.path.basename(file_path))
                    shutil.move(file_path, dest_file)
                    self.log_signal.emit(f"Moved file to {dest_file}")
                except Exception as e:
                    self.log_signal.emit(f"Error moving file: {e}")
            else:
                self.log_signal.emit("No genre information found, skipping file.")
        self.finished_signal.emit()

# -------------------------------
# Main Window (GUI)
# -------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audiobook Genre Updater")
        self.setGeometry(100, 100, 600, 400)
        self.worker = None

        # UI Elements
        self.folder_label = QLabel("Selected Folder:")
        self.folder_line_edit = QLineEdit()
        self.browse_button = QPushButton("Browse")
        self.start_button = QPushButton("Start Processing")
        self.api_count_label = QLabel("API Calls: 0")
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)

        # Layout Setup
        layout = QVBoxLayout()
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.folder_line_edit)
        folder_layout.addWidget(self.browse_button)
        layout.addWidget(self.folder_label)
        layout.addLayout(folder_layout)
        layout.addWidget(self.start_button)
        layout.addWidget(self.api_count_label)
        layout.addWidget(self.log_text_edit)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Signal Connections
        self.browse_button.clicked.connect(self.browse_folder)
        self.start_button.clicked.connect(self.start_processing)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.folder_line_edit.setText(folder)

    def start_processing(self):
        folder = self.folder_line_edit.text()
        if not folder or not os.path.isdir(folder):
            self.log_text_edit.append("Please select a valid folder.")
            return
        self.log_text_edit.append(f"Starting processing for folder: {folder}")
        self.worker = WorkerThread(folder)
        self.worker.api_count_signal.connect(self.update_api_count)
        self.worker.log_signal.connect(self.log_message)
        self.worker.finished_signal.connect(self.processing_finished)
        self.worker.start()
        self.start_button.setEnabled(False)

    def update_api_count(self, count):
        self.api_count_label.setText(f"API Calls: {count}")

    def log_message(self, message):
        self.log_text_edit.append(message)

    def processing_finished(self):
        self.log_text_edit.append("Processing finished.")
        self.start_button.setEnabled(True)

# -------------------------------
# Main Application Entry Point
# -------------------------------

if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
