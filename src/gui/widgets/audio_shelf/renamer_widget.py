
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QFileDialog, QProgressBar, QMessageBox, QTableWidget, 
    QTableWidgetItem, QHeaderView, QGroupBox, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from src.core.audio_shelf.renamer import TitleRenamer

class RenameScanThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, renamer, dirs, exts):
        super().__init__()
        self.renamer = renamer
        self.dirs = dirs
        self.exts = exts
        self.running = True

    def run(self):
        self.renamer.scan_directories(
            self.dirs, self.exts, 
            lambda msg: self.progress.emit(msg),
            stop_check=lambda: not self.running
        )
        self.progress.emit("Building plan...")
        self.renamer.build_plan(
            lambda i, t, p: self.progress.emit(f"Planning {i}/{t}: {p}"),
            stop_check=lambda: not self.running
        )
        self.finished.emit()

    def stop(self):
        self.running = False

class RenameExecuteThread(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int, int)

    def __init__(self, renamer, dry_run):
        super().__init__()
        self.renamer = renamer
        self.dry_run = dry_run
        self.running = True

    def run(self):
        renamed, errors = self.renamer.execute_rename(
            self.dry_run, 
            lambda i, t, src: self.progress.emit(i, t, f"Renaming {src}"),
            stop_check=lambda: not self.running
        )
        self.finished.emit(renamed, errors)

    def stop(self):
        self.running = False


class RenamerWidget(QWidget):
    def __init__(self, settings_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        self.renamer = TitleRenamer()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header_layout = QVBoxLayout()
        title_lbl = QLabel("Rename Files to Title")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #00bcd4;")
        desc_lbl = QLabel("Automatically renames files to match their internal 'Title' metadata tag.\n"
                          "This helps enforce consistent naming conventions across your library.")
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
        input_group = QGroupBox("Input Directories")
        input_layout = QVBoxLayout()
        self.dir_list = QListWidget()
        input_layout.addWidget(self.dir_list)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Directory")
        add_btn.clicked.connect(self.add_directory)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_directory)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        input_layout.addLayout(btn_layout)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # Settings
        settings_layout = QHBoxLayout()
        self.dry_run_check = QCheckBox("Dry Run")
        self.dry_run_check.setChecked(True)
        settings_layout.addWidget(self.dry_run_check)
        layout.addLayout(settings_layout)

        # Actions
        action_layout = QHBoxLayout()
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self.start_scan)
        
        self.execute_btn = QPushButton("Rename Files")
        self.execute_btn.setEnabled(False)
        self.execute_btn.clicked.connect(self.start_execute)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_process)
        
        action_layout.addWidget(self.scan_btn)
        action_layout.addWidget(self.execute_btn)
        action_layout.addWidget(self.stop_btn)
        layout.addLayout(action_layout)

        # Progress
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Original", "New Path"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

    def add_directory(self):
        d = QFileDialog.getExistingDirectory(self, "Select Directory")
        if d:
            self.dir_list.addItem(d)

    def remove_directory(self):
        row = self.dir_list.currentRow()
        if row >= 0:
            self.dir_list.takeItem(row)

    def start_scan(self):
        dirs = [self.dir_list.item(i).text() for i in range(self.dir_list.count())]
        if not dirs:
            QMessageBox.warning(self, "No Directories", "Please add input directories.")
            return

        self.scan_btn.setEnabled(False)
        self.execute_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setRange(0, 0)
        
        self.scan_thread = RenameScanThread(self.renamer, dirs, {"mp3", "m4a", "m4b"})
        self.scan_thread.progress.connect(self.update_status)
        self.scan_thread.finished.connect(self.scan_finished)
        self.scan_thread.start()

    def update_status(self, msg):
        self.status_label.setText(msg)

    def scan_finished(self):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Scan Complete. Found {len(self.renamer.plan)} files to rename.")
        self.scan_btn.setEnabled(True)
        self.execute_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.populate_table()

    def populate_table(self):
        self.table.setRowCount(0)
        plan = self.renamer.plan
        max_rows = 100
        self.table.setRowCount(min(len(plan), max_rows))
        for i, (src, dst) in enumerate(plan[:max_rows]):
            self.table.setItem(i, 0, QTableWidgetItem(src))
            self.table.setItem(i, 1, QTableWidgetItem(dst))

    def start_execute(self):
        self.execute_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setRange(0, len(self.renamer.plan))
        
        dry_run = self.dry_run_check.isChecked()
        self.exec_thread = RenameExecuteThread(self.renamer, dry_run)
        self.exec_thread.progress.connect(self.update_execution_progress)
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

    def update_execution_progress(self, current, total, msg):
        self.progress_bar.setValue(current)
        self.status_label.setText(msg)

    def execution_finished(self, renamed, errors):
        self.scan_btn.setEnabled(True)
        self.execute_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText(f"Done. Renamed: {renamed}, Errors: {errors}")
        QMessageBox.information(self, "Finished", f"Renamed: {renamed}\nErrors: {errors}")

    def get_dashboard_visibility(self):
        if self.settings_manager:
            # renamer id is 5
            val = self.settings_manager.get("dashboard_visible_5")
            # Default to True if not set
            if val is None: return True
            return str(val).lower() == 'true'
        return True

    def toggle_dashboard_visibility(self):
        if self.settings_manager:
            state = self.dashboard_toggle.isChecked()
            self.settings_manager.set("dashboard_visible_5", str(state).lower())
