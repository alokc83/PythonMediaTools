from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QCheckBox

class MassCompareWidget(QWidget):
    def __init__(self, settings_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        layout = QVBoxLayout(self)
        
        # Header & Toggle
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Mass Compare Widget - Coming Soon"))
        header_layout.addStretch()
        
        self.dashboard_toggle = QCheckBox("Show in Dashboard")
        self.dashboard_toggle.setChecked(self.get_dashboard_visibility())
        self.dashboard_toggle.stateChanged.connect(self.toggle_dashboard_visibility)
        header_layout.addWidget(self.dashboard_toggle)
        
        layout.addLayout(header_layout)

    def get_dashboard_visibility(self):
        if self.settings_manager:
            # mass compare id is 10
            val = self.settings_manager.get("dashboard_visible_10")
            if val is None: return True
            return str(val).lower() == 'true'
        return True

    def toggle_dashboard_visibility(self):
        if self.settings_manager:
            state = self.dashboard_toggle.isChecked()
            self.settings_manager.set("dashboard_visible_10", str(state).lower()) 