
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QFileDialog, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QMessageBox, QTextEdit, QCheckBox, QLineEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from src.core.audio_shelf.tagger import TaggerEngine
from src.gui.widgets.audio_shelf.organizer_widget import DragDropLineEdit

class TaggerThread(QThread):
    progress_signal = pyqtSignal(int, int, str)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, files, fields_to_update=None, dry_run=False, force_cover=False, providers=None, google_api_key=None):
        super().__init__()
        self.files = files
        self.fields_to_update = fields_to_update or {}
        self.dry_run = dry_run
        self.force_cover = force_cover
        self.providers = providers or ['audnexus']  # Default to audnexus if not specified
        self.engine = TaggerEngine(log_callback=None, google_books_api_key=google_api_key)
        self.running = True
        self.failed_directories = set()  # Track directories where metadata lookup failed

    def run(self):
        total = len(self.files)
        for idx, f in enumerate(self.files):
            if not self.running: break
            
            self.progress_signal.emit(idx + 1, total, f"Processing: {os.path.basename(f)}")
            
            # Check if this file's directory has already failed
            file_dir = os.path.dirname(f)
            if file_dir in self.failed_directories:
                self.log_signal.emit(f"⏭️  SKIPPED: Directory already failed metadata lookup")
                self.log_signal.emit(f"[SKIPPED] Skipping file in failed directory: {os.path.basename(f)}")
                self.log_signal.emit("-" * 50)
                continue
            
            # Pass our signal emitter as the callback for real-time logging, and providers
            # Update engine's log_callback for this specific file
            self.engine.log_callback = self.log_signal.emit
            success, msg = self.engine.process_file(f, fields_to_update=self.fields_to_update, dry_run=self.dry_run, force_cover=self.force_cover, providers=self.providers)
            
            # If metadata lookup failed, mark directory as failed
            if not success:
                # Case 1: No metadata found online
                if "No metadata found online" in msg:
                    self.failed_directories.add(file_dir)
                    self.log_signal.emit(f"📁 Marking directory for skip: {os.path.basename(file_dir)}/ (no metadata)")
                # Case 2: Extremely low confidence (< 0.50) = fundamentally wrong match
                elif "Low Confidence" in msg:
                    # Extract confidence score from message
                    import re
                    match = re.search(r'Low Confidence (\d+\.\d+)', msg)
                    if match:
                        confidence = float(match.group(1))
                        if confidence < 0.50:
                            self.failed_directories.add(file_dir)
                            self.log_signal.emit(f"📁 Marking directory for skip: {os.path.basename(file_dir)}/ (confidence {confidence:.2f} < 0.50)")
            
            status = "SUCCESS" if success else "FAILED"
            self.log_signal.emit(f"[{status}] Final Result: {msg}")
            self.log_signal.emit("-" * 50)
            
        self.finished_signal.emit()

    def stop(self):
        self.running = False


class TagEditorWidget(QWidget):
    def __init__(self, settings_manager=None, orchestrator=None):
        super().__init__()
        self.settings_manager = settings_manager
        self.orchestrator = orchestrator
        self.files = []
        self.task_id = "tag_editor_task" # Simple fixed ID for now, or uuid
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header_layout = QVBoxLayout()
        title_lbl = QLabel("Auto Metadata Tagger")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #00bcd4;")
        desc_lbl = QLabel("Automatically fetches metadata (Title, Author, GENRE, Cover Art) from Google Books.\n"
                          "Enforces Genre updates and preserves existing Cover Art.")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 14px; color: #b0b0b0; margin-bottom: 20px;")
        header_layout.addWidget(title_lbl)
        header_layout.addWidget(desc_lbl)
        
        # Dashboard Visibility Toggle
        self.dashboard_toggle = QCheckBox("Show in Dashboard")
        self.dashboard_toggle.setStyleSheet("font-weight: bold; color: #00bcd4;")
        self.dashboard_toggle.setChecked(self.get_dashboard_visibility())
        self.dashboard_toggle.stateChanged.connect(self.toggle_dashboard_visibility)
        header_layout.addWidget(self.dashboard_toggle)
        
        layout.addLayout(header_layout)

        # Input
        input_group = QGroupBox("Input Directories (comma-separated or multiple select)")
        input_layout = QHBoxLayout()
        self.dir_edit = DragDropLineEdit()
        self.dir_edit.setPlaceholderText("Enter directories separated by commas, or drag & drop")
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_dirs)
        input_layout.addWidget(self.dir_edit)
        input_layout.addWidget(browse_btn)
        
        scan_btn = QPushButton("Scan Files")
        scan_btn.clicked.connect(self.scan_files)
        input_layout.addWidget(scan_btn)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # File List
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(85)  # Reduced further
        self.file_list.setMaximumHeight(200) # Prevent it from dominating
        layout.addWidget(self.file_list)

        # Field Selection
        field_group = QGroupBox("Update Fields (Uncheck to skip)")
        field_group.setStyleSheet("""
            QCheckBox { font-size: 15px; spacing: 8px; }
            QCheckBox::indicator { width: 22px; height: 22px; }
        """)
        field_layout = QVBoxLayout()
        field_layout.setSpacing(4)  # Tight spacing
        
        # Master Select All checkbox
        master_layout = QHBoxLayout()
        self.select_all_check = QCheckBox("Select All / Deselect All")
        self.select_all_check.setTristate(True) # Enable 3-state cycling
        self.select_all_check.setCheckState(Qt.PartiallyChecked) # Default to Partical (Fill Mode)
        self.select_all_check.setStyleSheet("font-weight: bold; color: #00bcd4;")
        self.select_all_check.stateChanged.connect(self.toggle_all_fields)
        master_layout.addWidget(self.select_all_check)
        master_layout.addStretch()
        field_layout.addLayout(master_layout)
        
        # Create checkboxes (more compact)
        self.title_check = QCheckBox("Title")
        self.title_check.setTristate(True)
        self.title_check.setCheckState(Qt.PartiallyChecked)
        
        self.author_check = QCheckBox("Artist/Author")
        self.author_check.setTristate(True)
        self.author_check.setCheckState(Qt.PartiallyChecked)
        
        self.album_check = QCheckBox("Album")
        self.album_check.setTristate(True)
        self.album_check.setCheckState(Qt.PartiallyChecked)
        
        self.album_artist_check = QCheckBox("Album Artist")
        self.album_artist_check.setTristate(True)
        self.album_artist_check.setCheckState(Qt.PartiallyChecked)
        
        self.genre_check = QCheckBox("Genre")
        self.genre_check.setTristate(True)
        self.genre_check.setCheckState(Qt.PartiallyChecked)
        
        self.year_check = QCheckBox("Year")
        self.year_check.setTristate(True)
        self.year_check.setCheckState(Qt.PartiallyChecked)
        
        self.publisher_check = QCheckBox("Publisher")
        self.publisher_check.setTristate(True)
        self.publisher_check.setCheckState(Qt.PartiallyChecked)
        
        self.description_check = QCheckBox("Description/Comments")
        self.description_check.setTristate(True)  # Enable tri-state
        self.description_check.setCheckState(Qt.PartiallyChecked)
        
        self.cover_check = QCheckBox("Cover Art")
        self.cover_check.setTristate(True)  # Enable tri-state
        self.cover_check.setCheckState(Qt.PartiallyChecked)

        self.compilation_check = QCheckBox("Compilation")
        self.compilation_check.setTristate(True)  # Enable tri-state (Checked=True, Unchecked=False, Partial=SmartFalse)
        self.compilation_check.setCheckState(Qt.Unchecked)  # Default: False/Skip (Safer than partial for logic flag)
        
        # Enable Tristate for standard fields (Checked=Overwite, Partial=Fill, Unchecked=Skip)
        # Already set above during init
        
        # Store all field checkboxes for easy access
        # Store all field checkboxes for easy access
        self.field_checkboxes = [
            self.title_check, self.author_check, self.album_check, self.album_artist_check,
            self.genre_check, self.year_check, self.publisher_check,
            self.description_check, self.cover_check, self.compilation_check
        ]
        
        # Five-column layout for better space utilization
        columns_layout = QHBoxLayout()
        
        # Column 1
        col1 = QVBoxLayout()
        col1.setSpacing(14)
        col1.addWidget(self.title_check)
        col1.addWidget(self.author_check)
        col1.addStretch()
        
        # Column 2
        col2 = QVBoxLayout()
        col2.setSpacing(14)
        col2.addWidget(self.album_artist_check)
        col2.addWidget(self.genre_check)
        col2.addStretch()
        
        # Column 3
        col3 = QVBoxLayout()
        col3.setSpacing(14)
        col3.addWidget(self.publisher_check)
        col3.addWidget(self.album_check)  # Moved from Col 1
        col3.addStretch()
        
        # Column 4
        col4 = QVBoxLayout()
        col4.setSpacing(14)
        col4.addWidget(self.description_check)
        col4.addWidget(self.year_check)   # Moved from Col 2
        col4.addStretch()
        
        # Column 5
        col5 = QVBoxLayout()
        col5.setSpacing(14)
        col5.addWidget(self.cover_check)
        col5.addWidget(self.compilation_check)
        col5.addStretch()
        
        columns_layout.addLayout(col1)
        columns_layout.addLayout(col2)
        columns_layout.addLayout(col3)
        columns_layout.addLayout(col4)
        columns_layout.addLayout(col5)
        
        field_layout.addLayout(columns_layout)
        
        field_group.setLayout(field_layout)
        field_group.setMaximumHeight(260)  # Adjusted for 2-column layout
        layout.addWidget(field_group)

        # Options Layout (Horizontal)
        options_layout = QHBoxLayout()
        
        # Force Cover Art Option
        self.force_cover_check = QCheckBox("Force Replace Cover Art")
        self.force_cover_check.setChecked(False)
        self.force_cover_check.setToolTip("If checked, cover art will be downloaded and replaced even if the file already has one.")
        self.force_cover_check.setStyleSheet("font-style: italic; color: #ff5722;")
        options_layout.addWidget(self.force_cover_check)

        # Dry Run Option
        self.dry_run_check = QCheckBox("Dry Run (Preview only)")
        self.dry_run_check.setChecked(True)
        self.dry_run_check.setToolTip("Preview changes in the log without modifying files.")
        self.dry_run_check.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.dry_run_check.stateChanged.connect(self.update_button_text)
        options_layout.addWidget(self.dry_run_check)
        
        options_layout.addStretch()
        layout.addLayout(options_layout)

        # Logs
        log_group = QGroupBox("Process Log")
        log_layout = QVBoxLayout()
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(100)  # Reduced to allow shrinking
        log_layout.addWidget(self.log_area)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Actions
        action_layout = QHBoxLayout()
        self.run_btn = QPushButton("Start Auto-Tagging (Dry Run)")
        self.run_btn.setStyleSheet("background-color: #00bcd4; color: white; font-weight: bold; padding: 10px;")
        self.run_btn.clicked.connect(self.start_tagging)
        self.run_btn.setEnabled(False)
        action_layout.addWidget(self.run_btn)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold; padding: 10px;")
        self.stop_btn.clicked.connect(self.stop_tagging)
        self.stop_btn.setEnabled(False)
        action_layout.addWidget(self.stop_btn)
        
        layout.addLayout(action_layout)

    def browse_dirs(self):
        """Browse to select multiple directories"""
        # Use custom dialog to allow multiple folder selection
        from PyQt5.QtWidgets import QFileDialog
        dialog = QFileDialog(self, "Select Directories")
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        
        # Enable multi-selection in tree view
        file_view = dialog.findChild(QListView, 'listView')
        if file_view:
            file_view.setSelectionMode(QListView.MultiSelection)
        tree_view = dialog.findChild(QTreeView)
        if tree_view:
            tree_view.setSelectionMode(QTreeView.MultiSelection)
        
        if dialog.exec_():
            directories = dialog.selectedFiles()
            if directories:
                self.dir_edit.setText(", ".join(directories))
                self.scan_files()

    def scan_files(self):
        """Scan files from multiple directories (comma-separated)"""
        dir_text = self.dir_edit.text()
        if not dir_text:
            return
        
        # Split by comma and strip whitespace
        directories = [d.strip() for d in dir_text.split(',') if d.strip()]
        
        if not directories:
            return

        self.files = []
        self.file_list.clear()
        
        for directory in directories:
            if not os.path.isdir(directory):
                self.log_area.append(f"⚠️  Skipping invalid directory: {directory}")
                continue
                
            for root, _, files in os.walk(directory):
                for f in files:
                    if f.lower().endswith((".mp3", ".m4a", ".m4b", ".opus")):
                        path = os.path.join(root, f)
                        self.files.append(path)
                        self.file_list.addItem(f)
        
        total_dirs = len(directories)
        self.log_area.append(f"Found {len(self.files)} audio files from {total_dirs} director{'y' if total_dirs == 1 else 'ies'}.")
        if self.files:
            self.run_btn.setEnabled(True)
    
    def toggle_all_fields(self):
        """Toggle all field checkboxes based on Select All checkbox state (3-state)"""
        current_state = self.select_all_check.checkState()
        for checkbox in self.field_checkboxes:
            checkbox.setCheckState(current_state)
    
    def update_button_text(self):
        """Update button text based on dry run checkbox state"""
        if self.dry_run_check.isChecked():
            self.run_btn.setText("Start Auto-Tagging (Dry Run)")
        else:
            self.run_btn.setText("Start Auto-Tagging")

    def start_tagging(self):
        if not self.files: return
        
        # Helper function to map checkbox tri-state to action
        def get_action(checkbox, is_compilation=False):
            state = checkbox.checkState()
            if is_compilation:
                # Compilation: Checked=True(1), Unchecked=False(0), Partial=SmartFalse
                if state == Qt.Checked: return 'write_true'
                elif state == Qt.Unchecked: return 'write_false'
                else: return 'smart_false' 
            else:
                # Standard: Checked=Write, Partial=Fill, Unchecked=Skip
                if state == Qt.Checked: return 'write'
                elif state == Qt.PartiallyChecked: return 'fill'
                else: return 'skip'
        
        # Collect selected fields
        fields_to_update = {
            "title": get_action(self.title_check),
            "author": get_action(self.author_check),
            "album": get_action(self.album_check),
            "album_artist": get_action(self.album_artist_check),
            "genre": get_action(self.genre_check),
            "year": get_action(self.year_check),
            "publisher": get_action(self.publisher_check),
            "description": get_action(self.description_check),
            "cover": get_action(self.cover_check),
            "compilation": get_action(self.compilation_check, is_compilation=True)
        }
        
        dry_run = self.dry_run_check.isChecked()
        force_cover = self.force_cover_check.isChecked()
        
        # Collect selected providers from Settings
        providers = []
        if self.settings_manager:
            if self.settings_manager.get('metadata_use_audnexus', True):
                providers.append('audnexus')
            if self.settings_manager.get('metadata_use_google', True):
                providers.append('google')
        else:
            # Fallback default
            providers = ['audnexus']

        if not providers:
            QMessageBox.warning(self, "No Providers Selected", "Please enable at least one metadata provider in Settings!")
            return
        
        # Collect Google Books API key (from global settings)
        google_api_key = None
        if self.settings_manager:
            google_api_key = self.settings_manager.get('google_api_key')
        
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.log_area.clear()
        
        if dry_run:
            self.log_area.append('<span style="color: #ff9800; font-weight: bold;">🔍 DRY RUN MODE - No files will be modified</span>')
            self.log_area.append("-" * 50)

        # Notify Orchestrator of start
        if self.orchestrator:
            task_name = f"Mass Tagger ({len(self.files)} files)"
            # view_id 14 is Tag Editor in MainWindow
            self.orchestrator.start_task(self.task_id, task_name, 14) 
        
        self.thread = TaggerThread(self.files, fields_to_update, dry_run, force_cover, providers, google_api_key)
        self.thread.progress_signal.connect(self.update_progress)
        self.thread.log_signal.connect(self.log_msg)
        self.thread.finished_signal.connect(self.finished)
        self.thread.start()
        
    def stop_tagging(self):
        if hasattr(self, 'thread') and self.thread.isRunning():
            self.thread.stop()
            self.log_area.append('<span style="color: #ff4444; font-weight: bold;">Stopping...</span>')
            self.stop_btn.setEnabled(False)
            
            # Notify Orchestrator of finish (early stop)
            if self.orchestrator:
                self.orchestrator.finish_task(self.task_id)

    def update_progress(self, current, total, msg):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        
        # Rate limit orchestrator updates to prevent UI freezing
        # Only update every 1% or every 5 items, whichever is smaller, or if just starting/finishing
        should_update = (current == 1) or (current == total) or (current % 5 == 0)
        
        if self.orchestrator and should_update:
            self.orchestrator.report_progress(self.task_id, current, total, msg)
            # Force event loop to process pending events (e.g. repaints) in the main thread
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()

    def log_msg(self, msg):
        msg_str = str(msg)
        # Define styles
        green = 'color: #00e676; font-weight: bold;'
        red = 'color: #ff5252; font-weight: bold;'
        orange = 'color: #ff9800;'
        blue = 'color: #40c4ff;'
        
        lower_msg = msg_str.lower()
        
        # Color Logic
        if "success" in lower_msg or "updated" in lower_msg:
             if "skipped" not in lower_msg: # "Skipped (Already up-to-date)" is not "Success" green usually? 
                 # Actually user said "Success line should be green".
                 # My tagger emits "[SUCCESS]"
                 self.log_area.append(f'<span style="{green}">{msg_str}</span>')
                 return

        if "failed" in lower_msg or "error" in lower_msg or "confidence fail" in lower_msg:
            self.log_area.append(f'<span style="{red}">{msg_str}</span>')
            return
            
        if "skipped" in lower_msg:
             # Make skipped orange/yellow to differentiate from hard errors
             self.log_area.append(f'<span style="{orange}">{msg_str}</span>')
             return

        if "processing:" in lower_msg:
            self.log_area.append(f'<br><span style="{blue}">{msg_str}</span>')
            return

        # Default white
        self.log_area.append(msg_str)

    def finished(self):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        
        if self.orchestrator:
             self.orchestrator.finish_task(self.task_id)
             
        QMessageBox.information(self, "Completed", "Tagging Completed!")

    def get_dashboard_visibility(self):
        if self.settings_manager:
            # tag_editor id is 14
            val = self.settings_manager.get("dashboard_visible_14")
            # Default to True if not set
            if val is None: return True
            return str(val).lower() == 'true'
        return True

    def toggle_dashboard_visibility(self):
        if self.settings_manager:
            state = self.dashboard_toggle.isChecked()
            self.settings_manager.set("dashboard_visible_14", str(state).lower())
