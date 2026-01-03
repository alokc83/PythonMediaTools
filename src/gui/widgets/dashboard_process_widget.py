from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QProgressBar, QPushButton, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal

class DashboardProcessWidget(QFrame):
    """
    A widget representing a single running task on the dashboard.
    Layout:
    ------------------------------------------
    | Tool Name                              |
    | [====================] 45%             |
    | ...processing/File_Name.mp3            |
    |                                 [Show] |
    ------------------------------------------
    """
    # Signal to navigate to the tool
    navigate_signal = pyqtSignal(int)
    # Signal to stop the task (logic handled by orchestrator/tool connection usually)
    # For now, we mainly visualize. 'Stop' might need direct tool connection or orchestrator event.
    
    def __init__(self, task_id, task_name, view_id):
        super().__init__()
        self.task_id = task_id
        self.task_name = task_name
        self.view_id = view_id
        
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            DashboardProcessWidget {
                background-color: #2b2b2b;
                border-radius: 8px;
                border: 1px solid #3d3d3d;
                margin-bottom: 8px;
            }
            QLabel { color: #e0e0e0; }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)
        
        # Row 1: Header (Name only)
        self.name_label = QLabel(self.task_name)
        self.name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        main_layout.addWidget(self.name_label)
        
        # Row 2: Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #424242;
                border-radius: 2px;
                height: 6px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #00bcd4;
                border-radius: 2px;
            }
        """)
        self.progress_bar.setTextVisible(False) # Clean look
        main_layout.addWidget(self.progress_bar)
        
        # Row 3: Log (One liner, truncated)
        self.log_label = QLabel("Initializing...")
        self.log_label.setStyleSheet("color: #9e9e9e; font-size: 12px; font-family: monospace;")
        self.log_label.setWordWrap(False) # Force single line
        self.log_label.setFixedHeight(20) # Fixed height
        main_layout.addWidget(self.log_label)

        # Row 4: Footer (Show Button aligned right)
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        
        self.show_btn = QPushButton("Show")
        self.show_btn.setCursor(Qt.PointingHandCursor)
        self.show_btn.setStyleSheet("""
            QPushButton {
                background-color: #00bcd4;
                color: white;
                border: none;
                padding: 4px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #00acc1; }
        """)
        self.show_btn.clicked.connect(lambda: self.navigate_signal.emit(self.view_id))
        footer_layout.addWidget(self.show_btn)
        
        main_layout.addLayout(footer_layout)

    def update_progress(self, current, total, message):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        
        # Smart Truncation
        # If message is a path or very long, keep the end (filename) and truncate start
        text = str(message)
        if len(text) > 60:
            # Simple truncation approach for now: "...last_part"
            text = "..." + text[-55:]
        
        self.log_label.setText(text)
