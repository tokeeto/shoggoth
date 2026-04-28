"""
Main application entry point for Shoggoth with PySide6
"""
import signal
import sys
import threading
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer, QObject, Signal

from shoggoth.ui.main_window import ShoggothMainWindow
from shoggoth.settings import SettingsManager, apply_appearance
from shoggoth.i18n import load_language
from shoggoth import updater

logger = logging.getLogger(__name__)


class _AssetUpdateSignal(QObject):
    """Carries the 'assets were updated' notification from the background thread."""
    triggered = Signal()


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

    # Allow Ctrl+C from the terminal to kill the app without saving.
    # Qt's event loop blocks Python signal handling, so a timer wakes it up
    # periodically so the SIGINT handler can fire.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    interrupt_timer = QTimer()
    interrupt_timer.start(200)
    interrupt_timer.timeout.connect(lambda: None)

    # First-run: if no local assets exist, show a download dialog before
    # opening the main window (translations, dropdowns etc. all depend on
    # the asset pack being present).
    if not updater.assets_available():
        from shoggoth.ui.updater_ui import FirstRunDownloadDialog
        from PySide6.QtWidgets import QDialog
        dialog = FirstRunDownloadDialog()
        dialog.start_download()
        if dialog.exec() != QDialog.Accepted:
            sys.exit(0)
        # Assets are now present; fall through to create the main window.

    # Create the main window first so the signal connection is established
    # before the background thread can emit.
    window = ShoggothMainWindow()

    # Subsequent runs: run incremental asset update silently in the background.
    # The signal is connected before the thread starts to guarantee delivery
    # even if the download completes before the Qt event loop ticks.
    _update_signal = _AssetUpdateSignal()
    _update_signal.triggered.connect(window.on_assets_updated)
    threading.Thread(
        target=_incremental_update_background,
        args=(_update_signal,),
        daemon=True,
    ).start()

    window.show()
    sys.exit(app.exec())


def _incremental_update_background(signal: _AssetUpdateSignal):
    """Run ensure_assets_current() in a background thread on non-first runs."""
    try:
        changed = updater.ensure_assets_current()
        if changed:
            signal.triggered.emit()
    except Exception as exc:
        logger.warning(f"Background asset update failed: {exc}")


if __name__ == "__main__":
    main()
