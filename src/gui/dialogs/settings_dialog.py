from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QDialogButtonBox, QTabWidget,
    QWidget, QCheckBox, QGroupBox, QFormLayout
)

class SettingsDialog(QDialog):
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Settings")
        self.resize(500, 400)
        self.init_ui()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # --- General Tab ---
        self.general_tab = QWidget()
        self.init_general_tab()
        self.tabs.addTab(self.general_tab, "General")
        
        # --- Metadata Providers Tab ---
        self.providers_tab = QWidget()
        self.init_providers_tab()
        self.tabs.addTab(self.providers_tab, "Metadata Providers")
        
        # --- Dialog Buttons ---
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        
    def init_general_tab(self):
        layout = QVBoxLayout(self.general_tab)
        # Placeholder for future general settings
        layout.addWidget(QLabel("General Application Settings"))
        layout.addStretch()
        
    def init_providers_tab(self):
        layout = QVBoxLayout(self.providers_tab)
        
        # 1. Google Books Config
        gb_group = QGroupBox("Google Books")
        gb_layout = QFormLayout()
        
        self.chk_google = QCheckBox("Enable Google Books")
        self.chk_google.setChecked(self.settings_manager.get('metadata_use_google', True))
        
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setText(self.settings_manager.get('google_api_key', ''))
        self.api_key_edit.setPlaceholderText("Optional (Increases rate limits)")
        self.api_key_edit.setStyleSheet("color: white; background-color: #404040; padding: 5px; border-radius: 4px;")
        self.api_key_edit.setMinimumWidth(350)
        
        gb_layout.addRow(self.chk_google)
        gb_layout.addRow("API Key:", self.api_key_edit)
        gb_group.setLayout(gb_layout)
        layout.addWidget(gb_group)
        
        # 2. Other Providers
        other_group = QGroupBox("Other Providers")
        other_layout = QVBoxLayout()
        
        self.chk_audnexus = QCheckBox("Enable Audnexus (High Quality Metadata)")
        self.chk_audnexus.setChecked(self.settings_manager.get('metadata_use_audnexus', True))
        
        self.chk_goodreads = QCheckBox("Enable Goodreads (Ratings/Reviews)")
        self.chk_goodreads.setChecked(self.settings_manager.get('metadata_use_goodreads', True))
        
        self.chk_amazon = QCheckBox("Enable Amazon/DuckDuckGo (Fallback)")
        self.chk_amazon.setChecked(self.settings_manager.get('metadata_use_amazon', True))
        
        other_layout.addWidget(self.chk_audnexus)
        other_layout.addWidget(self.chk_goodreads)
        other_layout.addWidget(self.chk_amazon)
        other_group.setLayout(other_layout)
        layout.addWidget(other_group)
        
        layout.addStretch()

    def accept(self):
        # Save Metadata Settings
        self.settings_manager.set('google_api_key', self.api_key_edit.text().strip())
        self.settings_manager.set('metadata_use_google', self.chk_google.isChecked())
        self.settings_manager.set('metadata_use_audnexus', self.chk_audnexus.isChecked())
        self.settings_manager.set('metadata_use_goodreads', self.chk_goodreads.isChecked())
        self.settings_manager.set('metadata_use_amazon', self.chk_amazon.isChecked())
        
        super().accept() 