from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QDialogButtonBox
)

class SettingsDialog(QDialog):
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Settings")
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # API Key input
        api_layout = QHBoxLayout()
        api_label = QLabel("Google API Key:")
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setText(self.settings_manager.get('google_api_key', ''))
        api_layout.addWidget(api_label)
        api_layout.addWidget(self.api_key_edit)
        layout.addLayout(api_layout)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def accept(self):
        # Save settings before closing
        self.settings_manager.set('google_api_key', self.api_key_edit.text().strip())
        super().accept() 