from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel

class MassCompareWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Mass Compare Widget - Coming Soon")) 