
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QAction
)
from PyQt5.QtCore import Qt

from src.core.settings_manager import SettingsManager
from src.gui.dialogs.settings_dialog import SettingsDialog

# New UI Components
from src.gui.widgets.sidebar import SidebarWidget
from src.gui.widgets.dashboard import DashboardWidget

# Legacy Tools
from src.gui.widgets.mass_compare_widget import MassCompareWidget
from src.gui.widgets.genre_updater_widget import GenreUpdaterWidget
from src.gui.widgets.unique_copier_widget import UniqueFileCopierWidget
from src.gui.widgets.bitrate_mover_widget import BitrateMoverWidget

# Audio Shelf Tools
from src.gui.widgets.audio_shelf.duplicates_widget import DuplicatesWidget
from src.gui.widgets.audio_shelf.renamer_widget import RenamerWidget
from src.gui.widgets.audio_shelf.flattener_widget import FlattenerWidget
from src.gui.widgets.audio_shelf.organizer_widget import OrganizerWidget
from src.gui.widgets.audio_shelf.pruner_widget import PrunerWidget
from src.gui.widgets.audio_shelf.tag_editor_widget import TagEditorWidget
from src.gui.widgets.audio_shelf.atf_cleaner_widget import ATFCleanerWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio Toolbox")
        self.setGeometry(100, 100, 1280, 850)
        
        self.settings_manager = SettingsManager()
        
        # Central widget is now a horizontal container
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 1. Sidebar
        self.sidebar = SidebarWidget()
        self.sidebar.change_page_signal.connect(self.handle_navigation)
        self.main_layout.addWidget(self.sidebar)
        
        # 2. Content Area (Stacked Widget)
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0) # Padding handled by widgets
        
        self.stacked_widget = QStackedWidget()
        self.content_layout.addWidget(self.stacked_widget)
        
        self.main_layout.addWidget(self.content_area)
        
        # Initialize Widgets
        self.dashboard = DashboardWidget()
        self.dashboard.navigate_signal.connect(self.handle_navigation)
        
        # Legacy
        self.mass_compare = MassCompareWidget()
        self.genre_updater = GenreUpdaterWidget(self.settings_manager)
        self.unique_copier = UniqueFileCopierWidget()
        self.bitrate_mover = BitrateMoverWidget()

        # Audio Toolbox
        self.duplicates_widget = DuplicatesWidget()
        self.renamer_widget = RenamerWidget()
        self.flattener_widget = FlattenerWidget()
        self.organizer_widget = OrganizerWidget()
        self.pruner_widget = PrunerWidget()
        self.tag_editor_widget = TagEditorWidget()
        self.atf_cleaner_widget = ATFCleanerWidget()
        
        # Stack Order Mapping
        # 0: Dashboard
        
        # Legacy Group (Offsets 10+)
        # 10: Mass Compare
        # 11: Genre Updater
        # 12: Unique Copier
        # 13: Bitrate Mover
        
        # Toolbox Group (Offsets 4+)
        # 4:  Duplicates
        # 5:  Renamer
        # 6:  Flattener
        # 7:  Organizer
        # 8:  Pruner
        # 14: Tag Editor
        
        # We need to map these logical IDs to Stack Indices
        self.page_map = {}
        
        def add_page(widget, logical_id):
            idx = self.stacked_widget.addWidget(widget)
            self.page_map[logical_id] = idx
            
        add_page(self.dashboard, 0)
        
        add_page(self.duplicates_widget, 4)
        add_page(self.renamer_widget, 5)
        add_page(self.flattener_widget, 6)
        add_page(self.organizer_widget, 7)
        add_page(self.pruner_widget, 8)
        
        add_page(self.mass_compare, 10)
        add_page(self.genre_updater, 11)
        add_page(self.unique_copier, 12)
        add_page(self.bitrate_mover, 13)
        
        add_page(self.tag_editor_widget, 14)
        add_page(self.atf_cleaner_widget, 15)
        
        # Set default
        self.handle_navigation(0)
        
        # Menu Bar (Legacy access or Settings only)
        # self.create_menu_bar() 
        # Removed Menu Bar per professional design requirement
        # Settings is accessible via Sidebar

    def handle_navigation(self, logical_id):
        if logical_id == 99:
            self.show_settings()
            return
            
        if logical_id in self.page_map:
            stack_idx = self.page_map[logical_id]
            self.stacked_widget.setCurrentIndex(stack_idx)
            self.sidebar.set_active(logical_id)
    
    def show_settings(self):
        dialog = SettingsDialog(self.settings_manager, self)
        dialog.exec_()