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
# Helper Function: Normalize Genre
# -------------------------------
def normalize_genre(genre_str):
    """Normalize a genre string to Pascal Case."""
    return " ".join(genre_str.split()).title()

# -------------------------------
# API and Metadata Functions
# -------------------------------
def get_book_info_google(book_title, api_key, delay=1):
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
        if not categories:
            continue
        normalized_categories = [normalize_genre(cat) for cat in categories if cat.strip()]
        cover_url = (volume_info.get("imageLinks", {}).get("thumbnail") or
                     volume_info.get("imageLinks", {}).get("smallThumbnail"))
        title = volume_info.get("title")
        authors = volume_info.get("authors")
        publisher = volume_info.get("publisher")
        publishedDate = volume_info.get("publishedDate")
        description = volume_info.get("description")
        return {
            "title": title,
            "authors": authors,
            "publisher": publisher,
            "publishedDate": publishedDate,
            "description": description,
            "categories": normalized_categories,
            "cover_url": cover_url
        }
    return None

def get_book_categories_openlibrary(book_title):
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
            return [normalize_genre(s) for s in subjects if s.strip()]
    return None

def extract_title_from_file(file_path):
    try:
        audio = MutagenFile(file_path, easy=True)
        if audio is None:
            return None
        album = audio.get("album", [])
        if album and album[0].strip():
            return album[0]
        title = audio.get("title", [])
        if title and title[0].strip():
            return title[0]
    except Exception as e:
        print(f"Error reading metadata from '{file_path}': {e}")
    return None

def write_genre_to_file(file_path, genres):
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
    audio_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(('.mp3', '.m4a')):
                audio_files.append(os.path.join(dirpath, filename))
    return audio_files

# -------------------------------
# Metadata Completeness Check Functions
# -------------------------------
def is_metadata_complete_mp3(file_path, publisher_override=None):
    from mutagen.id3 import ID3
    try:
        tags = ID3(file_path)
    except Exception:
        return False
    # Check Title, Authors, Published Date, Genre
    if not tags.get("TIT2") or not tags.get("TIT2").text[0].strip():
        return False
    if not tags.get("TPE1") or not tags.get("TPE1").text[0].strip():
        return False
    if not tags.get("TDRC") or not tags.get("TDRC").text[0].strip():
        return False
    if not tags.get("TCON") or not tags.get("TCON").text[0].strip():
        return False
    # Check Publisher – if publisher_override is not provided, publisher must exist.
    if not publisher_override or publisher_override.strip() == "":
        comms = tags.getall("COMM")
        has_pub = any(comm.desc == "Publisher" and comm.text and comm.text[0].strip() for comm in comms)
        if not has_pub:
            return False
    # Check Description
    comms = tags.getall("COMM")
    has_desc = any(comm.desc == "Description" and comm.text and comm.text[0].strip() for comm in comms)
    if not has_desc:
        return False
    return True

def is_metadata_complete_m4a(file_path, publisher_override=None):
    from mutagen.mp4 import MP4
    tags = MP4(file_path)
    if "©nam" not in tags or not tags["©nam"][0].strip():
        return False
    if "©ART" not in tags or not any(a.strip() for a in tags["©ART"]):
        return False
    if "©day" not in tags or not tags["©day"][0].strip():
        return False
    if "©gen" not in tags or not any(g.strip() for g in tags["©gen"]):
        return False
    if "desc" not in tags or not tags["desc"][0].strip():
        return False
    # Check Publisher; if publisher_override not provided, look for "©pub"
    if not publisher_override or publisher_override.strip() == "":
        if "©pub" not in tags or not tags["©pub"][0].strip():
            return False
    return True

def is_metadata_complete(file_path, publisher_override=None):
    if file_path.lower().endswith('.mp3'):
        return is_metadata_complete_mp3(file_path, publisher_override)
    elif file_path.lower().endswith('.m4a'):
        return is_metadata_complete_m4a(file_path, publisher_override)
    return False

# -------------------------------
# Full Metadata Update Function
# -------------------------------
def update_full_metadata(file_path, info, comment=None, publisher_override=None):
    if file_path.lower().endswith('.mp3'):
        from mutagen.id3 import ID3, TIT2, TPE1, TDRC, TCON, COMM
        try:
            tags = ID3(file_path)
        except Exception:
            tags = ID3()
        if info.get("title"):
            current = tags.get("TIT2")
            if not current or not current.text or current.text[0].strip() == "":
                tags.add(TIT2(encoding=3, text=[info["title"]]))
        if info.get("authors"):
            current = tags.get("TPE1")
            if not current or not current.text or current.text[0].strip() == "":
                tags.add(TPE1(encoding=3, text=info["authors"]))
        # Publisher: use publisher_override if provided.
        pub_val = publisher_override if publisher_override and publisher_override.strip() != "" else info.get("publisher")
        if pub_val:
            for comm in tags.getall("COMM"):
                if comm.desc == "Publisher":
                    tags.delall("COMM")
                    break
            tags.add(COMM(encoding=3, lang='eng', desc='Publisher', text=[pub_val]))
        if info.get("publishedDate"):
            current = tags.get("TDRC")
            if not current or not current.text or current.text[0].strip() == "":
                tags.add(TDRC(encoding=3, text=[info["publishedDate"]]))
        if info.get("categories"):
            current = tags.get("TCON")
            if not current or not current.text or current.text[0].strip() == "":
                tags.add(TCON(encoding=3, text=info["categories"]))
        if info.get("description"):
            for comm in tags.getall("COMM"):
                if comm.desc == "Description":
                    tags.delall("COMM")
                    break
            tags.add(COMM(encoding=3, lang='eng', desc='Description', text=[info["description"]]))
        # Always update Comment with provided value.
        if comment is not None:
            for comm in tags.getall("COMM"):
                if comm.desc == "Comment":
                    tags.delall("COMM")
                    break
            tags.add(COMM(encoding=3, lang='eng', desc='Comment', text=[comment]))
        tags.save(file_path)
        return True
    elif file_path.lower().endswith('.m4a'):
        from mutagen.mp4 import MP4
        tags = MP4(file_path)
        if info.get("title"):
            current = tags.get("©nam")
            if not current or not current[0].strip():
                tags["©nam"] = [info["title"]]
        if info.get("authors"):
            current = tags.get("©ART")
            if not current or not any(a.strip() for a in current):
                tags["©ART"] = info["authors"]
        if info.get("categories"):
            current = tags.get("©gen")
            if not current or not any(g.strip() for g in current):
                tags["©gen"] = info["categories"]
        if info.get("publishedDate"):
            current = tags.get("©day")
            if not current or not current[0].strip():
                tags["©day"] = [info["publishedDate"]]
        if info.get("description"):
            current = tags.get("desc")
            if not current or not current[0].strip():
                tags["desc"] = [info["description"]]
        # Publisher: use publisher_override if provided.
        pub_val = publisher_override if publisher_override and publisher_override.strip() != "" else info.get("publisher")
        if pub_val:
            tags["©pub"] = [pub_val]
        if comment is not None:
            tags["©cmt"] = [comment]
        tags.save()
        return True
    return False

# -------------------------------
# Worker Thread for Processing
# -------------------------------
class WorkerThread(QThread):
    api_count_signal = pyqtSignal(int)
    progress_signal = pyqtSignal(int)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, folder, api_key, force_cover_update=False, comment=None, publisher_override=None):
        super().__init__()
        self.folder = folder
        self.api_key = api_key
        self.force_cover_update = force_cover_update
        self.comment = comment
        self.publisher_override = publisher_override
        self.api_count = 0
        self._paused = False
        self._cancelled = False

    def run(self):
        files = scan_audio_files(self.folder)
        total_files = len(files)
        self.log_signal.emit(f"Found {total_files} audio files.")
        processed_files = 0
        root_folder = self.folder

        for file_path in files:
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

            # Check if metadata is complete (all required fields).
            if not is_metadata_complete(file_path, publisher_override=self.publisher_override):
                try:
                    info = get_book_info_google(title, self.api_key)
                    self.api_count += 1
                    self.api_count_signal.emit(self.api_count)
                except RateLimitException as e:
                    self.log_signal.emit(f"Rate limit error: {e}. Stopping processing.")
                    self.finished_signal.emit()
                    return
                if info:
                    self.log_signal.emit("Retrieved metadata from API.")
                    update_full_metadata(file_path, info, comment=self.comment, publisher_override=self.publisher_override)
                else:
                    self.log_signal.emit("No metadata retrieved from API.")
            else:
                self.log_signal.emit("All metadata fields are complete; skipping metadata update.")

            # Update cover image if needed.
            # (For cover, we update if missing or if forced.)
            if info and info.get("cover_url"):
                if (not cover_exists(file_path)) or self.force_cover_update:
                    if write_cover_to_file(file_path, info["cover_url"]):
                        self.log_signal.emit("Cover image updated successfully.")
                    else:
                        self.log_signal.emit("Failed to update cover image.")
                else:
                    self.log_signal.emit("Cover image exists; not updating.")

            # --- File Move Logic ---
            if info and info.get("categories"):
                target_genre = info["categories"][0]
                target_folder = os.path.join(root_folder, target_genre)
                current_dir_name = os.path.basename(os.path.abspath(os.path.dirname(file_path)))
                if current_dir_name == target_genre:
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
        self._paused = False

# -------------------------------
# Main Window (GUI)
# -------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audiobook Genre Updater")
        self.setGeometry(100, 100, 700, 750)
        self.worker = None
        self.processing = False
        self.paused = False

        self.folder_label = QLabel("Selected Folder:")
        self.folder_line_edit = QLineEdit()
        self.browse_button = QPushButton("Browse")
        self.api_key_label = QLabel("Google API Key:")
        self.api_key_line_edit = QLineEdit()
        self.force_cover_checkbox = QCheckBox("Cover image force update")
        self.comment_label = QLabel("Comment:")
        self.comment_line_edit = QLineEdit()
        self.publisher_label = QLabel("Publisher:")
        self.publisher_line_edit = QLineEdit()
        self.start_button = QPushButton("Start Processing")
        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.api_count_label = QLabel("API Calls: 0")
        self.progress_bar = QProgressBar()
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)

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

        comment_layout = QHBoxLayout()
        comment_layout.addWidget(self.comment_label)
        comment_layout.addWidget(self.comment_line_edit)
        layout.addLayout(comment_layout)

        publisher_layout = QHBoxLayout()
        publisher_layout.addWidget(self.publisher_label)
        publisher_layout.addWidget(self.publisher_line_edit)
        layout.addLayout(publisher_layout)

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
            comment = self.comment_line_edit.text().strip()
            publisher_override = self.publisher_line_edit.text().strip()
            if not folder or not os.path.isdir(folder):
                self.log_text_edit.append("Please select a valid folder.")
                return
            if not api_key:
                self.log_text_edit.append("Please enter a valid Google API key.")
                return

            self.log_text_edit.append(f"Starting processing for folder: {folder}")
            self.worker = WorkerThread(folder, api_key, force_cover_update=force_cover,
                                         comment=comment, publisher_override=publisher_override)
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

if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
