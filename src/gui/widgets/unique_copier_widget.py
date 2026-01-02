from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QProgressBar, QTextEdit,
    QFileDialog, QListWidget, QCheckBox
)
from PyQt5.QtCore import Qt
from ...core.workers.unique_copier_worker import UniqueCopierWorker

class UniqueFileCopierWidget(QWidget):
    def __init__(self, settings_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        self.worker = None
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header & Toggle
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Unique File Copier"))
        header_layout.addStretch()
        
        self.dashboard_toggle = QCheckBox("Show in Dashboard")
        self.dashboard_toggle.setChecked(self.get_dashboard_visibility())
        self.dashboard_toggle.stateChanged.connect(self.toggle_dashboard_visibility)
        header_layout.addWidget(self.dashboard_toggle)
        layout.addLayout(header_layout)
        
        # Destination folder selection
        dest_layout = QHBoxLayout()
        dest_label = QLabel("Destination Folder:")
        self.dest_edit = QLineEdit()
        dest_browse = QPushButton("Browse")
        dest_browse.clicked.connect(self.browse_dest)
        dest_layout.addWidget(dest_label)
        dest_layout.addWidget(self.dest_edit)
        dest_layout.addWidget(dest_browse)
        layout.addLayout(dest_layout)
        
        # Source folders list
        self.source_list = QListWidget()
        layout.addWidget(QLabel("Source Folders:"))
        layout.addWidget(self.source_list)
        
        # Add source button
        self.add_source_button = QPushButton("Add Source Folder")
        self.add_source_button.clicked.connect(self.add_source_folder)
        layout.addWidget(self.add_source_button)
        
        # Start/Cancel button
        self.start_button = QPushButton("Start Processing")
        self.start_button.clicked.connect(self.toggle_processing)
        layout.addWidget(self.start_button)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # Console output
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)
    
    def browse_dest(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder:
            self.dest_edit.setText(folder)
            self.log_message(f"Selected destination folder: {folder}")
    
    def add_source_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder:
            self.source_list.addItem(folder)
            self.log_message(f"Added source folder: {folder}")
    
    def toggle_processing(self):
        if self.worker is None:
            self.start_processing()
        else:
            self.stop_processing()
    
    def start_processing(self):
        dest_folder = self.dest_edit.text().strip()
        if not dest_folder:
            self.log_message("Error: Please select a destination folder")
            return
        
        source_folders = [
            self.source_list.item(i).text() 
            for i in range(self.source_list.count())
        ]
        if not source_folders:
            self.log_message("Error: Please add at least one source folder")
            return
        
        self.worker = UniqueCopierWorker(dest_folder, source_folders)
        self.worker.progress_updated.connect(self.progress_bar.setValue)
        self.worker.log_message.connect(self.log_message)
        self.worker.finished.connect(self.processing_finished)
        
        self.start_button.setText("Stop Processing")
        self.dest_edit.setEnabled(False)
        self.add_source_button.setEnabled(False)
        
        self.worker.start()
    
    def stop_processing(self):
        if self.worker:
            self.worker.stop()
            self.log_message("Processing stopped by user")
    
    def processing_finished(self):
        self.worker = None
        self.start_button.setText("Start Processing")
        self.dest_edit.setEnabled(True)
        self.add_source_button.setEnabled(True)
        self.log_message("Processing completed")
    
    def log_message(self, message):
        self.console.append(message)
        self.console.verticalScrollBar().setValue(
            self.console.verticalScrollBar().maximum()
        )

    def get_dashboard_visibility(self):
        if self.settings_manager:
            # unique copier id is 12
            val = self.settings_manager.get("dashboard_visible_12")
            if val is None: return True
            return str(val).lower() == 'true'
        return True

    def toggle_dashboard_visibility(self):
        if self.settings_manager:
            state = self.dashboard_toggle.isChecked()
            self.settings_manager.set("dashboard_visible_12", str(state).lower()) 