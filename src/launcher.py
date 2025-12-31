
import sys
import os
from PyQt5.QtWidgets import QApplication
try:
    from qt_material import apply_stylesheet
except ImportError:
    apply_stylesheet = None

# Ensure src is in path to import modules correctly if run from root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    
    # Apply theme if available
    if apply_stylesheet:
        # Using a dark teal theme that looks modern and professional
        apply_stylesheet(app, theme='dark_teal.xml')
    else:
        print("Warning: qt-material not installed. Running with default theme.")
        print("Install it with: pip install qt-material")

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
