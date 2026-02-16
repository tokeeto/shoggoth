"""
Main application entry point for Shoggoth with PySide6
"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from shoggoth.main_window import ShoggothMainWindow
from shoggoth.settings import SettingsManager
from shoggoth.i18n import load_language


def main():
    """Main application entry point"""
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Shoggoth")
    app.setOrganizationName("Shoggoth")
    
    # Load saved language setting
    settings = SettingsManager()
    saved_language = settings.get('Shoggoth', 'language', 'en')
    load_language(saved_language)
    
    # Set application style
    app.setStyle("Fusion")
    
    # Create and show main window
    window = ShoggothMainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()