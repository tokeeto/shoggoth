"""
Main application entry point for Shoggoth with PySide6
"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from shoggoth.ui.main_window import ShoggothMainWindow
from shoggoth.settings import SettingsManager, apply_appearance
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

    # Apply saved style and color scheme
    color_scheme = settings.get('Shoggoth', 'color_scheme', 'system')
    ui_style = settings.get('Shoggoth', 'ui_style', 'Fusion')
    apply_appearance(color_scheme, ui_style)

    # Create and show main window
    window = ShoggothMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
