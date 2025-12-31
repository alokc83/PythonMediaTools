
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QLineEdit, QFileDialog, QProgressBar, QMessageBox, QCheckBox, QGroupBox, QListWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from src.core.audio_shelf.pruner import FormatPruner

class PrunerScanThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(list)

    def __init__(self, pruner, root_dir):
        super().__init__()
        self.pruner = pruner
        self.root_dir = root_dir
        self.running = True

    def run(self):
        candidates = self.pruner.scan_directory(
            self.root_dir, 
            lambda msg: self.progress.emit(msg),
            stop_check=lambda: not self.running
        )
        self.finished.emit(candidates)

    def stop(self):
        self.running = False

class PrunerExecuteThread(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int, int)

    def __init__(self, pruner, dry_run):
        super().__init__()
        self.pruner = pruner
        self.dry_run = dry_run
        self.running = True

    def run(self):
        deleted, errors = self.pruner.execute_prune(
            self.dry_run, 
            lambda i, t, p: self.progress.emit(i, t, f"Deleting {p}"),
            stop_check=lambda: not self.running
        )
        self.finished.emit(deleted, errors)

    def stop(self):
        self.running = False


class PrunerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.pruner = FormatPruner()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header_layout = QVBoxLayout()
        title_lbl = QLabel("Blinkist Format Pruner")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #00bcd4;")
        desc_lbl = QLabel("Automatically finds and deletes 'mp3' files if a higher quality 'm4a' or 'm4b' version exists with the same name.\n"
                          "This helps reduce storage usage by removing redundant lower-quality copies.")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 14px; color: #b0b0b0; margin-bottom: 20px;")
        header_layout.addWidget(title_lbl)
        header_layout.addWidget(desc_lbl)
        layout.addLayout(header_layout)

        # Input
        input_group = QGroupBox("Blinkist Pruner (Delete mp3 if m4a/m4b exists)")
        input_layout = QHBoxLayout()
        self.dir_edit = QLineEdit()
        browse_btn = QPushButton("Browse Root")
        browse_btn.clicked.connect(self.browse_dir)
        input_layout.addWidget(self.dir_edit)
        input_layout.addWidget(browse_btn)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # Settings
        self.dry_run_check = QCheckBox("Dry Run")
        self.dry_run_check.setChecked(True)
        layout.addWidget(self.dry_run_check)

        # Actions
        btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self.start_scan)
        
        self.execute_btn = QPushButton("Prune Files")
        self.execute_btn.setEnabled(False)
        self.execute_btn.clicked.connect(self.start_execute)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold;")
        self.stop_btn.clicked.connect(self.stop_process)
        self.stop_btn.setEnabled(False)
        
        btn_layout.addWidget(self.scan_btn)
        btn_layout.addWidget(self.execute_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)

        # Progress
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        # List
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

    def browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Root Directory")
        if d:
            self.dir_edit.setText(d)

    def start_scan(self):
        d = self.dir_edit.text()
        if not d:
            QMessageBox.warning(self, "Error", "Select a root directory.")
            return

        self.scan_btn.setEnabled(False)
        self.execute_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setRange(0, 0)
        
        self.scan_thread = PrunerScanThread(self.pruner, d)
        self.scan_thread.progress.connect(lambda msg: self.status_label.setText(msg))
        self.scan_thread.finished.connect(self.scan_finished)
        self.scan_thread.start()

    def scan_finished(self, candidates):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Found {len(candidates)} mp3 files to delete.")
        self.list_widget.clear()
        for p in candidates:
            self.list_widget.addItem(p)
        
        self.scan_btn.setEnabled(True)
        self.execute_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def start_execute(self):
        self.execute_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setRange(0, len(self.pruner.to_delete))

        dry_run = self.dry_run_check.isChecked()
        self.exec_thread = PrunerExecuteThread(self.pruner, dry_run)
        self.exec_thread.progress.connect(self.update_progress)
        self.exec_thread.finished.connect(self.execution_finished)
        self.exec_thread.start()

    def stop_process(self):
        if hasattr(self, 'scan_thread') and self.scan_thread.isRunning():
            self.scan_thread.stop()
            self.status_label.setText("Stopping Scan...")
        if hasattr(self, 'exec_thread') and self.exec_thread.isRunning():
            self.exec_thread.stop()
            self.status_label.setText("Stopping Execution...")
        self.stop_btn.setEnabled(False)

    def update_progress(self, current, total, msg):
        self.progress_bar.setValue(current)
        self.status_label.setText(msg)

    def execution_finished(self, deleted, errors):
        self.scan_btn.setEnabled(True)
        self.execute_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        QMessageBox.information(self, "Result", f"Deleted: {deleted}\nErrors: {errors}")
