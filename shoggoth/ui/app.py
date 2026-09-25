"""
Main application entry point for Shoggoth with PySide6
"""
import signal
import sys
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer

from shoggoth.ui.main_window import ShoggothMainWindow
from shoggoth.ui.snippet_input import SnippetSequenceFilter
from shoggoth.settings import SettingsManager, apply_appearance
from shoggoth.i18n import load_language, tr
from shoggoth import telemetry, updater

logger = logging.getLogger(__name__)


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

    # Opt-in usage data collection (off by default -- see telemetry.py and
    # CLAUDE.md's Data collection section). No-ops unless the user has
    # already turned it on in Settings -> Privacy on a previous run. Started
    # here, before the window is constructed, so ShoggothMainWindow.__init__
    # already has an active session to record the startup event into.
    telemetry.start_session(settings)

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

    # Ctrl+Space snippet sequences (app-wide). Stored on window to keep the
    # Python wrapper alive for as long as Qt dispatches events to it.
    window._snippet_filter = SnippetSequenceFilter(app)
    app.installEventFilter(window._snippet_filter)

    # Ctrl+L "Insert Link" in any text field (app-wide, same rationale).
    from shoggoth.ui.insert_link import InsertLinkFilter
    window._insert_link_filter = InsertLinkFilter(app)
    app.installEventFilter(window._insert_link_filter)

    # Subsequent runs: update the asset pack in the background -- silently,
    # unless it would overwrite files the user changed, or files fail.
    from shoggoth.ui.updater_ui import BackgroundAssetUpdater
    window.asset_updater = BackgroundAssetUpdater(window)
    window.asset_updater.start()

    window.show()

    # First-run only, ever: a single-button notice pointing at the opt-in
    # telemetry setting (Settings -> Privacy). Never shown again afterwards,
    # regardless of what level (if any) the user ends up choosing.
    if not settings.getboolean('Shoggoth', 'telemetry_notice_shown', False):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(window, tr("DLG_TELEMETRY_NOTICE"), tr("MSG_TELEMETRY_NOTICE"))
        settings.set('Shoggoth', 'telemetry_notice_shown', True)
        settings.save()

    if window._snippet_filter.load_errors:
        from shoggoth.ui.snippet_loader import report_load_errors
        report_load_errors(window, window._snippet_filter.load_errors)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
