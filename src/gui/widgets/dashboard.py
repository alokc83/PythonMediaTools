from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFrame, QGridLayout, QScrollArea, QProgressBar, QGraphicsOpacityEffect
)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from src.gui.widgets.dashboard_process_widget import DashboardProcessWidget

class DashboardWidget(QWidget):
    # Signals to navigate to specific tool indices
    navigate_signal = pyqtSignal(int)

    def __init__(self, orchestrator=None, settings_manager=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.settings_manager = settings_manager
        
        # Map task_id -> (progressBar, logLabel) (Current UI widgets)
        self.active_card_elements = {} 
        # Map view_id -> (progressBar, logLabel) (Lookup for new cards)
        self.card_ui_map = {}
        
        # State Persistence: { task_id : { 'view_id': int, 'name': str, 'progress': int, 'total': int, 'msg': str } }
        self.active_task_state = {}
        
        # Definitions of all available tools
        self.tool_definitions = [
            # Row 0
            {"title": "Find Duplicates", "desc": "Scan folders to find and organize duplicate audio files.", "id": 4, "key": "duplicates"},
            {"title": "Rename to Title", "desc": "Rename mp3/m4b files based on their internal metadata.", "id": 5, "key": "renamer"},
            {"title": "Flatten to Root", "desc": "Move files from subdirectories into a single root folder.", "id": 6, "key": "flattener"},
            # Row 1
            {"title": "File to Folder", "desc": "Organize loose files into individual folders.", "id": 7, "key": "organizer"},
            {"title": "Blinkist Pruner", "desc": "Format priority pruning for audiobook libraries.", "id": 8, "key": "pruner"},
            {"title": "Tag Editor", "desc": "Auto-tag MP3/M4B files using Audnexus/Google Books.", "id": 14, "key": "tag_editor"},
            # Row 2
            {"title": "ATF Cleaner", "desc": "Recursively delete .atf metadata cache files.", "id": 15, "key": "atf_cleaner"},
            {"title": "Rating Updater", "desc": "Update ratings from user metadata to file tags.", "id": 16, "key": "rating_updater"},
            {"title": "Description Updater", "desc": "Scrape and update book descriptions to Comment tag.", "id": 17, "key": "desc_updater"},
            {"title": "Settings", "desc": "Configure global application defaults.", "id": 99, "key": "settings"}
        ]
        
        self.init_ui()
        
        if self.orchestrator:
             self.orchestrator.task_added.connect(self.on_task_added)
             self.orchestrator.task_progress.connect(self.on_task_progress)
             self.orchestrator.task_finished.connect(self.on_task_finished)
             self.orchestrator.task_log.connect(self.on_task_log)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Scroll Area for the whole dashboard
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        content_widget = QWidget()
        self.layout = QVBoxLayout(content_widget)
        self.layout.setContentsMargins(40, 40, 40, 40)
        self.layout.setSpacing(30)
        
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # Welcome Section
        welcome_label = QLabel("Welcome to Audio Toolbox")
        welcome_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #ffffff;")
        welcome_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(welcome_label)

        desc_label = QLabel("Professional tools for managing your audio library.")
        desc_label.setStyleSheet("font-size: 16px; color: #cccccc;")
        desc_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(desc_label)

        self.layout.addSpacing(20)

        # Cards Section (Container)
        self.cards_container = QWidget()
        self.cards_grid = QGridLayout(self.cards_container)
        self.cards_grid.setSpacing(20)
        self.layout.addWidget(self.cards_container)
        
        self.layout.addStretch()
        
        # Initial Grid Build
        self.refresh_grid()

    def showEvent(self, event):
        """Refresh logic when dashboard is shown to pick up setting changes"""
        self.refresh_grid()
        super().showEvent(event)

    def refresh_grid(self):
        # Clear existing items
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        self.card_ui_map = {}
        self.active_card_elements = {} # Clear old widget refs
        
        # Filter visible tools
        row = 0
        col = 0
        max_cols = 3
        
        for tool in self.tool_definitions:
            # Check settings (Default True)
            key = f"dashboard_visible_{tool['id']}"
            is_visible = True
            if self.settings_manager:
                val = self.settings_manager.get(key)
                if val is not None:
                     is_visible = str(val).lower() == 'true'
            
            if is_visible:
                self.create_card(tool['title'], tool['desc'], tool['id'], row, col)
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
        
        # Restore active tasks state to new widgets
        for task_id, state in self.active_task_state.items():
            view_id = state['view_id']
            if view_id in self.card_ui_map:
                p_bar, l_label = self.card_ui_map[view_id]
                
                # Restore connections
                self.active_card_elements[task_id] = (p_bar, l_label)
                
                # Restore visuals
                p_bar.setVisible(True)
                p_bar.setMaximum(state.get('total', 100))
                p_bar.setValue(state.get('progress', 0))
                
                l_label.setVisible(True)
                l_label.setText(state.get('msg', 'Running...'))
                l_label.setStyleSheet("color: #00bcd4; font-size: 11px; font-family: monospace; background: transparent; border: none;")

    def create_card(self, title, desc, tool_idx, row, col):
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
        card_layout.setSpacing(8)
        
        # Title
        t_label = QLabel(title)
        t_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff; background: transparent; border: none;")
        t_label.setFixedHeight(30) # Fixed height
        t_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        card_layout.addWidget(t_label)
        
        # Description
        d_label = QLabel(desc)
        d_label.setWordWrap(True)
        d_label.setStyleSheet("font-size: 12px; color: #aaa; background: transparent; border: none;")
        d_label.setFixedHeight(40) # Fixed height
        card_layout.addWidget(d_label)
        
        # Embedded Progress Section
        p_bar = QProgressBar()
        p_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #222;
                border-radius: 2px;
                height: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #00bcd4;
                border-radius: 2px;
            }
        """)
        p_bar.setTextVisible(False)
        p_bar.setVisible(False)
        card_layout.addWidget(p_bar)
        
        l_label = QLabel("Ready")
        l_label.setStyleSheet("color: #00bcd4; font-size: 11px; font-family: monospace; background: transparent; border: none;")
        l_label.setVisible(False)
        l_label.setFixedHeight(15)
        card_layout.addWidget(l_label)
        
        self.card_ui_map[tool_idx] = (p_bar, l_label)
        
        btn = QPushButton("Open Tool")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #00bcd4;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #00acc1; }
        """)
        btn.clicked.connect(lambda: self.navigate_signal.emit(tool_idx))
        card_layout.addWidget(btn)
        
        self.cards_grid.addWidget(card, row, col)

    def on_task_added(self, task_id, task_name, view_id):
        # Update State
        self.active_task_state[task_id] = {
            'view_id': view_id,
            'name': task_name,
            'progress': 0,
            'total': 0,
            'msg': 'Starting...'
        }
        
        # Look up UI and bind
        if view_id in self.card_ui_map:
            p_bar, l_label = self.card_ui_map[view_id]
            
            p_bar.setVisible(True)
            p_bar.setValue(0)
            l_label.setVisible(True)
            l_label.setText("Starting...")
            l_label.setStyleSheet("color: #00bcd4; font-size: 11px; font-family: monospace; background: transparent; border: none;")
            
            self.active_card_elements[task_id] = (p_bar, l_label)

    def on_task_progress(self, task_id, current, total, message):
        # Update State
        if task_id in self.active_task_state:
            self.active_task_state[task_id].update({
                'progress': current,
                'total': total,
                'msg': message
            })

        # Update UI
        if task_id in self.active_card_elements:
            p_bar, l_label = self.active_card_elements[task_id]
            try:
                p_bar.setMaximum(total)
                p_bar.setValue(current)
                
                text = str(message)
                if len(text) > 40:
                    text = "..." + text[-35:]
                l_label.setText(text)
            except RuntimeError:
                pass

    def on_task_log(self, task_id, message):
        # Logic same as progress, usually
        # Actually better to separate
        if task_id in self.active_task_state:
            self.active_task_state[task_id]['msg'] = message
            
        if task_id in self.active_card_elements:
             _, l_label = self.active_card_elements[task_id]
             try:
                text = str(message)
                if len(text) > 40:
                    text = "..." + text[-35:]
                l_label.setText(text)
             except RuntimeError:
                pass

    def on_task_finished(self, task_id):
        # Clear State
        if task_id in self.active_task_state:
            self.active_task_state.pop(task_id)

        if task_id in self.active_card_elements:
            p_bar, l_label = self.active_card_elements.pop(task_id)
            try:
                p_bar.setValue(p_bar.maximum())
                l_label.setText("Done")
                l_label.setStyleSheet("color: #00e676; font-size: 11px; font-family: monospace; background: transparent; border: none;")
            except RuntimeError:
                pass
