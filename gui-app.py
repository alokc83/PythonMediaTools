import sys
import os
import time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QAction, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QProgressBar, QFileDialog, QMessageBox
)
from PyQt5.QtCore import QThread, pyqtSignal
import mutagen

def get_metadata(file_path):
    """Extract album and title metadata from an audio file."""
    try:
        audio = mutagen.File(file_path, easy=True)
        if audio is None:
            return {}
        metadata = {}
        if 'album' in audio:
            metadata['album'] = audio['album'][0]
        if 'title' in audio:
            metadata['title'] = audio['title'][0]
        return metadata
    except Exception:
        return {}

# Worker thread that performs file comparison
class MassCompareThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    current_file_signal = pyqtSignal(str)
    
    def __init__(self, dest, source_folders, parent=None):
        super().__init__(parent)
        self.dest = dest
        self.source_folders = source_folders

    def run(self):
        # Gather all mp3 and m4a files from the destination folder.
        dest_files = []
        for root, _, files in os.walk(self.dest):
            for file in files:
                if file.lower().endswith(('.mp3', '.m4a')):
                    dest_files.append(os.path.join(root, file))
        # Build a list of destination metadata.
        dest_metadata = []
        for file in dest_files:
            meta = get_metadata(file)
            if meta:
                dest_metadata.append((file, meta))
        
        # Gather all mp3 and m4a files from each source folder.
        source_files = []
        for folder in self.source_folders:
            for root, _, files in os.walk(folder):
                for file in files:
                    if file.lower().endswith(('.mp3', '.m4a')):
                        source_files.append(os.path.join(root, file))
        
        total = len(source_files)
        if total == 0:
            self.progress.emit(100)
            self.finished.emit()
            return
        
        # Process each source file.
        for i, file in enumerate(source_files):
            # Emit the current file being processed.
            self.current_file_signal.emit(file)
            meta = get_metadata(file)
            match_found = False
            # Check if a file in the destination has the same album or title.
            if meta:
                for dest_file, dest_meta in dest_metadata:
                    if (('album' in meta and 'album' in dest_meta and meta['album'] == dest_meta['album']) or
                        ('title' in meta and 'title' in dest_meta and meta['title'] == dest_meta['title'])):
                        match_found = True
                        break
            # (Optional) Here you could log the result of the comparison (match_found)
            # Simulate processing time.
            time.sleep(0.1)
            progress_val = int(((i + 1) / total) * 100)
            self.progress.emit(progress_val)
        self.finished.emit()

# Dialog for the "Mass Compare" functionality.
class MassCompareDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mass Compare")
        self.layout = QVBoxLayout()

        # Destination folder selection.
        dest_layout = QHBoxLayout()
        dest_label = QLabel("Destination Folder:")
        self.dest_edit = QLineEdit()
        self.dest_browse = QPushButton("Browse")
        self.dest_browse.clicked.connect(self.browse_destination)
        dest_layout.addWidget(dest_label)
        dest_layout.addWidget(self.dest_edit)
        dest_layout.addWidget(self.dest_browse)
        self.layout.addLayout(dest_layout)

        # Source folders selection.
        self.layout.addWidget(QLabel("Source Folders:"))
        self.source_list = QListWidget()
        self.layout.addWidget(self.source_list)
        self.add_source_button = QPushButton("Add Source Folder")
        self.add_source_button.clicked.connect(self.add_source_folder)
        self.layout.addWidget(self.add_source_button)

        # Button to start the comparison.
        self.compare_button = QPushButton("Compare")
        self.compare_button.clicked.connect(self.start_comparison)
        self.layout.addWidget(self.compare_button)

        # Progress bar to indicate overall progress.
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.layout.addWidget(self.progress_bar)
        
        # Label to display the current file being processed.
        self.current_file_label = QLabel("Currently processing: None")
        self.layout.addWidget(self.current_file_label)

        self.setLayout(self.layout)
        self.thread = None

    def browse_destination(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder:
            self.dest_edit.setText(folder)

    def add_source_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder:
            self.source_list.addItem(folder)

    def start_comparison(self):
        dest = self.dest_edit.text().strip()
        if not dest:
            QMessageBox.warning(self, "Input Error", "Please select a destination folder.")
            return

        source_folders = [self.source_list.item(i).text() for i in range(self.source_list.count())]
        if not source_folders:
            QMessageBox.warning(self, "Input Error", "Please add at least one source folder.")
            return

        # Disable inputs while processing.
        self.compare_button.setEnabled(False)
        self.dest_edit.setEnabled(False)
        self.dest_browse.setEnabled(False)
        self.add_source_button.setEnabled(False)

        # Start the comparison in a separate thread.
        self.thread = MassCompareThread(dest, source_folders)
        self.thread.progress.connect(self.progress_bar.setValue)
        self.thread.current_file_signal.connect(self.update_current_file)
        self.thread.finished.connect(self.comparison_finished)
        self.thread.start()

    def update_current_file(self, filename):
        # Display only the base name of the file.
        self.current_file_label.setText("Currently processing: " + os.path.basename(filename))

    def comparison_finished(self):
        QMessageBox.information(self, "Done", "Mass comparison completed!")
        # Re-enable inputs.
        self.compare_button.setEnabled(True)
        self.dest_edit.setEnabled(True)
        self.dest_browse.setEnabled(True)
        self.add_source_button.setEnabled(True)

# Main window with a menu containing the "Mass Compare" option.
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mass Compare App")
        operations_menu = self.menuBar().addMenu("Operations")
        mass_compare_action = QAction("Mass Compare", self)
        mass_compare_action.triggered.connect(self.open_mass_compare_dialog)
        operations_menu.addAction(mass_compare_action)

    def open_mass_compare_dialog(self):
        dialog = MassCompareDialog(self)
        dialog.exec_()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    mainWin = MainWindow()
    mainWin.resize(600, 400)
    mainWin.show()
    sys.exit(app.exec_())
