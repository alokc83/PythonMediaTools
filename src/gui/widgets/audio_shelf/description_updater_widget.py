from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QFileDialog, QGroupBox, QProgressBar, QMessageBox, QCheckBox, QTextEdit
)
import os
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from src.core.audio_shelf.description_updater import DescriptionUpdaterEngine

class UpdateWorker(QThread):
    progress_signal = pyqtSignal(int, int) # current, total
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, directories, engine):
        super().__init__()
        self.directories = directories
        self.engine = engine
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
        self.controller = parent 
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
                    if self.controller:
                        self.controller.add_directory_path(path)
            event.accept()

class DescriptionUpdaterWidget(QWidget):
    def __init__(self, settings_manager=None, orchestrator=None):
        super().__init__()
        self.settings_manager = settings_manager
        self.orchestrator = orchestrator
        self.task_id = "description_updater_task"
        self.directories = []
        self.engine = DescriptionUpdaterEngine(settings_manager=self.settings_manager)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header
        header_lbl = QLabel("Description Updater")
        header_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #b388ff;") # Purple theme
        layout.addWidget(header_lbl)
        
        # Dashboard Visibility Toggle (ID 17)
        self.dashboard_toggle = QCheckBox("Show in Dashboard")
        self.dashboard_toggle.setStyleSheet("font-weight: bold; color: #b388ff; margin-bottom: 10px;")
        self.dashboard_toggle.setChecked(self.get_dashboard_visibility())
        self.dashboard_toggle.stateChanged.connect(self.toggle_dashboard_visibility)
        layout.addWidget(self.dashboard_toggle)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        desc = QLabel(
            "Batch update audio files with fresh descriptions from Audible/Google.\n"
            "Feature: Preserves existing 'Rating' headers in comments, appends new description."
        )
        desc.setStyleSheet("color: #b0b0b0; margin-bottom: 5px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Input List
        input_group = QGroupBox("Directories to Update (Drag & Drop Supported)")
        input_layout = QHBoxLayout() 
        
        self.dir_list = DragDropListWidget(self)
        self.dir_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.dir_list.setMaximumHeight(150)
        input_layout.addWidget(self.dir_list, 1) 
        
        btn_layout = QVBoxLayout() 
        add_btn = QPushButton("Add Listing")
        add_btn.clicked.connect(self.add_directory)
        
        clear_btn = QPushButton("Clear List")
        clear_btn.clicked.connect(self.clear_list)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch() 
        input_layout.addLayout(btn_layout)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # Log Area
        log_group = QGroupBox("Process Log")
        log_layout = QVBoxLayout()
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: monospace; font-size: 11px; background-color: #1e1e1e; color: #d4d4d4;")
        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group, 1) 

        # Action Buttons
        action_layout = QHBoxLayout()
        self.run_btn = QPushButton("Start Update")
        self.run_btn.setStyleSheet("background-color: #b388ff; color: white; font-weight: bold; padding: 10px 20px; font-size: 14px;")
        self.run_btn.clicked.connect(self.start_update)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold; padding: 10px;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_update)
        
        action_layout.addStretch()
        action_layout.addWidget(self.run_btn)
        action_layout.addWidget(self.stop_btn)
        layout.addLayout(action_layout) 

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
        
        # Orchestrator Start
        if self.orchestrator:
             task_name = f"Description Updater ({len(self.directories)} items)"
             # view_id 17 is Description Updater
             self.orchestrator.start_task(self.task_id, task_name, 17)
        
        self.worker.start()

    def stop_update(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.terminate() 
            self.append_log("Process stopped by user.")
            
            if self.orchestrator:
                self.orchestrator.finish_task(self.task_id)
                
            self.finished()

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        
        if self.orchestrator:
            self.orchestrator.report_progress(self.task_id, current, total, f"Processing item {current}/{total}")
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()

    def append_log(self, text):
        color = "#d4d4d4" 
        if "Merged Metadata" in text:
            color = "#00ff00" 
        elif "Updated" in text:
            color = "#b388ff" 
        elif "Error" in text:
            color = "#ff5555" 
        elif "Audnexus" in text:
            color = "#00bcd4" 
            
        html = f'<span style="color: {color};">{text}</span>'
        self.log_view.append(html)

    def finished(self):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.append_log("Done.")
        
        if self.orchestrator:
            self.orchestrator.finish_task(self.task_id)

    def get_dashboard_visibility(self):
        if self.settings_manager:
            # ID 17
            val = self.settings_manager.get("dashboard_visible_17")
            if val is None: return True
            return str(val).lower() == 'true'
        return True

    def toggle_dashboard_visibility(self):
        if self.settings_manager:
            state = self.dashboard_toggle.isChecked()
            self.settings_manager.set("dashboard_visible_17", str(state).lower())
