from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QProgressBar,
    QTextEdit, QFileDialog, QMenuBar, QMenu, QAction,
    QStackedWidget
)
from PyQt5.QtCore import Qt
from src.core.settings_manager import SettingsManager
from src.gui.dialogs.settings_dialog import SettingsDialog
from src.gui.widgets.mass_compare_widget import MassCompareWidget
from src.gui.widgets.genre_updater_widget import GenreUpdaterWidget
from src.gui.widgets.unique_copier_widget import UniqueFileCopierWidget
from src.gui.widgets.bitrate_mover_widget import BitrateMoverWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Python Media Tools")
        self.setGeometry(100, 100, 900, 700)
        
        # Initialize settings
        self.settings_manager = SettingsManager()
        
        # Create central widget and main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # Create stacked widget to hold different tools
        self.stacked_widget = QStackedWidget()
        
        # Initialize tool widgets
        self.mass_compare = MassCompareWidget()
        self.genre_updater = GenreUpdaterWidget(self.settings_manager)
        self.unique_copier = UniqueFileCopierWidget()
        self.bitrate_mover = BitrateMoverWidget()
        
        # Add widgets to stacked widget
        self.stacked_widget.addWidget(self.mass_compare)
        self.stacked_widget.addWidget(self.genre_updater)
        self.stacked_widget.addWidget(self.unique_copier)
        self.stacked_widget.addWidget(self.bitrate_mover)
        
        self.main_layout.addWidget(self.stacked_widget)
        
        # Create menu bar
        self.create_menu_bar()
    
    def create_menu_bar(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        # Settings action
        settings_action = QAction("Settings", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        
        # Mass Compare action
        mass_compare_action = QAction("Mass Compare", self)
        mass_compare_action.triggered.connect(lambda: self.switch_tool(0))
        tools_menu.addAction(mass_compare_action)
        
        # Genre Updater action
        genre_updater_action = QAction("Genre Updater", self)
        genre_updater_action.triggered.connect(lambda: self.switch_tool(1))
        tools_menu.addAction(genre_updater_action)
        
        # Unique Copier action
        unique_copier_action = QAction("Unique File Copier", self)
        unique_copier_action.triggered.connect(lambda: self.switch_tool(2))
        tools_menu.addAction(unique_copier_action)
        
        # Bitrate Mover action
        bitrate_mover_action = QAction("Bitrate Mover", self)
        bitrate_mover_action.triggered.connect(lambda: self.switch_tool(3))
        tools_menu.addAction(bitrate_mover_action)
    
    def switch_tool(self, index):
        self.stacked_widget.setCurrentIndex(index)
    
    def show_settings(self):
        dialog = SettingsDialog(self.settings_manager, self)
        dialog.exec_() 