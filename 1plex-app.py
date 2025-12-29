import sys
import os
import json
import requests
from io import BytesIO
from bs4 import BeautifulSoup

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAction, QAbstractItemView
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer

CONFIG_FILE = "config.json"


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print("Error reading config:", e)
    return {}


def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print("Error writing config:", e)


def get_goodreads_rating(album_name):
    """Scrape Goodreads for the rating of the given album (book)."""
    query = album_name.replace(" ", "+")
    search_url = f"https://www.goodreads.com/search?q={query}"
    try:
        response = requests.get(search_url, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            rating_elem = soup.find('span', class_='minirating')
            if rating_elem:
                rating_text = rating_elem.get_text(strip=True)
                parts = rating_text.split()
                try:
                    return float(parts[0])
                except (ValueError, IndexError):
                    return None
        return None
    except Exception as e:
        print(f"Error fetching Goodreads rating for '{album_name}':", e)
        return None


def get_audible_rating(album_name):
    """Placeholder for audible rating logic."""
    return None


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plex Login")
        self.resize(400, 250)
        self.token = None
        self.plex_url = None
        self.library_name = None

        layout = QVBoxLayout()

        # Username
        user_layout = QHBoxLayout()
        user_layout.addWidget(QLabel("Username:"))
        self.username_edit = QLineEdit()
        user_layout.addWidget(self.username_edit)
        layout.addLayout(user_layout)

        # Password
        pass_layout = QHBoxLayout()
        pass_layout.addWidget(QLabel("Password:"))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        pass_layout.addWidget(self.password_edit)
        layout.addLayout(pass_layout)

        # Plex Server URL
        server_layout = QHBoxLayout()
        server_layout.addWidget(QLabel("Plex Server URL:"))
        self.server_edit = QLineEdit("http://localhost:32400")
        server_layout.addWidget(self.server_edit)
        layout.addLayout(server_layout)

        # Library Name
        lib_layout = QHBoxLayout()
        lib_layout.addWidget(QLabel("Library Name:"))
        self.library_edit = QLineEdit("Audiobooks")
        lib_layout.addWidget(self.library_edit)
        layout.addLayout(lib_layout)

        # Connect Button
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.do_login)
        layout.addWidget(self.connect_button)

        self.setLayout(layout)

    def do_login(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        server_url = self.server_edit.text().strip()
        library_name = self.library_edit.text().strip()

        if not username or not password or not server_url or not library_name:
            QMessageBox.warning(self, "Input Error", "Please fill in all fields.")
            return

        try:
            # Use the existing login logic from before.
            account = MyPlexAccount(username, password)
        except Exception as e:
            QMessageBox.critical(self, "Login Error", f"Failed to login: {e}")
            return

        # Find the server resource – match by server URL or part of the name.
        resource = None
        for r in account.resources():
            # Check if the provided server URL is in the resource's address or name.
            if server_url.lower() in r.address.lower() or server_url.lower() in r.name.lower():
                resource = r
                break
        if resource is None:
            QMessageBox.critical(self, "Server Error",
                                 f"Server '{server_url}' not found in your account.")
            return

        try:
            plex = resource.connect()
            self.token = plex._token  # capture the token
            self.plex_url = plex._baseUrl  # typically the base URL of the server
            self.library_name = library_name
            QMessageBox.information(self, "Connected", "Successfully connected to Plex!")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", f"Failed to connect to Plex: {e}")


class LibraryWidget(QWidget):
    def __init__(self, plex_server, library_name, parent=None):
        super().__init__(parent)
        self.plex_server = plex_server
        self.library_name = library_name

        layout = QVBoxLayout()
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Image", "Album/Title", "Artist", "Plex Rating", "Goodreads Rating", "Audible Rating"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.load_library_items()

    def load_library_items(self):
        try:
            library = self.plex_server.library.section(self.library_name)
            items = library.search()
        except Exception as e:
            QMessageBox.critical(self, "Library Error", f"Failed to load library: {e}")
            return

        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            # Thumbnail image if available.
            if item.thumb:
                try:
                    thumb_url = self.plex_server.url(item.thumb)
                    response = requests.get(thumb_url, timeout=10)
                    pixmap = QPixmap()
                    pixmap.loadFromData(response.content)
                    icon_label = QLabel()
                    icon_label.setPixmap(pixmap.scaled(80, 80, Qt.KeepAspectRatio))
                except Exception as e:
                    icon_label = QLabel("No Image")
            else:
                icon_label = QLabel("No Image")
            self.table.setCellWidget(row, 0, icon_label)

            # Album/Title
            title_item = QTableWidgetItem(item.title)
            self.table.setItem(row, 1, title_item)

            # Artist – using grandparentTitle if available.
            artist = item.grandparentTitle if hasattr(item, 'grandparentTitle') else "Unknown"
            artist_item = QTableWidgetItem(artist)
            self.table.setItem(row, 2, artist_item)

            # Plex Rating (if available)
            plex_rating = item.userRating if hasattr(item, 'userRating') else "N/A"
            plex_rating_item = QTableWidgetItem(str(plex_rating))
            self.table.setItem(row, 3, plex_rating_item)

            # Goodreads Rating (scraped)
            gr_rating = get_goodreads_rating(item.title)
            gr_rating_item = QTableWidgetItem(str(gr_rating) if gr_rating is not None else "N/A")
            self.table.setItem(row, 4, gr_rating_item)

            # Audible Rating (dummy function)
            audible_rating = get_audible_rating(item.title)
            audible_rating_item = QTableWidgetItem(str(audible_rating) if audible_rating is not None else "N/A")
            self.table.setItem(row, 5, audible_rating_item)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plex Library Viewer")
        self.resize(900, 600)
        self.config = load_config()
        self.plex_server = None
        self.library_name = None

        # Menu Bar: Login is under Account.
        menubar = self.menuBar()
        account_menu = menubar.addMenu("Account")
        login_action = QAction("Login", self)
        login_action.triggered.connect(self.show_login)
        account_menu.addAction(login_action)

        # Central widget and layout.
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.vlayout = QVBoxLayout()
        self.central_widget.setLayout(self.vlayout)

        # Try to connect using stored configuration.
        self.try_connect_from_config()

    def try_connect_from_config(self):
        token = self.config.get("token")
        plex_url = self.config.get("plex_url")
        library_name = self.config.get("library_name")
        if token and plex_url and library_name:
            try:
                self.plex_server = PlexServer(plex_url, token)
                # Test the connection by accessing a property.
                _ = self.plex_server.friendlyName
                self.library_name = library_name
                self.setWindowTitle(f"Connected to: {self.plex_server.friendlyName}")
                self.load_library_view()
            except Exception as e:
                QMessageBox.warning(self, "Connection Error", f"Stored token invalid: {e}")
                self.show_login()
        else:
            self.show_login()

    def show_login(self):
        dlg = LoginDialog(self)
        if dlg.exec_():
            # On successful login, store settings to config.
            self.config["token"] = dlg.token
            self.config["plex_url"] = dlg.plex_url
            self.config["library_name"] = dlg.library_name
            save_config(self.config)
            try:
                self.plex_server = PlexServer(dlg.plex_url, dlg.token)
                self.library_name = dlg.library_name
                self.setWindowTitle(f"Connected to: {self.plex_server.friendlyName}")
                self.load_library_view()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to connect after login: {e}")

    def load_library_view(self):
        # Remove any existing widget from the layout.
        while self.vlayout.count():
            widget = self.vlayout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        lib_widget = LibraryWidget(self.plex_server, self.library_name)
        self.vlayout.addWidget(lib_widget)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    mainWin = MainWindow()
    mainWin.show()
    sys.exit(app.exec_())
