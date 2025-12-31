
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QLineEdit, QFileDialog, QProgressBar, QMessageBox, QCheckBox, QGroupBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from src.core.audio_shelf.organizer import FileToDir

class OrganizerScanThread(QThread):
    finished = pyqtSignal(list)

    def __init__(self, organizer, target_dir, exts):
        super().__init__()
        self.organizer = organizer
        self.target_dir = target_dir
        self.exts = exts

    def run(self):
        files = self.organizer.scan_directory(self.target_dir, self.exts)
        self.finished.emit(files)

class OrganizerExecuteThread(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int, int, int, int)

    def __init__(self, organizer, target_dir, dry_run):
        super().__init__()
        self.organizer = organizer
        self.target_dir = target_dir
        self.dry_run = dry_run
        self.running = True

    def run(self):
        moved, s1, s2, err = self.organizer.execute_organize(
            self.target_dir, 
            self.dry_run, 
            lambda i, t, s: self.progress.emit(i, t, f"Moving {s}"),
            stop_check=lambda: not self.running
        )
        self.finished.emit(moved, s1, s2, err)

    def stop(self):
        self.running = False


class DragDropLineEdit(QLineEdit):
    # ... (unchanged) ...
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Select or Drag & Drop a Directory here...")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.setText(path)
                event.acceptProposedAction()

class OrganizerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.organizer = FileToDir()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header_layout = QVBoxLayout()
        title_lbl = QLabel("File to Directory Organizer")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #00bcd4;")
        desc_lbl = QLabel("Moves each file (Audio/PDF/EPUB) from the selected directory into its own new folder named after the file.\n"
                          "Useful for organizing loose tracks and books into a structured folder hierarchy.")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 14px; color: #b0b0b0; margin-bottom: 20px;")
        header_layout.addWidget(title_lbl)
        header_layout.addWidget(desc_lbl)
        layout.addLayout(header_layout)

        # Input
        input_group = QGroupBox("Target Directory (Current Level Only)")
        input_layout = QHBoxLayout()
        self.dir_edit = DragDropLineEdit()
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_dir)
        input_layout.addWidget(self.dir_edit)
        input_layout.addWidget(browse_btn)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # Settings
        self.dry_run_check = QCheckBox("Dry Run")
        self.dry_run_check.setChecked(True)
        layout.addWidget(self.dry_run_check)

        # Status
        self.info_label = QLabel("Select a directory and scan.")
        layout.addWidget(self.info_label)

        # Actions
        btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self.start_scan)
        
        self.execute_btn = QPushButton("Organize Files")
        self.execute_btn.setEnabled(False)
        self.execute_btn.clicked.connect(self.start_execute)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold;")
        self.stop_btn.clicked.connect(self.stop_execute)
        self.stop_btn.setEnabled(False)
        
        btn_layout.addWidget(self.scan_btn)
        btn_layout.addWidget(self.execute_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)

        # Progress
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

    def browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Directory")
        if d:
            self.dir_edit.setText(d)

    def start_scan(self):
        d = self.dir_edit.text()
        if not d:
            QMessageBox.warning(self, "Error", "Select a directory.")
            return
        
        self.scan_btn.setEnabled(False)
        self.execute_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.scan_thread = OrganizerScanThread(self.organizer, d, {"mp3", "m4a", "m4b", "pdf", "epub"})
        self.scan_thread.finished.connect(self.scan_finished)
        self.scan_thread.start()

    def scan_finished(self, files):
        self.info_label.setText(f"Found {len(files)} files.")
        self.scan_btn.setEnabled(True)
        self.execute_btn.setEnabled(True)

    def start_execute(self):
        d = self.dir_edit.text()
        self.execute_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setRange(0, len(self.organizer.files))

        dry_run = self.dry_run_check.isChecked()
        self.exec_thread = OrganizerExecuteThread(self.organizer, d, dry_run)
        self.exec_thread.progress.connect(lambda c, t, m: self.progress_bar.setValue(c))
        self.exec_thread.finished.connect(self.execution_finished)
        self.exec_thread.start()

    def stop_execute(self):
        if hasattr(self, 'exec_thread') and self.exec_thread.isRunning():
            self.exec_thread.stop()
            self.stop_btn.setEnabled(False)

    def execution_finished(self, moved, s1, s2, err):
        self.scan_btn.setEnabled(True)
        self.execute_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        QMessageBox.information(self, "Result", f"Moved: {moved}\nSkipped (exists/bad): {s1+s2}\nErrors: {err}")
