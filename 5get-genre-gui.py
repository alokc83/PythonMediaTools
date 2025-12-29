#!/usr/bin/env python3
import os
import time
import shutil
import requests
from mutagen import File as MutagenFile
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog,
    QVBoxLayout, QWidget, QHBoxLayout, QProgressBar, QCheckBox
)
from PyQt5.QtCore import QThread, pyqtSignal

# Custom exception for rate limiting
class RateLimitException(Exception):
    pass

# -------------------------------
# API and Metadata Functions
# -------------------------------

def get_book_info_google(book_title, api_key, delay=1):
    """
    Query the Google Books API for a given book title and return a dictionary
    with keys 'categories' and 'cover_url' from the first result that has categories.
    Raises RateLimitException if a 429 or 403 status is encountered.
    """
    query = f"intitle:{book_title}"
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": query, "maxResults": 5, "key": api_key}
    time.sleep(delay)
    response = requests.get(url, params=params)
    if response.status_code == 429:
        raise RateLimitException("Google Books API rate limit exceeded.")
    elif response.status_code == 403:
        raise RateLimitException("Google Books API returned 403. Check your API key and permissions.")
    elif response.status_code != 200:
        return None
    data = response.json()
    items = data.get("items", [])
    if not items:
        return None
    for item in items:
        volume_info = item.get("volumeInfo", {})
        categories = volume_info.get("categories")
        image_links = volume_info.get("imageLinks", {})
        cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")
        if categories:
            return {"categories": categories, "cover_url": cover_url}
    return None

def get_book_categories_openlibrary(book_title):
    """
    Query the OpenLibrary API for a given book title and return the subjects
    (as genre information) from the first result that has them.
    (OpenLibrary does not provide cover image data in this endpoint.)
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

def cover_exists(file_path):
    """
    Check if the file already has a cover image embedded.
    For MP3 files, checks for an APIC frame.
    For M4A files, checks for the 'covr' tag.
    """
    if file_path.lower().endswith('.mp3'):
        try:
            from mutagen.id3 import ID3
            audio = ID3(file_path)
            return any(frame for frame in audio.values() if frame.FrameID == "APIC")
        except Exception:
            return False
    elif file_path.lower().endswith('.m4a'):
        try:
            from mutagen.mp4 import MP4
            audio = MP4(file_path)
            return "covr" in audio and bool(audio["covr"])
        except Exception:
            return False
    return False

def write_cover_to_file(file_path, cover_url):
    """
    Download the cover image from cover_url and write it to the file's metadata
    as the album cover.
    Supports MP3 (ID3 APIC) and M4A (MP4 covr) files.
    """
    try:
        response = requests.get(cover_url, timeout=10)
        if response.status_code != 200:
            return False
        cover_data = response.content
        if file_path.lower().endswith('.mp3'):
            from mutagen.id3 import ID3, APIC
            try:
                audio = ID3(file_path)
            except Exception:
                audio = ID3()
            audio.delall("APIC")
            audio.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover_data))
            audio.save(file_path)
        elif file_path.lower().endswith('.m4a'):
            from mutagen.mp4 import MP4, MP4Cover
            audio = MP4(file_path)
            audio['covr'] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.save()
        return True
    except Exception as e:
        print(f"Error writing cover image for file {file_path}: {e}")
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
    progress_signal = pyqtSignal(int)  # Emits number of files processed
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, folder, api_key, force_cover_update=False):
        super().__init__()
        self.folder = folder
        self.api_key = api_key
        self.force_cover_update = force_cover_update
        self.api_count = 0
        self._paused = False
        self._cancelled = False

    def run(self):
        files = scan_audio_files(self.folder)
        total_files = len(files)
        self.log_signal.emit(f"Found {total_files} audio files.")
        processed_files = 0
        parent_folder = os.path.dirname(self.folder)

        for file_path in files:
            # Process only files directly in the processing folder.
            if os.path.abspath(os.path.dirname(file_path)) != os.path.abspath(self.folder):
                self.log_signal.emit(f"File already moved, skipping: {file_path}")
                processed_files += 1
                self.progress_signal.emit(processed_files)
                continue

            if self._cancelled:
                self.log_signal.emit("Processing cancelled.")
                self.finished_signal.emit()
                return

            while self._paused:
                self.msleep(100)
                if self._cancelled:
                    self.log_signal.emit("Processing cancelled.")
                    self.finished_signal.emit()
                    return

            self.log_signal.emit(f"\nProcessing file: {file_path}")
            title = extract_title_from_file(file_path)
            if not title:
                self.log_signal.emit("No title metadata found, skipping.")
                processed_files += 1
                self.progress_signal.emit(processed_files)
                continue

            self.log_signal.emit(f"Extracted title: {title}")

            # Process metadata: update genre and cover image if needed.
            audio = MutagenFile(file_path, easy=True)
            if audio is not None and "genre" in audio and audio["genre"]:
                categories = audio["genre"]
                self.log_signal.emit("Existing genre metadata found: " + ", ".join(categories))
                if self.force_cover_update:
                    self.log_signal.emit("Force update enabled. Updating cover image...")
                    try:
                        info = get_book_info_google(title, self.api_key)
                        self.api_count += 1
                        self.api_count_signal.emit(self.api_count)
                        if info and info.get("cover_url"):
                            cover_url = info["cover_url"]
                            if write_cover_to_file(file_path, cover_url):
                                self.log_signal.emit("Cover image updated successfully.")
                            else:
                                self.log_signal.emit("Failed to update cover image.")
                        else:
                            self.log_signal.emit("No cover image found from API.")
                    except RateLimitException as e:
                        self.log_signal.emit(f"Rate limit error: {e}. Stopping processing.")
                        self.finished_signal.emit()
                        return
                else:
                    self.log_signal.emit("Cover image exists and force update not enabled; skipping cover update.")
            else:
                try:
                    info = get_book_info_google(title, self.api_key)
                    self.api_count += 1
                    self.api_count_signal.emit(self.api_count)
                except RateLimitException as e:
                    self.log_signal.emit(f"Rate limit error: {e}. Stopping processing.")
                    self.finished_signal.emit()
                    return
                if info:
                    categories = info.get("categories")
                    cover_url = info.get("cover_url")
                    if categories:
                        self.log_signal.emit("Categories found: " + ", ".join(categories))
                        if write_genre_to_file(file_path, categories):
                            self.log_signal.emit("File metadata updated with genre.")
                        else:
                            self.log_signal.emit("Failed to update file metadata.")
                    else:
                        self.log_signal.emit("No genre information found from API.")
                else:
                    categories = None
                    cover_url = None
                if cover_url:
                    if (not cover_exists(file_path)) or self.force_cover_update:
                        if write_cover_to_file(file_path, cover_url):
                            self.log_signal.emit("Cover image updated successfully.")
                        else:
                            self.log_signal.emit("Failed to update cover image.")
                    else:
                        self.log_signal.emit("Cover image exists; not updating.")

            # --- File Move Logic ---
            # We always process and update metadata.
            # For moving: if genre info is available, determine target folder.
            if categories:
                target_folder = os.path.join(parent_folder, categories[0])
                # If the current directory name equals the target folder name, skip moving.
                current_dir_name = os.path.basename(os.path.abspath(os.path.dirname(file_path)))
                if current_dir_name == categories[0]:
                    self.log_signal.emit("File is already in the target genre folder; not moving.")
                else:
                    if not os.path.exists(target_folder):
                        os.makedirs(target_folder)
                        self.log_signal.emit(f"Created folder: {target_folder}")
                    try:
                        dest_file = os.path.join(target_folder, os.path.basename(file_path))
                        shutil.move(file_path, dest_file)
                        self.log_signal.emit(f"Moved file to {dest_file}")
                    except Exception as e:
                        self.log_signal.emit(f"Error moving file: {e}")
            else:
                self.log_signal.emit("No genre information found, skipping move.")

            processed_files += 1
            self.progress_signal.emit(processed_files)

        self.finished_signal.emit()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def cancel(self):
        self._cancelled = True
        self._paused = False  # Ensure we exit pause if paused

# -------------------------------
# Main Window (GUI)
# -------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audiobook Genre Updater")
        self.setGeometry(100, 100, 700, 650)
        self.worker = None
        self.processing = False
        self.paused = False

        # UI Elements
        self.folder_label = QLabel("Selected Folder:")
        self.folder_line_edit = QLineEdit()
        self.browse_button = QPushButton("Browse")
        self.api_key_label = QLabel("Google API Key:")
        self.api_key_line_edit = QLineEdit()
        self.force_cover_checkbox = QCheckBox("Cover image force update")
        self.start_button = QPushButton("Start Processing")
        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.api_count_label = QLabel("API Calls: 0")
        self.progress_bar = QProgressBar()
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)

        # Layout Setup
        layout = QVBoxLayout()

        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.folder_line_edit)
        folder_layout.addWidget(self.browse_button)
        layout.addWidget(self.folder_label)
        layout.addLayout(folder_layout)

        api_layout = QHBoxLayout()
        api_layout.addWidget(self.api_key_label)
        api_layout.addWidget(self.api_key_line_edit)
        layout.addLayout(api_layout)

        layout.addWidget(self.force_cover_checkbox)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.pause_button)
        layout.addLayout(button_layout)

        layout.addWidget(self.api_count_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_text_edit)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Signal Connections
        self.browse_button.clicked.connect(self.browse_folder)
        self.start_button.clicked.connect(self.toggle_processing)
        self.pause_button.clicked.connect(self.toggle_pause)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.folder_line_edit.setText(folder)

    def toggle_processing(self):
        if not self.processing:
            folder = self.folder_line_edit.text()
            api_key = self.api_key_line_edit.text().strip()
            force_cover = self.force_cover_checkbox.isChecked()
            if not folder or not os.path.isdir(folder):
                self.log_text_edit.append("Please select a valid folder.")
                return
            if not api_key:
                self.log_text_edit.append("Please enter a valid Google API key.")
                return

            self.log_text_edit.append(f"Starting processing for folder: {folder}")
            self.worker = WorkerThread(folder, api_key, force_cover_update=force_cover)
            self.worker.api_count_signal.connect(self.update_api_count)
            self.worker.progress_signal.connect(self.update_progress)
            self.worker.log_signal.connect(self.log_message)
            self.worker.finished_signal.connect(self.processing_finished)

            total_files = len(scan_audio_files(folder))
            self.progress_bar.setMaximum(total_files)
            self.progress_bar.setValue(0)

            self.worker.start()
            self.start_button.setText("Cancel Process")
            self.pause_button.setEnabled(True)
            self.processing = True
        else:
            if self.worker:
                self.worker.cancel()
            self.start_button.setEnabled(False)
            self.log_text_edit.append("Cancellation requested...")

    def toggle_pause(self):
        if not self.paused:
            if self.worker:
                self.worker.pause()
            self.pause_button.setText("Resume")
            self.log_text_edit.append("Processing paused.")
            self.paused = True
        else:
            if self.worker:
                self.worker.resume()
            self.pause_button.setText("Pause")
            self.log_text_edit.append("Processing resumed.")
            self.paused = False

    def update_api_count(self, count):
        self.api_count_label.setText(f"API Calls: {count}")

    def update_progress(self, processed_count):
        self.progress_bar.setValue(processed_count)

    def log_message(self, message):
        self.log_text_edit.append(message)

    def processing_finished(self):
        self.log_text_edit.append("Processing finished.")
        self.start_button.setText("Start Processing")
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.processing = False
        self.paused = False

# -------------------------------
# Main Application Entry Point
# -------------------------------

if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
