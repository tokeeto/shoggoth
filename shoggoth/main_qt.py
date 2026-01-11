"""
Main application entry point for Shoggoth with PySide6
"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from shoggoth.main_window import ShoggothMainWindow


def main():
    """Main application entry point"""
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Shoggoth")
    app.setOrganizationName("Shoggoth")
    
    # Set application style
    app.setStyle("Fusion")
    
    # Create and show main window
    window = ShoggothMainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()