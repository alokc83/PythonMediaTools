from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QProgressBar, QTextEdit,
    QFileDialog
)
from PyQt5.QtCore import Qt
from ...core.worker import ProcessingWorker

class FileProcessorWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Source folder selection
        source_layout = QHBoxLayout()
        self.source_label = QLabel("Source Folder:")
        self.source_edit = QLineEdit()
        self.source_button = QPushButton("Browse...")
        self.source_button.clicked.connect(self.browse_source)
        source_layout.addWidget(self.source_label)
        source_layout.addWidget(self.source_edit)
        source_layout.addWidget(self.source_button)
        layout.addLayout(source_layout)
        
        # Process control
        control_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Processing")
        self.start_button.clicked.connect(self.toggle_processing)
        control_layout.addWidget(self.start_button)
        layout.addLayout(control_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # Log console
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)
    
    def browse_source(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Source Folder", "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if folder:
            self.source_edit.setText(folder)
            self.log_message(f"Selected source folder: {folder}")
    
    def toggle_processing(self):
        if self.worker is None:
            self.start_processing()
        else:
            self.stop_processing()
    
    def start_processing(self):
        source_folder = self.source_edit.text().strip()
        if not source_folder:
            self.log_message("Error: Please select a source folder")
            return
            
        self.worker = ProcessingWorker(source_folder)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.log_message.connect(self.log_message)
        self.worker.finished.connect(self.processing_finished)
        
        self.start_button.setText("Stop Processing")
        self.worker.start()
    
    def stop_processing(self):
        if self.worker:
            self.worker.stop()
            self.log_message("Processing stopped by user")
    
    def processing_finished(self):
        self.worker = None
        self.start_button.setText("Start Processing")
        self.log_message("Processing completed")
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def log_message(self, message):
        self.console.append(message)
        # Auto-scroll to bottom
        self.console.verticalScrollBar().setValue(
            self.console.verticalScrollBar().maximum()
        ) 