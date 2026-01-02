
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QFrame, QButtonGroup, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal

class SidebarWidget(QWidget):
    change_page_signal = pyqtSignal(int)
    open_settings_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.btn_group = QButtonGroup()
        self.btn_group.setExclusive(True)
        self.init_ui()

    def init_ui(self):
        self.setFixedWidth(250)
        self.setStyleSheet("background-color: #2b2b2b; border-right: 1px solid #3d3d3d;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # App Title Area
        title_frame = QFrame()
        title_frame.setFixedHeight(60)
        title_frame.setStyleSheet("background-color: #2b2b2b; border-bottom: 1px solid #3d3d3d;")
        title_layout = QVBoxLayout(title_frame)
        title_label = QLabel("AUDIO TOOLBOX")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #00bcd4; font-weight: bold; font-size: 16px; border: none;")
        title_layout.addWidget(title_label)
        layout.addWidget(title_frame)

        # Navigation Buttons
        self.nav_layout = QVBoxLayout()
        self.nav_layout.setContentsMargins(0, 10, 0, 10)
        self.nav_layout.setSpacing(2)

        self.add_nav_btn("Dashboard", 0, True)
        self.nav_layout.addSpacing(10)
        
        # Section 1: Metadata Tools
        lbl_meta = QLabel("  METADATA TOOLS")
        lbl_meta.setStyleSheet("color: #666; font-size: 11px; font-weight: bold; padding-left: 10px; border: none;")
        self.nav_layout.addWidget(lbl_meta)
        
        self.add_nav_btn("Find Duplicates", 4)
        self.add_nav_btn("Metadata Tagger", 14)
        self.add_nav_btn("Rename to Title", 5)
        self.add_nav_btn("Genre Updater", 11)
        self.add_nav_btn("Mass Compare", 10)
        self.add_nav_btn("ATF Cleaner", 15)
        self.add_nav_btn("Rating Updater", 16)

        self.nav_layout.addSpacing(15)

        # Section 2: File Operations
        lbl_file = QLabel("  FILE OPERATIONS")
        lbl_file.setStyleSheet("color: #666; font-size: 11px; font-weight: bold; padding-left: 10px; border: none;")
        self.nav_layout.addWidget(lbl_file)

        self.add_nav_btn("Flatten to Root", 6)
        self.add_nav_btn("File to Folder", 7)
        self.add_nav_btn("Blinkist Pruner", 8)
        self.add_nav_btn("Unique Copier", 12)
        self.add_nav_btn("Bitrate Mover", 13)

        self.nav_layout.addStretch()
        layout.addLayout(self.nav_layout)
        
        # Bottom area
        bottom_frame = QFrame()
        bottom_layout = QVBoxLayout(bottom_frame)
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings_signal.emit)
        settings_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 12px 20px;
                border: none;
                color: #aaa;
                background: transparent;
            }
            QPushButton:hover {
                color: #fff;
                background-color: #383838;
            }
        """)
        bottom_layout.addWidget(settings_btn)

        # Exit Button
        exit_btn = QPushButton("Exit App")
        exit_btn.clicked.connect(QApplication.instance().quit)
        exit_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 12px 20px;
                border: none;
                color: #aaa;
                background: transparent;
            }
            QPushButton:hover {
                color: #ff5555;
                background-color: #383838;
                font-weight: bold;
            }
        """)
        bottom_layout.addWidget(exit_btn)
        layout.addWidget(bottom_frame)

    def add_nav_btn(self, text, page_id, checked=False):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.clicked.connect(lambda: self.change_page_signal.emit(page_id))
        
        # Styling for selected state indicator
        btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 12px 20px;
                border: none;
                color: #ccc;
                background-color: transparent;
                border-left: 3px solid transparent;
            }
            QPushButton:hover {
                background-color: #333;
                color: #fff;
            }
            QPushButton:checked {
                background-color: #3a3a3a;
                color: #00bcd4;
                border-left: 3px solid #00bcd4;
                font-weight: bold;
            }
        """)
        
        self.btn_group.addButton(btn, page_id)
        self.nav_layout.addWidget(btn)

    def set_active(self, page_id):
        btn = self.btn_group.button(page_id)
        if btn:
            btn.setChecked(True)
