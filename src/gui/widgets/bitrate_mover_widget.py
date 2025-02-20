from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QProgressBar, QTextEdit,
    QFileDialog
)
from PyQt5.QtCore import Qt
from ...core.workers.bitrate_mover_worker import BitrateMoverWorker

class BitrateMoverWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Bitrate Mover Widget - Coming Soon"))
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Source folder selection
        source_layout = QHBoxLayout()
        source_label = QLabel("Source Folder:")
        self.source_edit = QLineEdit()
        source_browse = QPushButton("Browse...")
        source_browse.clicked.connect(self.select_source)
        source_layout.addWidget(source_label)
        source_layout.addWidget(self.source_edit)
        source_layout.addWidget(source_browse)
        layout.addLayout(source_layout)
        
        # Destination folder selection
        dest_layout = QHBoxLayout()
        dest_label = QLabel("Destination Folder:")
        self.dest_edit = QLineEdit()
        dest_browse = QPushButton("Browse...")
        dest_browse.clicked.connect(self.select_destination)
        dest_layout.addWidget(dest_label)
        dest_layout.addWidget(self.dest_edit)
        dest_layout.addWidget(dest_browse)
        layout.addLayout(dest_layout)
        
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
    
    def select_source(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder:
            self.source_edit.setText(folder)
            self.log_message(f"Source folder selected: {folder}")
    
    def select_destination(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder:
            self.dest_edit.setText(folder)
            self.log_message(f"Destination folder selected: {folder}")
    
    def toggle_processing(self):
        if self.worker is None:
            self.start_processing()
        else:
            self.stop_processing()
    
    def start_processing(self):
        source_folder = self.source_edit.text().strip()
        dest_folder = self.dest_edit.text().strip()
        
        if not source_folder or not dest_folder:
            self.log_message("Error: Please select both source and destination folders")
            return
        
        self.worker = BitrateMoverWorker(source_folder, dest_folder)
        self.worker.progress_updated.connect(self.progress_bar.setValue)
        self.worker.log_message.connect(self.log_message)
        self.worker.finished.connect(self.processing_finished)
        
        self.start_button.setText("Stop Processing")
        self.source_edit.setEnabled(False)
        self.dest_edit.setEnabled(False)
        
        self.worker.start()
    
    def stop_processing(self):
        if self.worker:
            self.worker.stop()
            self.log_message("Processing stopped by user")
    
    def processing_finished(self):
        self.worker = None
        self.start_button.setText("Start Processing")
        self.source_edit.setEnabled(True)
        self.dest_edit.setEnabled(True)
        self.log_message("Processing completed")
    
    def log_message(self, message):
        self.console.append(message)
        self.console.verticalScrollBar().setValue(
            self.console.verticalScrollBar().maximum()
        ) 