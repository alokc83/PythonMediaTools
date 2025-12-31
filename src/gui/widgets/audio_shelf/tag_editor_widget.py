
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QFileDialog, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QMessageBox, QTextEdit, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from src.core.audio_shelf.tagger import TaggerEngine
from src.gui.widgets.audio_shelf.organizer_widget import DragDropLineEdit

class TaggerThread(QThread):
    progress_signal = pyqtSignal(int, int, str)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, files, fields_to_update=None, dry_run=False, force_cover=False):
        super().__init__()
        self.files = files
        self.fields_to_update = fields_to_update or {}
        self.dry_run = dry_run
        self.force_cover = force_cover
        self.engine = TaggerEngine()
        self.running = True
        self.failed_directories = set()  # Track directories where metadata lookup failed

    def run(self):
        total = len(self.files)
        for idx, f in enumerate(self.files):
            if not self.running: break
            
            self.progress_signal.emit(idx + 1, total, f"Processing: {os.path.basename(f)}")
            
            # Check if this file's directory has already failed
            file_dir = os.path.dirname(f)
            if file_dir in self.failed_directories:
                self.log_signal.emit(f"⏭️  SKIPPED: Directory already failed metadata lookup")
                self.log_signal.emit(f"[SKIPPED] Skipping file in failed directory: {os.path.basename(f)}")
                self.log_signal.emit("-" * 50)
                continue
            
            # Pass our signal emitter as the callback for real-time logging
            success, msg = self.engine.process_file(f, fields_to_update=self.fields_to_update, dry_run=self.dry_run, force_cover=self.force_cover, log_callback=self.log_signal.emit)
            
            # If metadata lookup failed (not just low confidence), mark directory as failed
            if not success and "No metadata found online" in msg:
                self.failed_directories.add(file_dir)
                self.log_signal.emit(f"📁 Marking directory for skip: {os.path.basename(file_dir)}/")
            
            status = "SUCCESS" if success else "FAILED"
            self.log_signal.emit(f"[{status}] Final Result: {msg}")
            self.log_signal.emit("-" * 50)
            
        self.finished_signal.emit()

    def stop(self):
        self.running = False


class TagEditorWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.files = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header_layout = QVBoxLayout()
        title_lbl = QLabel("Auto Metadata Tagger")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #00bcd4;")
        desc_lbl = QLabel("Automatically fetches metadata (Title, Author, GENRE, Cover Art) from Google Books.\n"
                          "Enforces Genre updates and preserves existing Cover Art.")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 14px; color: #b0b0b0; margin-bottom: 20px;")
        header_layout.addWidget(title_lbl)
        header_layout.addWidget(desc_lbl)
        layout.addLayout(header_layout)

        # Input
        input_group = QGroupBox("Input Directory")
        input_layout = QHBoxLayout()
        self.dir_edit = DragDropLineEdit()
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_dir)
        input_layout.addWidget(self.dir_edit)
        input_layout.addWidget(browse_btn)
        
        scan_btn = QPushButton("Scan Files")
        scan_btn.clicked.connect(self.scan_files)
        input_layout.addWidget(scan_btn)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # File List
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(250)  # Larger file list
        layout.addWidget(self.file_list)

        # Field Selection
        field_group = QGroupBox("Update Fields (Uncheck to skip)")
        field_layout = QVBoxLayout()
        field_layout.setSpacing(8)  # Moderate spacing
        
        # Create checkboxes (more compact)
        self.title_check = QCheckBox("Title")
        self.title_check.setChecked(True)
        self.author_check = QCheckBox("Artist/Author")
        self.author_check.setChecked(True)
        self.album_check = QCheckBox("Album")
        self.album_check.setChecked(True)
        self.album_artist_check = QCheckBox("Album Artist")
        self.album_artist_check.setChecked(True)
        self.genre_check = QCheckBox("Genre")
        self.genre_check.setChecked(True)
        self.year_check = QCheckBox("Year")
        self.year_check.setChecked(True)
        self.publisher_check = QCheckBox("Publisher")
        self.publisher_check.setChecked(True)
        self.description_check = QCheckBox("Description/Comments")
        self.description_check.setChecked(True)
        self.cover_check = QCheckBox("Cover Art")
        self.cover_check.setChecked(True)
        self.grouping_check = QCheckBox("Grouping")
        self.grouping_check.setChecked(False)  # Optional field
        self.compilation_check = QCheckBox("Compilation")
        self.compilation_check.setChecked(False)  # Optional field
        
        # Add to layout in four columns (more compact)
        row1 = QHBoxLayout()
        row1.setSpacing(15)
        row1.addWidget(self.title_check)
        row1.addWidget(self.author_check)
        row1.addWidget(self.album_check)
        row1.addWidget(self.album_artist_check)
        
        row2 = QHBoxLayout()
        row2.setSpacing(15)
        row2.addWidget(self.genre_check)
        row2.addWidget(self.year_check)
        row2.addWidget(self.publisher_check)
        row2.addWidget(self.grouping_check)
        
        row3 = QHBoxLayout()
        row3.setSpacing(15)
        row3.addWidget(self.description_check)
        row3.addWidget(self.cover_check)
        row3.addWidget(self.compilation_check)
        row3.addStretch()  # Push to left
        
        field_layout.addLayout(row1)
        field_layout.addLayout(row2)
        field_layout.addLayout(row3)
        field_group.setLayout(field_layout)
        field_group.setMaximumHeight(150)  # Slightly more height
        layout.addWidget(field_group)

        # Force Cover Art Option
        self.force_cover_check = QCheckBox("Force Replace Cover Art (even if exists)")
        self.force_cover_check.setChecked(False)
        self.force_cover_check.setStyleSheet("font-style: italic; color: #ff5722;")
        layout.addWidget(self.force_cover_check)

        # Dry Run Option
        self.dry_run_check = QCheckBox("Dry Run (Preview changes without writing)")
        self.dry_run_check.setChecked(True)
        self.dry_run_check.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.dry_run_check.stateChanged.connect(self.update_button_text)
        layout.addWidget(self.dry_run_check)

        # Logs
        log_group = QGroupBox("Process Log")
        log_layout = QVBoxLayout()
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(400)  # Much larger process log
        log_layout.addWidget(self.log_area)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Actions
        action_layout = QHBoxLayout()
        self.run_btn = QPushButton("Start Auto-Tagging (Dry Run)")
        self.run_btn.setStyleSheet("background-color: #00bcd4; color: white; font-weight: bold; padding: 10px;")
        self.run_btn.clicked.connect(self.start_tagging)
        self.run_btn.setEnabled(False)
        action_layout.addWidget(self.run_btn)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold; padding: 10px;")
        self.stop_btn.clicked.connect(self.stop_tagging)
        self.stop_btn.setEnabled(False)
        action_layout.addWidget(self.stop_btn)
        
        layout.addLayout(action_layout)

    def browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Directory")
        if d:
            self.dir_edit.setText(d)
            self.scan_files()

    def scan_files(self):
        d = self.dir_edit.text()
        if not d or not os.path.isdir(d):
            return

        self.files = []
        self.file_list.clear()
        
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith((".mp3", ".m4a", ".m4b", ".opus")):
                    path = os.path.join(root, f)
                    self.files.append(path)
                    self.file_list.addItem(f)
                    
        self.log_area.append(f"Found {len(self.files)} audio files.")
        if self.files:
            self.run_btn.setEnabled(True)
    
    def update_button_text(self):
        """Update button text based on dry run checkbox state"""
        if self.dry_run_check.isChecked():
            self.run_btn.setText("Start Auto-Tagging (Dry Run)")
        else:
            self.run_btn.setText("Start Auto-Tagging")

    def start_tagging(self):
        if not self.files: return
        
        # Collect selected fields
        fields_to_update = {
            "title": self.title_check.isChecked(),
            "author": self.author_check.isChecked(),
            "album": self.album_check.isChecked(),
            "album_artist": self.album_artist_check.isChecked(),
            "genre": self.genre_check.isChecked(),
            "year": self.year_check.isChecked(),
            "publisher": self.publisher_check.isChecked(),
            "description": self.description_check.isChecked(),
            "cover": self.cover_check.isChecked(),
            "grouping": self.grouping_check.isChecked(),
            "compilation": self.compilation_check.isChecked()
        }
        
        dry_run = self.dry_run_check.isChecked()
        force_cover = self.force_cover_check.isChecked()
        
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.log_area.clear()
        
        if dry_run:
            self.log_area.append('<span style="color: #ff9800; font-weight: bold;">🔍 DRY RUN MODE - No files will be modified</span>')
            self.log_area.append("-" * 50)
        
        self.thread = TaggerThread(self.files, fields_to_update, dry_run, force_cover)
        self.thread.progress_signal.connect(self.update_progress)
        self.thread.log_signal.connect(self.log_msg)
        self.thread.finished_signal.connect(self.finished)
        self.thread.start()
        
    def stop_tagging(self):
        if hasattr(self, 'thread') and self.thread.isRunning():
            self.thread.stop()
            self.log_area.append('<span style="color: #ff4444; font-weight: bold;">Stopping...</span>')
            self.stop_btn.setEnabled(False)

    def update_progress(self, current, total, msg):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def log_msg(self, msg):
        if "[FAILED]" in msg:
            # efficient html styling
            formatted = f'<span style="color: #ff4444; font-weight: bold;">{msg}</span>'
            self.log_area.append(formatted)
        elif "[SUCCESS]" in msg:
            formatted = f'<span style="color: #00ff00; font-weight: bold;">{msg}</span>'
            self.log_area.append(formatted)
        else:
            self.log_area.append(msg)

    def finished(self):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        QMessageBox.information(self, "Completed", "Tagging Completed!")
