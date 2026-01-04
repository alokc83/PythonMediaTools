import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QProgressBar, QTextEdit,
    QFileDialog, QCheckBox, QGroupBox, QGridLayout,
    QMessageBox, QListWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from ...core.empty_cleaner import JunkCleaner

class FileDropListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DropOnly)
        self.setStyleSheet("QListWidget { border: 1px solid #444; background: #222; color: #ccc; }")

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
                if os.path.exists(path) and os.path.isdir(path):
                    # Check duplicates
                    existing = [self.item(i).text() for i in range(self.count())]
                    if path not in existing:
                        self.addItem(path)
            event.accept()
        else:
            event.ignore()
            
class EmptyFolderCleanerWidget(QWidget):
    def __init__(self, settings_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        self.cleaner = JunkCleaner()
        self.operations = [] # Store scan results
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header 
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<h2>Empty Folder & Junk Cleaner</h2>"))
        header_layout.addStretch()
        
        self.dashboard_toggle = QCheckBox("Show in Dashboard")
        self.dashboard_toggle.setChecked(self.get_dashboard_visibility())
        self.dashboard_toggle.stateChanged.connect(self.toggle_dashboard_visibility)
        header_layout.addWidget(self.dashboard_toggle)
        layout.addLayout(header_layout)
        
        # Section 1: Target Directories (List)
        target_group = QGroupBox("Target Directories (Drag & Drop Supported)")
        target_layout = QVBoxLayout()
        
        self.target_list = FileDropListWidget()
        target_layout.addWidget(self.target_list)
        
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add Folder")
        self.btn_add.clicked.connect(self.browse_target)
        self.btn_clear = QPushButton("Clear List")
        self.btn_clear.clicked.connect(self.target_list.clear)
        
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_clear)
        target_layout.addLayout(btn_layout)
        
        target_group.setLayout(target_layout)
        layout.addWidget(target_group)
        
        # Section 2: Junk Type Selection
        junk_group = QGroupBox("Select Junk Files to Delete (and subsequently empty folders)")
        junk_layout = QVBoxLayout()
        
        self.junk_checkboxes = {}
        
        # Categories
        self.create_category(junk_layout, "Metadata & Text", [".txt", ".nfo", ".log", ".sfv", ".md", ".dat"])
        self.create_category(junk_layout, "System & Temp", [".tmp", ".bak", ".ds_store", "thumbs.db", ".url", ".webloc"])
        self.create_category(junk_layout, "Images", [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"])
        self.create_category(junk_layout, "Playlists", [".m3u", ".m3u8", ".pls", ".cue"])
        self.create_category(junk_layout, "Audio (Review Carefully!)", [".mp3", ".m4a", ".m4b", ".flac", ".opus"], default_checked=False)
        
        # Select All / None Buttons
        btn_layout_junk = QHBoxLayout()
        self.btn_select_safe = QPushButton("Select Safe Junk")
        self.btn_select_safe.clicked.connect(self.select_safe_junk)
        self.btn_select_none = QPushButton("Select None")
        self.btn_select_none.clicked.connect(self.select_none)
        btn_layout_junk.addWidget(self.btn_select_safe)
        btn_layout_junk.addWidget(self.btn_select_none)
        btn_layout_junk.addStretch()
        junk_layout.addLayout(btn_layout_junk)
        
        junk_group.setLayout(junk_layout)
        layout.addWidget(junk_group)
        
        # Section 3: Actions
        action_layout = QHBoxLayout()
        self.btn_scan = QPushButton("Step 1: Scan & Preview")
        self.btn_scan.clicked.connect(self.scan_directory)
        self.btn_delete = QPushButton("Step 2: Delete Selected Items")
        self.btn_delete.clicked.connect(self.delete_items)
        self.btn_delete.setEnabled(False) # Disabled until scan
        self.btn_delete.setStyleSheet("background-color: #ffcccc; color: red; font-weight: bold;")
        
        action_layout.addWidget(self.btn_scan)
        action_layout.addWidget(self.btn_delete)
        layout.addLayout(action_layout)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # Console/Preview Output
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)
        
        # Initial Selection
        self.select_safe_junk()

    def create_category(self, parent_layout, title, extensions, default_checked=True):
        cat_label = QLabel(f"<b>{title}</b>")
        parent_layout.addWidget(cat_label)
        
        grid = QGridLayout()
        col_count = 5
        for i, ext in enumerate(extensions):
            cb = QCheckBox(ext)
            cb.setChecked(default_checked)
            grid.addWidget(cb, i // col_count, i % col_count)
            self.junk_checkboxes[ext] = cb
            
        parent_layout.addLayout(grid)

    def select_safe_junk(self):
        # Select everything EXCEPT Audio
        unsafe = {".mp3", ".m4a", ".m4b", ".flac", ".opus"}
        for ext, cb in self.junk_checkboxes.items():
            cb.setChecked(ext not in unsafe)

    def select_none(self):
        for cb in self.junk_checkboxes.values():
            cb.setChecked(False)

    def browse_target(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Target Library")
        if folder:
            # Add to list if not exists
            existing = [self.target_list.item(i).text() for i in range(self.target_list.count())]
            if folder not in existing:
                self.target_list.addItem(folder)
                self.log(f"Added target: {folder}")

    def get_selected_junk_extensions(self):
        selected = set()
        for ext, cb in self.junk_checkboxes.items():
            if cb.isChecked():
                selected.add(ext.lower())
        return selected
        
    def get_target_roots(self):
        return [self.target_list.item(i).text() for i in range(self.target_list.count())]

    def scan_directory(self):
        roots = self.get_target_roots()
        if not roots:
            self.log("Please add at least one target folder.")
            return
            
        junk_exts = self.get_selected_junk_extensions()
        if not junk_exts:
            self.log("Please select at least one junk file type.")
            return
            
        self.log(f"Scanning {len(roots)} folders...")
        self.progress_bar.setRange(0, 0) # Indeterminate
        
        self.thread = ScanThread(self.cleaner, roots, junk_exts)
        self.thread.finished.connect(self.scan_finished)
        self.thread.start()
        self.btn_scan.setEnabled(False)

    def scan_finished(self, operations):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.btn_scan.setEnabled(True)
        self.operations = operations
        
        if not operations:
            self.log("Scan complete. No junk files or empty folders found.")
            self.btn_delete.setEnabled(False)
        else:
            count_files = sum(1 for op in operations if op[0] == 'file')
            count_dirs = sum(1 for op in operations if op[0] == 'dir')
            self.log(f"Scan complete. Found {count_files} files and {count_dirs} folders to delete.")
            self.log("-" * 40)
            
            # Show preview
            preview_text = ""
            for op_type, path in operations[:100]: # Limit preview
                 icon = "📄" if op_type == 'file' else "vd"
                 preview_text += f"{icon} {op_type.upper()}: {path}\n"
            
            if len(operations) > 100:
                preview_text += f"... and {len(operations) - 100} more items."
                
            self.console.setText(preview_text)
            self.btn_delete.setEnabled(True)

    def delete_items(self):
        if not self.operations:
            return
            
        count = len(self.operations)
        
        reply = QMessageBox.question(
            self, "Confirm Permanent Deletion",
            f"Are you sure you want to PERMANENTLY delete {count} items?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.log("Starting deletion...")
            self.progress_bar.setRange(0, count)
            self.thread = DeleteThread(self.cleaner, self.operations)
            self.thread.progress.connect(self.progress_bar.setValue)
            self.thread.finished.connect(self.delete_finished)
            self.thread.start()
            self.btn_delete.setEnabled(False)
            self.btn_scan.setEnabled(False)

    def delete_finished(self, success_count):
        self.btn_scan.setEnabled(True)
        self.btn_delete.setEnabled(False)
        self.operations = []
        self.log(f"Deletion complete. Successfully removed {success_count} items.")
        QMessageBox.information(self, "Complete", f"Deleted {success_count} items.")

    def log(self, msg):
        self.console.append(msg)
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def get_dashboard_visibility(self):
        if self.settings_manager:
            # ID 18 for Empty Folder Cleaner
            val = self.settings_manager.get("dashboard_visible_18")
            if val is None: return True
            return str(val).lower() == 'true'
        return True

    def toggle_dashboard_visibility(self):
        if self.settings_manager:
            state = self.dashboard_toggle.isChecked()
            self.settings_manager.set("dashboard_visible_18", str(state).lower())

# Worker Threads

class ScanThread(QThread):
    finished = pyqtSignal(list)
    
    def __init__(self, cleaner, roots, junk_exts):
        super().__init__()
        self.cleaner = cleaner
        self.roots = roots
        self.junk_exts = junk_exts
        
    def run(self):
        all_ops = []
        for root in self.roots:
             ops = self.cleaner.scan_directory(root, self.junk_exts)
             all_ops.extend(ops)
        self.finished.emit(all_ops)

class DeleteThread(QThread):
    finished = pyqtSignal(int)
    progress = pyqtSignal(int)
    
    def __init__(self, cleaner, operations):
        super().__init__()
        self.cleaner = cleaner
        self.operations = operations
        
    def run(self):
        success_count, total = self.cleaner.execute_operations(
            self.operations, 
            progress_callback=lambda idx, tot: self.progress.emit(idx)
        )
        self.finished.emit(success_count)
