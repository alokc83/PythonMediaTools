
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFrame, QGridLayout, QScrollArea
)
from PyQt5.QtCore import Qt, pyqtSignal

class DashboardWidget(QWidget):
    # Signals to navigate to specific tool indices
    navigate_signal = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(30)

        # Welcome Section
        welcome_label = QLabel("Welcome to Audio Toolbox")
        welcome_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #ffffff;")
        welcome_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome_label)

        desc_label = QLabel("Professional tools for managing your audio library.")
        desc_label.setStyleSheet("font-size: 16px; color: #cccccc;")
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)

        layout.addSpacing(20)

        # Cards Section
        cards_layout = QGridLayout()
        cards_layout.setSpacing(20)
        
        # Helper to crete action cards
        def create_card(title, desc, tool_idx, row, col):
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background-color: #333333;
                    border-radius: 10px;
                    border: 1px solid #444;
                }
                QFrame:hover {
                    background-color: #404040;
                    border: 1px solid #555;
                }
            """)
            card_layout = QVBoxLayout(card)
            
            t_label = QLabel(title)
            t_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff; background: transparent;")
            card_layout.addWidget(t_label)
            
            d_label = QLabel(desc)
            d_label.setWordWrap(True)
            d_label.setStyleSheet("font-size: 12px; color: #aaa; background: transparent;")
            card_layout.addWidget(d_label)
            
            btn = QPushButton("Open Tool")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda: self.navigate_signal.emit(tool_idx))
            card_layout.addWidget(btn)
            
            cards_layout.addWidget(card, row, col)

        # Row 0
        create_card("Find Duplicates", "Scan folders to find and organize duplicate audio files.", 4, 0, 0)
        create_card("Rename to Title", "Rename mp3/m4b files based on their internal metadata.", 5, 0, 1)
        create_card("Flatten to Root", "Move files from subdirectories into a single root folder.", 6, 0, 2)
        
        # Row 1
        create_card("File to Folder", "Organize loose files into individual folders.", 7, 1, 0)
        create_card("Blinkist Pruner", "Format priority pruning for audiobook libraries.", 8, 1, 1)
        create_card("Settings", "Configure global application defaults.", 99, 1, 2) # 99 for settings/dummy

        layout.addLayout(cards_layout)
        layout.addStretch()
