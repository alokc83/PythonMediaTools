
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QLineEdit, 
    QTextEdit, QFileDialog, QHBoxLayout, QMessageBox, QProgressBar, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from src.core.audio_shelf.atf_cleaner import ATFCleaner
import os

class DragDropLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Drag & Drop folder here or browse...")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isdir(path):
                self.setText(path)
                event.acceptProposedAction()

class ATFCleanWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, cleaner, directory):
        super().__init__()
        self.cleaner = cleaner
        self.directory = directory
        self._is_running = True

    def run(self):
        self.cleaner.clean_files(self.directory, self.log_signal.emit)
        self.finished_signal.emit()

    def stop(self):
        self._is_running = False

class ATFCleanerWidget(QWidget):
    def __init__(self, settings_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        self.cleaner = ATFCleaner()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Header
        header_layout = QHBoxLayout()
        header = QLabel("ATF Cache Cleaner")
        header.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px; color: #00bcd4;")
        header_layout.addWidget(header)
        header_layout.addStretch()
        
        self.dashboard_toggle = QCheckBox("Show in Dashboard")
        self.dashboard_toggle.setChecked(self.get_dashboard_visibility())
        self.dashboard_toggle.stateChanged.connect(self.toggle_dashboard_visibility)
        header_layout.addWidget(self.dashboard_toggle)
        
        layout.addLayout(header_layout)

        desc = QLabel("Recursively delete all .atf cache files to force a fresh metadata scan next time.")
        desc.setStyleSheet("color: #aaa; margin-bottom: 15px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Input Area
        input_layout = QHBoxLayout()
        self.dir_edit = DragDropLineEdit()
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_dir)
        input_layout.addWidget(self.dir_edit)
        input_layout.addWidget(browse_btn)
        layout.addLayout(input_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton("Clean .atf Files")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff5555; 
                color: white; 
                padding: 10px; 
                border-radius: 4px; 
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ff7777;
            }
        """)
        self.run_btn.clicked.connect(self.run_clean)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_clean)
        
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)

        # Log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: monospace;")
        layout.addWidget(self.log_text)

        self.setLayout(layout)

    def browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Directory")
        if d:
            self.dir_edit.setText(d)

    def log(self, msg):
        self.log_text.append(msg)
        # Scroll to bottom
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def run_clean(self):
        d = self.dir_edit.text()
        if not d or not os.path.exists(d):
            QMessageBox.warning(self, "Error", "Please select a valid directory.")
            return

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.dir_edit.setEnabled(False)
        self.log_text.clear()

        self.worker = ATFCleanWorker(self.cleaner, d)
        self.worker.log_signal.connect(self.log)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def stop_clean(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate() # Force kill for simple logic, or implement check in loop
            self.log("Stopped by user.")
            self.on_finished()

    def on_finished(self):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.dir_edit.setEnabled(True)

    def get_dashboard_visibility(self):
        if self.settings_manager:
            # atf cleaner id is 15
            val = self.settings_manager.get("dashboard_visible_15")
            if val is None: return True
            return str(val).lower() == 'true'
        return True

    def toggle_dashboard_visibility(self):
        if self.settings_manager:
            state = self.dashboard_toggle.isChecked()
            self.settings_manager.set("dashboard_visible_15", str(state).lower())
