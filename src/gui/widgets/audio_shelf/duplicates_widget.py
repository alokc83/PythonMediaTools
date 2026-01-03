from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QFileDialog, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QMessageBox, QCheckBox, QRadioButton, QButtonGroup,
    QLineEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from src.core.audio_shelf.duplicates import DuplicatesFinder, DuplicateMethod

class DuplicateScanningThread(QThread):
    progress_signal = pyqtSignal(int, int, str)
    finished_signal = pyqtSignal(object) # returns the groups dict

    def __init__(self, directories, finder, method):
        super().__init__()
        self.directories = directories
        self.finder = finder
        self.method = method
        self.running = True

    def run(self):
        groups = self.finder.scan_and_get_groups(
            self.directories, 
            method=self.method,
            progress_callback=self.emit_progress,
            stop_check=lambda: not self.running
        )
        self.finished_signal.emit(groups)

    def emit_progress(self, current, total, text):
        self.progress_signal.emit(current, total, text)

    def stop(self):
        self.running = False

class DuplicateExecutionThread(QThread):
    progress_signal = pyqtSignal(int, int, str)
    finished_signal = pyqtSignal(int, int) # moved, errors

    def __init__(self, finder, dest, dry_run):
        super().__init__()
        self.finder = finder
        self.dest = dest
        self.dry_run = dry_run
        self.running = True

    def run(self):
        moved, errors = self.finder.execute_move(
            self.dest, 
            dry_run=self.dry_run, 
            progress_callback=self.emit_progress,
            stop_check=lambda: not self.running
        )
        self.finished_signal.emit(moved, errors)

    def emit_progress(self, current, total, text):
        self.progress_signal.emit(current, total, text)

    def stop(self):
        self.running = False

class DuplicatesWidget(QWidget):
    def __init__(self, settings_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        self.input_dirs = []
        self.finder = DuplicatesFinder()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header_layout = QVBoxLayout()
        title_lbl = QLabel("Duplicate Audio Finder")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #00bcd4;")
        desc_lbl = QLabel("Scans multiple directories to find duplicate audio files based on Metadata 'Title' or File Hash.\n"
                          "Allows you to keep the best quality version and move duplicates to a separate folder.")
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
        input_group = QGroupBox("1. Input Directories (to scan)")
        input_layout = QVBoxLayout()
        self.dir_list = QListWidget()
        input_layout.addWidget(self.dir_list)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Directory")
        add_btn.clicked.connect(self.add_directory)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_directories)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(clear_btn)
        input_layout.addLayout(btn_layout)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # Method
        method_group = QGroupBox("2. Scan Method")
        method_layout = QHBoxLayout()
        self.bg = QButtonGroup()
        
        rb_title = QRadioButton("Title Tag (Best for audiobooks)")
        rb_title.setChecked(True)
        self.bg.addButton(rb_title, 1)
        method_layout.addWidget(rb_title)
        
        rb_hash = QRadioButton("Values Hash (Exact binary match)")
        self.bg.addButton(rb_hash, 2)
        method_layout.addWidget(rb_hash)
        
        rb_name = QRadioButton("Filename (Exact name match)")
        self.bg.addButton(rb_name, 3)
        method_layout.addWidget(rb_name)
        
        method_group.setLayout(method_layout)
        layout.addWidget(method_group)

        # Destination
        dest_group = QGroupBox("3. Destination (Move duplicates here)")
        dest_layout = QHBoxLayout()
        self.dest_edit = QLineEdit()
        self.dest_edit.setPlaceholderText("Select folder to move duplicates into...")
        dest_btn = QPushButton("Browse")
        dest_btn.clicked.connect(self.select_dest)
        dest_layout.addWidget(self.dest_edit)
        dest_layout.addWidget(dest_btn)
        dest_group.setLayout(dest_layout)
        layout.addWidget(dest_group)

        # Settings
        self.dry_run_check = QCheckBox("Dry Run (Simulate move)")
        self.dry_run_check.setChecked(True)
        layout.addWidget(self.dry_run_check)

        # Actions
        action_layout = QHBoxLayout()
        self.scan_btn = QPushButton("Scan for Duplicates")
        self.scan_btn.setStyleSheet("background-color: #00bcd4; color: white; font-weight: bold; padding: 10px;")
        self.scan_btn.clicked.connect(self.start_scan)
        
        self.exec_btn = QPushButton("Move Duplicates")
        self.exec_btn.setEnabled(False)
        self.exec_btn.setStyleSheet("padding: 10px;")
        self.exec_btn.clicked.connect(self.start_execute)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold; padding: 10px;")
        self.stop_btn.clicked.connect(self.stop_process)
        self.stop_btn.setEnabled(False)
        
        action_layout.addWidget(self.scan_btn)
        action_layout.addWidget(self.exec_btn)
        action_layout.addWidget(self.stop_btn)
        layout.addLayout(action_layout)

        # Progress
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        self.status_lbl = QLabel("Ready")
        layout.addWidget(self.status_lbl)

    def add_directory(self):
        d = QFileDialog.getExistingDirectory(self, "Select Directory")
        if d:
            self.input_dirs.append(d)
            self.dir_list.addItem(d)

    def clear_directories(self):
        self.input_dirs = []
        self.dir_list.clear()

    def select_dest(self):
        d = QFileDialog.getExistingDirectory(self, "Select Destination for Duplicates")
        if d:
            self.dest_edit.setText(d)

    def get_selected_method(self):
        mid = self.bg.checkedId()
        if mid == 2: return DuplicateMethod.HASH
        if mid == 3: return DuplicateMethod.FILENAME
        return DuplicateMethod.TITLE

    def start_scan(self):
        if not self.input_dirs:
            QMessageBox.warning(self, "Error", "Add at least one input directory.")
            return

        method = self.get_selected_method()
        self.scan_btn.setEnabled(False)
        self.exec_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_lbl.setText("Scanning...")
        self.progress_bar.setValue(0)
        
        self.scan_thread = DuplicateScanningThread(self.input_dirs, self.finder, method)
        self.scan_thread.progress_signal.connect(self.update_progress)
        self.scan_thread.finished_signal.connect(self.scan_finished)
        self.scan_thread.start()

    def update_progress(self, current, total, text):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_lbl.setText(text)

    def scan_finished(self, groups):
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        count = sum(len(v) for v in groups.values())
        self.status_lbl.setText(f"Scan Complete. Found {len(groups)} groups of duplicates ({count} files total).")
        
        if groups:
            self.finder.auto_plan_keep()
            self.exec_btn.setEnabled(True)
            QMessageBox.information(self, "Scan Complete", f"Found {len(groups)} duplicate sets.\nReview plan not implemented yet, proceeds with auto-selection.")
        else:
            QMessageBox.information(self, "Scan Complete", "No duplicates found.")

    def start_execute(self):
        dest = self.dest_edit.text()
        if not dest:
            QMessageBox.warning(self, "Error", "Select a destination directory.")
            return

        self.scan_btn.setEnabled(False)
        self.exec_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_lbl.setText("Moving duplicates...")
        
        dry_run = self.dry_run_check.isChecked()
        self.exec_thread = DuplicateExecutionThread(self.finder, dest, dry_run)
        self.exec_thread.progress_signal.connect(self.update_progress)
        self.exec_thread.finished_signal.connect(self.execute_finished)
        self.exec_thread.start()

    def stop_process(self):
        if hasattr(self, 'scan_thread') and self.scan_thread.isRunning():
            self.scan_thread.stop()
            self.status_lbl.setText("Stopping Scan...")
        if hasattr(self, 'exec_thread') and self.exec_thread.isRunning():
            self.exec_thread.stop()
            self.status_lbl.setText("Stopping Execution...")
        self.stop_btn.setEnabled(False)

    def execute_finished(self, moved, errors):
        self.scan_btn.setEnabled(True)
        self.exec_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_lbl.setText("Finished.")
        QMessageBox.information(self, "Result", f"Moved: {moved}\nErrors: {errors}")

    def get_dashboard_visibility(self):
        if self.settings_manager:
            # duplicates id is 4
            val = self.settings_manager.get("dashboard_visible_4")
            # Default to True if not set
            if val is None: return True
            return str(val).lower() == 'true'
        return True

    def toggle_dashboard_visibility(self):
        if self.settings_manager:
            state = self.dashboard_toggle.isChecked()
            self.settings_manager.set("dashboard_visible_4", str(state).lower())
