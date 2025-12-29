import os
import subprocess
import shutil
import sys

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QProgressBar
)
from PyQt5.QtCore import QThread, pyqtSignal

class WorkerThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()

    def __init__(self, source_folder, dest_folder):
        super().__init__()
        self.source_folder = source_folder
        self.dest_folder = dest_folder
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run_command(self, command):
        """
        Runs a command via subprocess.run, logs the command and its stdout and stderr,
        and returns the completed process.
        """
        cmd_str = " ".join(command)
        self.log_signal.emit(f"[CMD] Executing: {cmd_str}")
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.stdout:
                self.log_signal.emit(f"[CMD OUTPUT] {result.stdout.strip()}")
            if result.stderr:
                self.log_signal.emit(f"[CMD ERROR] {result.stderr.strip()}")
            return result
        except Exception as e:
            self.log_signal.emit(f"[CMD EXCEPTION] Error executing {cmd_str}: {e}")
            return None

    def get_bitrate(self, file_path):
        """
        Returns the audio bitrate (in bps) for the given file by calling ffprobe.
        Logs the command and its output.
        """
        command = [
            'ffprobe', '-v', 'error', '-select_streams', 'a:0',
            '-show_entries', 'stream=bit_rate', '-of', 'default=noprint_wrappers=1:nokey=1', file_path
        ]
        result = self.run_command(command)
        if result and result.stdout.strip():
            try:
                return int(result.stdout.strip())
            except ValueError:
                self.log_signal.emit(f"[ERROR] Invalid bitrate value for file {file_path}")
                return 0
        return 0

    def get_identifier(self, file_path):
        """
        Returns an identifier from the file metadata.
        It first tries to get the 'title' tag; if not found, it uses 'album'.
        Logs the command line call and its output.
        """
        command = [
            'ffprobe', '-v', 'error', '-show_entries', 'format_tags=title,album',
            '-of', 'default=noprint_wrappers=1', file_path
        ]
        result = self.run_command(command)
        title = ""
        album = ""
        if result:
            lines = result.stdout.splitlines()
            for line in lines:
                if line.startswith("title="):
                    title = line.split("=", 1)[1].strip()
                elif line.startswith("album="):
                    album = line.split("=", 1)[1].strip()
        ident = title if title else album
        self.log_signal.emit(f"[INFO] Metadata identifier for {os.path.basename(file_path)}: '{ident}'")
        return ident

    def run(self):
        # Build a dictionary mapping metadata identifier -> source file path
        source_map = {}
        self.log_signal.emit("[INFO] Building source file map based on metadata identifiers...")
        for f in os.listdir(self.source_folder):
            src_path = os.path.join(self.source_folder, f)
            if os.path.isfile(src_path):
                ident = self.get_identifier(src_path)
                if ident:
                    source_map[ident] = src_path

        dest_files = [f for f in os.listdir(self.dest_folder)
                      if os.path.isfile(os.path.join(self.dest_folder, f))]
        total_files = len(dest_files)
        if total_files == 0:
            self.log_signal.emit("No files found in the destination folder.")
            self.finished_signal.emit()
            return

        # Ensure "ToDelete" folder exists in destination
        to_delete_folder = os.path.join(self.dest_folder, "ToDelete")
        os.makedirs(to_delete_folder, exist_ok=True)
        self.log_signal.emit(f"Ensured 'ToDelete' folder exists at {to_delete_folder}")

        processed = 0

        for filename in dest_files:
            if not self._is_running:
                self.log_signal.emit("Processing canceled by user.")
                break

            dest_path = os.path.join(self.dest_folder, filename)
            self.log_signal.emit(f"-----\nStarting processing for destination file: {filename}")

            dest_bitrate = self.get_bitrate(dest_path)
            dest_kbps = dest_bitrate / 1000.0 if dest_bitrate else 0
            self.log_signal.emit(f"Destination bitrate for {filename}: {dest_kbps:.2f} kbps")

            dest_identifier = self.get_identifier(dest_path)
            if not dest_identifier:
                self.log_signal.emit(f"No metadata identifier found for {filename}. Skipping matching for this file.")
                processed += 1
                self.progress_signal.emit(processed)
                continue

            if dest_bitrate < 64000:
                self.log_signal.emit(f"Bitrate is less than 64 kbps. Searching for matching source file...")
                source_path = source_map.get(dest_identifier, None)
                if source_path and os.path.isfile(source_path):
                    source_bitrate = self.get_bitrate(source_path)
                    source_kbps = source_bitrate / 1000.0 if source_bitrate else 0
                    self.log_signal.emit(f"Source bitrate for matching file '{dest_identifier}': {source_kbps:.2f} kbps")
                    if source_bitrate == 64000:
                        try:
                            shutil.move(source_path, to_delete_folder)
                            self.log_signal.emit(f"Moved 64kbps version of '{dest_identifier}' to 'ToDelete'.")
                        except Exception as e:
                            self.log_signal.emit(f"Error moving file for '{dest_identifier}': {e}")
                    else:
                        self.log_signal.emit(f"Source file for '{dest_identifier}' does not have a 64kbps bitrate.")
                else:
                    self.log_signal.emit(f"No corresponding source file found for identifier '{dest_identifier}'.")
            else:
                self.log_signal.emit(f"Destination file '{filename}' has acceptable bitrate ({dest_kbps:.2f} kbps).")
            
            self.log_signal.emit(f"Finished processing file: {filename}\n-----")
            processed += 1
            self.progress_signal.emit(processed)

        self.log_signal.emit("Processing complete.")
        self.finished_signal.emit()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Metadata Bitrate Checker and File Mover")
        self.worker = None
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Folder selection
        source_layout = QHBoxLayout()
        source_label = QLabel("Source Folder:")
        self.source_edit = QLineEdit()
        source_browse = QPushButton("Browse...")
        source_browse.clicked.connect(self.select_source)
        source_layout.addWidget(source_label)
        source_layout.addWidget(self.source_edit)
        source_layout.addWidget(source_browse)

        dest_layout = QHBoxLayout()
        dest_label = QLabel("Destination Folder:")
        self.dest_edit = QLineEdit()
        dest_browse = QPushButton("Browse...")
        dest_browse.clicked.connect(self.select_destination)
        dest_layout.addWidget(dest_label)
        dest_layout.addWidget(self.dest_edit)
        dest_layout.addWidget(dest_browse)

        layout.addLayout(source_layout)
        layout.addLayout(dest_layout)

        # Processing button
        self.start_button = QPushButton("Start Processing")
        self.start_button.clicked.connect(self.toggle_processing)
        layout.addWidget(self.start_button)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        layout.addWidget(self.progress_bar)

        # Console output
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)

        self.setLayout(layout)

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

    def log_message(self, msg):
        self.console.append(msg)
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def toggle_processing(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.start_button.setText("Start Processing")
            self.log_message("Cancellation requested.")
        else:
            self.start_processing()

    def start_processing(self):
        source_folder = self.source_edit.text()
        dest_folder = self.dest_edit.text()
        if not source_folder or not dest_folder:
            self.log_message("Please select both source and destination folders.")
            return

        dest_files = [f for f in os.listdir(dest_folder)
                      if os.path.isfile(os.path.join(dest_folder, f))]
        total_files = len(dest_files)
        self.progress_bar.setMaximum(total_files)
        self.progress_bar.setValue(0)
        self.start_button.setText("Cancel Processing")

        self.worker = WorkerThread(source_folder, dest_folder)
        self.worker.log_signal.connect(self.log_message)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(self.processing_finished)
        self.worker.start()

    def processing_finished(self):
        self.start_button.setText("Start Processing")
        self.log_message("All processing complete.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(600, 500)
    window.show()
    sys.exit(app.exec_())
