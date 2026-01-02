from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QFileDialog, QGroupBox, QProgressBar, QMessageBox, QCheckBox, QTextEdit
)
import os
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from src.core.audio_shelf.rating_updater import RatingUpdaterEngine

class UpdateWorker(QThread):
    progress_signal = pyqtSignal(int, int) # current, total
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, directories, engine):
        super().__init__()
        self.directories = directories
        self.engine = engine
        # Redirect engine log to signal
        self.engine.log_callback = self.emit_log

    def run(self):
        self.engine.scan_and_update(
            self.directories,
            progress_callback=self.emit_progress
        )
        self.finished_signal.emit()

    def emit_progress(self, current, total):
        self.progress_signal.emit(current, total)
    
    def emit_log(self, text):
        self.log_signal.emit(text)

class DragDropListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.controller = parent # Store explicit reference to main widget
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DropOnly)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    # Signal controller to add directory
                    if self.controller:
                        self.controller.add_directory_path(path)
            event.accept()

class RatingUpdaterWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.directories = []
        self.engine = RatingUpdaterEngine()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header
        header_lbl = QLabel("Rating & Review Updater")
        header_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #00bcd4;")
        layout.addWidget(header_lbl)
        
        # Progress Bar (Moved to Top)
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        desc = QLabel(
            "Batch update audio files with Star Ratings and Review Counts from Audible/Google.\n"
            "Feature: Updates fresh data every time (ignoring cache validity)."
        )
        desc.setStyleSheet("color: #b0b0b0; margin-bottom: 5px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Input List
        input_group = QGroupBox("Directories to Update (Drag & Drop Supported)")
        input_layout = QHBoxLayout() # Horizontal main layout
        
        self.dir_list = DragDropListWidget(self)
        self.dir_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.dir_list.setMaximumHeight(150)
        input_layout.addWidget(self.dir_list, 1) # Expand text area
        
        btn_layout = QVBoxLayout() # Vertical button column
        add_btn = QPushButton("Add Listing")
        add_btn.clicked.connect(self.add_directory)
        
        clear_btn = QPushButton("Clear List")
        clear_btn.clicked.connect(self.clear_list)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch() # Push buttons to top
        input_layout.addLayout(btn_layout)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # Log Area (Increased size)
        log_group = QGroupBox("Process Log")
        log_layout = QVBoxLayout()
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: monospace; font-size: 11px; background-color: #1e1e1e; color: #d4d4d4;")
        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group, 1) # Give flex 1 to expand

        # Action Buttons
        action_layout = QHBoxLayout()
        self.run_btn = QPushButton("Start Update")
        self.run_btn.setStyleSheet("background-color: #00bcd4; color: white; font-weight: bold; padding: 10px 20px; font-size: 14px;")
        self.run_btn.clicked.connect(self.start_update)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold; padding: 10px;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_update)
        
        action_layout.addStretch()
        action_layout.addWidget(self.run_btn)
        action_layout.addWidget(self.stop_btn)
        layout.addLayout(action_layout) # Removed spacer to let Log Area expand

    def add_directory(self):
        d = QFileDialog.getExistingDirectory(self, "Select Directory to Update")
        if d:
            self.add_directory_path(d)

    def add_directory_path(self, path):
         if path not in self.directories:
             self.directories.append(path)
             self.dir_list.addItem(path)

    def clear_list(self):
        self.directories = []
        self.dir_list.clear()

    def start_update(self):
        if not self.directories:
            QMessageBox.warning(self, "No Directories", "Please add at least one directory to update.")
            return

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.log_view.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self.directories))
        
        self.worker = UpdateWorker(self.directories, self.engine)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.log_signal.connect(self.append_log)
        self.worker.finished_signal.connect(self.finished)
        self.worker.start()

    def stop_update(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.terminate() # Force stop for now as engine doesn't have polite stop check yet
            self.append_log("Process stopped by user.")
            self.finished()

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def append_log(self, text):
        color = "#d4d4d4" # Default grey
        if "Final Weighted Rating" in text:
            color = "#00ff00" # Green
        elif "Updated ATF cache" in text or "Updated" in text:
            color = "#4caf50" # Green
        elif "Audnexus fetch error" in text or "Google fetch error" in text or "Error" in text:
            color = "#ff5555" # Red
        elif "Found Audible" in text or "Found Google" in text:
            color = "#00bcd4" # Cyan
        elif "Fetching fresh rating" in text or "Searching for" in text:
            color = "#ffb74d" # Orange/Yellow
            
        html = f'<span style="color: {color};">{text}</span>'
        self.log_view.append(html)
        # self.log_view.moveCursor(QTextCursor.End) # Auto scroll is default for append

    def finished(self):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.append_log("Done.")
