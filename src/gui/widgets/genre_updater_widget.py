from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QProgressBar, QTextEdit,
    QFileDialog, QCheckBox
)
from PyQt5.QtCore import Qt
from ...core.workers.genre_updater_worker import GenreUpdaterWorker

class GenreUpdaterWidget(QWidget):
    def __init__(self, settings_manager):
        super().__init__()
        self.worker = None
        self.settings_manager = settings_manager
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Folder selection
        folder_layout = QHBoxLayout()
        folder_label = QLabel("Source Folder:")
        self.folder_edit = QLineEdit()
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_folder)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(self.browse_button)
        layout.addLayout(folder_layout)
        
        # API Key input
        api_layout = QHBoxLayout()
        api_label = QLabel("Google API Key:")
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setText(self.settings_manager.get('google_api_key', ''))
        self.api_key_edit.setReadOnly(True)
        api_layout.addWidget(api_label)
        api_layout.addWidget(self.api_key_edit)
        layout.addLayout(api_layout)
        
        # Force cover update checkbox
        self.force_cover_checkbox = QCheckBox("Force Cover Update")
        layout.addWidget(self.force_cover_checkbox)
        
        # Control buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Processing")
        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.start_button.clicked.connect(self.toggle_processing)
        self.pause_button.clicked.connect(self.toggle_pause)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.pause_button)
        layout.addLayout(button_layout)
        
        # API Counter
        self.api_count_label = QLabel("API Calls: 0")
        layout.addWidget(self.api_count_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # Console output
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)
    
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.folder_edit.setText(folder)
            self.log_message(f"Selected folder: {folder}")
    
    def toggle_processing(self):
        if self.worker is None:
            self.start_processing()
        else:
            self.stop_processing()
    
    def toggle_pause(self):
        if self.worker and hasattr(self.worker, '_paused'):
            if self.worker._paused:
                self.worker.resume()
                self.pause_button.setText("Pause")
                self.log_message("Processing resumed")
            else:
                self.worker.pause()
                self.pause_button.setText("Resume")
                self.log_message("Processing paused")
    
    def start_processing(self):
        folder = self.folder_edit.text().strip()
        api_key = self.settings_manager.get('google_api_key', '').strip()
        
        if not folder:
            self.log_message("Error: Please select a folder")
            return
        if not api_key:
            self.log_message("Error: Please set the Google API key in Settings")
            return
        
        self.worker = GenreUpdaterWorker(
            folder, 
            api_key, 
            force_cover=self.force_cover_checkbox.isChecked()
        )
        self.worker.progress_updated.connect(self.progress_bar.setValue)
        self.worker.log_message.connect(self.log_message)
        self.worker.api_count_signal.connect(self.update_api_count)
        self.worker.finished.connect(self.processing_finished)
        
        self.start_button.setText("Stop Processing")
        self.pause_button.setEnabled(True)
        self.browse_button.setEnabled(False)
        self.api_key_edit.setEnabled(False)
        
        self.worker.start()
    
    def stop_processing(self):
        if self.worker:
            self.worker.cancel()
            self.log_message("Processing stopped by user")
    
    def processing_finished(self):
        self.worker = None
        self.start_button.setText("Start Processing")
        self.pause_button.setEnabled(False)
        self.pause_button.setText("Pause")
        self.browse_button.setEnabled(True)
        self.api_key_edit.setEnabled(True)
        self.log_message("Processing completed")
    
    def update_api_count(self, count):
        self.api_count_label.setText(f"API Calls: {count}")
    
    def log_message(self, message):
        self.console.append(message)
        self.console.verticalScrollBar().setValue(
            self.console.verticalScrollBar().maximum()
        ) 