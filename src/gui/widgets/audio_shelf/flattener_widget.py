
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QLineEdit, QFileDialog, QProgressBar, QMessageBox, QCheckBox, QGroupBox, QTextEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from src.core.audio_shelf.flattener import FolderFlattener

class FlattenerScanThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, flattener, root_dir, exts, cleanup):
        super().__init__()
        self.flattener = flattener
        self.root_dir = root_dir
        self.exts = exts
        self.cleanup = cleanup
        self.running = True

    def run(self):
        self.progress.emit("Scanning root files...")
        self.flattener.scan_root_files(self.root_dir, self.exts)
        
        if not self.running: 
            self.finished.emit()
            return

        self.progress.emit("Scanning recursive audio...")
        self.flattener.scan_recursive(
            self.root_dir, self.exts, 
            lambda msg: self.progress.emit(msg),
            stop_check=lambda: not self.running
        )
        
        if self.running and self.cleanup:
            self.progress.emit("Building cleanup list...")
            self.flattener.build_cleanup_list(self.root_dir, self.exts)
        
        self.finished.emit()

    def stop(self):
        self.running = False


class FlattenerExecuteThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, flattener, root_dir, dry_run, cleanup):
        super().__init__()
        self.flattener = flattener
        self.root_dir = root_dir
        self.dry_run = dry_run
        self.cleanup = cleanup
        self.running = True

    def run(self):
        log = []
        
        # 1. Rename root files
        if self.running:
            self.progress.emit("Renaming root files...")
            r, s, e = self.flattener.rename_root_files(
                self.root_dir, self.dry_run,
                stop_check=lambda: not self.running
            )
            log.append(f"Root Renamed: {r}, Skipped: {s}, Errors: {e}")

        # 2. Move to root
        if self.running:
            self.progress.emit("Moving files to root...")
            m, e2 = self.flattener.execute_move_to_root(
                self.root_dir, self.dry_run, 
                lambda i, t, p: self.progress.emit(f"Moving {i}/{t}"),
                stop_check=lambda: not self.running
            )
            log.append(f"Moved to Root: {m}, Errors: {e2}")

        # 3. Cleanup
        if self.running and self.cleanup:
            self.progress.emit("Cleaning up directories...")
            d, e3 = self.flattener.execute_cleanup(
                self.dry_run, 
                lambda i, t, p: self.progress.emit(f"Deleting {p}"),
                stop_check=lambda: not self.running
            )
            log.append(f"Dirs Deleted: {d}, Errors: {e3}")
        
        self.finished.emit("\n".join(log))

    def stop(self):
        self.running = False


class FlattenerWidget(QWidget):
    def __init__(self, settings_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        self.flattener = FolderFlattener()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header_layout = QVBoxLayout()
        title_lbl = QLabel("Flatten Directory Application")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #00bcd4;")
        desc_lbl = QLabel("Moves all audio files from nested subfolders into the selected root directory.\n"
                          "Optionally cleans up any empty folders left behind.")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 14px; color: #b0b0b0; margin-bottom: 20px;")
        header_layout.addWidget(title_lbl)
        header_layout.addWidget(desc_lbl)
        
        # Dashboard Visibility Toggle
        self.dashboard_toggle = QCheckBox("Show in Dashboard")
        self.dashboard_toggle.setStyleSheet("font-weight: bold; color: #00bcd4; margin-bottom: 10px;")
        self.dashboard_toggle.setChecked(self.get_dashboard_visibility())
        self.dashboard_toggle.stateChanged.connect(self.toggle_dashboard_visibility)
        header_layout.addWidget(self.dashboard_toggle)
        
        layout.addLayout(header_layout)

        # Input
        input_group = QGroupBox("Flatten to Root")
        input_layout = QHBoxLayout()
        self.dir_edit = QLineEdit()
        browse_btn = QPushButton("Browse Root")
        browse_btn.clicked.connect(self.browse_dir)
        input_layout.addWidget(self.dir_edit)
        input_layout.addWidget(browse_btn)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # Settings
        settings_layout = QHBoxLayout()
        self.cleanup_check = QCheckBox("Cleanup Empty Dirs")
        self.dry_run_check = QCheckBox("Dry Run")
        self.dry_run_check.setChecked(True)
        settings_layout.addWidget(self.cleanup_check)
        settings_layout.addWidget(self.dry_run_check)
        layout.addLayout(settings_layout)

        # Actions
        btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self.start_scan)
        
        self.execute_btn = QPushButton("Execute Flatten")
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

        # Log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

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
        
        self.scan_thread = FlattenerScanThread(
            self.flattener, d, {"mp3", "m4a", "m4b"}, self.cleanup_check.isChecked()
        )
        self.scan_thread.progress.connect(lambda msg: self.status_label.setText(msg))
        self.scan_thread.finished.connect(self.scan_finished)
        self.scan_thread.start()

    def scan_finished(self):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        
        msg = f"Scan Done.\nRoot Files: {len(self.flattener.root_files)}\nRecursive Audio: {len(self.flattener.all_audio)}\nTo Move: {len(self.flattener.to_move)}"
        if self.cleanup_check.isChecked():
            msg += f"\nDirs to Delete: {len(self.flattener.cleanup_dirs_list)}"
        
        self.log_text.setText(msg)
        self.status_label.setText("Scan Complete")
        self.scan_btn.setEnabled(True)
        self.execute_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def start_execute(self):
        d = self.dir_edit.text()
        self.execute_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setRange(0, 0) # Indeterminate for global progress

        dry_run = self.dry_run_check.isChecked()
        cleanup = self.cleanup_check.isChecked()
        
        self.exec_thread = FlattenerExecuteThread(self.flattener, d, dry_run, cleanup)
        self.exec_thread.progress.connect(lambda msg: self.status_label.setText(msg))
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

    def execution_finished(self, log):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.scan_btn.setEnabled(True)
        self.execute_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log_text.append("\nExecution Results:\n" + log)
        QMessageBox.information(self, "Finished", "Flatten operation complete.")

    def get_dashboard_visibility(self):
        if self.settings_manager:
            # flattener id is 6
            val = self.settings_manager.get("dashboard_visible_6")
            # Default to True if not set
            if val is None: return True
            return str(val).lower() == 'true'
        return True

    def toggle_dashboard_visibility(self):
        if self.settings_manager:
            state = self.dashboard_toggle.isChecked()
            self.settings_manager.set("dashboard_visible_6", str(state).lower())
