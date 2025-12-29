import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox
)
from plexapi.myplex import MyPlexAccount

class PlexLoginWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plex Login")
        self.resize(400, 250)
        
        # Create a central widget and a vertical layout
        central_widget = QWidget()
        layout = QVBoxLayout()
        
        # Username field
        username_layout = QHBoxLayout()
        username_label = QLabel("Username:")
        self.username_edit = QLineEdit()
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_edit)
        layout.addLayout(username_layout)
        
        # Password field (with hidden text)
        password_layout = QHBoxLayout()
        password_label = QLabel("Password:")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_edit)
        layout.addLayout(password_layout)
        
        # Server Name field
        server_layout = QHBoxLayout()
        server_label = QLabel("Server Name:")
        self.server_edit = QLineEdit()
        server_layout.addWidget(server_label)
        server_layout.addWidget(self.server_edit)
        layout.addLayout(server_layout)
        
        # Library Name field
        library_layout = QHBoxLayout()
        library_label = QLabel("Library Name:")
        self.library_edit = QLineEdit()
        library_layout.addWidget(library_label)
        library_layout.addWidget(self.library_edit)
        layout.addLayout(library_layout)
        
        # Connect button
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_to_plex)
        layout.addWidget(self.connect_button)
        
        # Set layout and central widget
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
    
    def connect_to_plex(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        server_name = self.server_edit.text().strip()
        library_name = self.library_edit.text().strip()
        
        if not username or not password or not server_name or not library_name:
            QMessageBox.warning(self, "Input Error", "Please fill in all fields.")
            return
        
        try:
            # Log in to your Plex account.
            account = MyPlexAccount(username, password)
            # Find the Plex server resource by name (case-insensitive search)
            resource = None
            for r in account.resources():
                if server_name.lower() in r.name.lower():
                    resource = r
                    break
            if resource is None:
                QMessageBox.critical(self, "Connection Error",
                                     f"Server '{server_name}' not found in your account.")
                return
            
            # Connect to the resource (server)
            plex = resource.connect()
            token = plex._token  # Capture the token
            QMessageBox.information(self, "Connected",
                                    f"Connected to Plex server!\nToken: {token}")
            # You can now use this token for further Plex interactions.
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", f"Failed to connect: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PlexLoginWindow()
    window.show()
    sys.exit(app.exec_())
