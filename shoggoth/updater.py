"""
Auto-update functionality for Shoggoth

Supports both PyPI and GitHub releases based on installation type.
"""
import sys
import json
import logging
import threading
import urllib.request
import urllib.error
import tempfile
import subprocess
import platform
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Signal, QProcess, QTimer, QUrl
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QTextBrowser, QProgressBar,
    QPlainTextEdit, QMessageBox, QApplication
)
from PySide6.QtGui import QDesktopServices

# Constants
GITHUB_REPO = "tokeeto/shoggoth"
PYPI_PACKAGE = "shoggoth"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
PYPI_API_URL = f"https://pypi.org/pypi/{PYPI_PACKAGE}/json"

logger = logging.getLogger(__name__)


class InstallationType(Enum):
    """How Shoggoth was installed"""
    PYPI = "pypi"           # pip install shoggoth
    BINARY = "binary"       # PyInstaller frozen exe
    DEVELOPMENT = "dev"     # Running from source (uv run, pip -e)


@dataclass
class VersionInfo:
    """Information about an available version"""
    version: str
    download_url: Optional[str] = None
    release_notes: Optional[str] = None
    published_at: Optional[str] = None


def get_current_version() -> str:
    """Get current version from package metadata"""
    try:
        from importlib.metadata import version
        return version("shoggoth")
    except Exception:
        return "unknown"


def detect_installation_type() -> InstallationType:
    """Detect how Shoggoth was installed"""
    # Check for PyInstaller frozen executable
    if getattr(sys, 'frozen', False):
        return InstallationType.BINARY

    # Check if running from a pip-installed package
    try:
        from importlib.metadata import distribution
        dist = distribution('shoggoth')

        # Check if it's an editable install (development)
        try:
            direct_url_text = dist.read_text('direct_url.json')
            if direct_url_text:
                direct_url = json.loads(direct_url_text)
                if direct_url.get('dir_info', {}).get('editable', False):
                    return InstallationType.DEVELOPMENT
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        return InstallationType.PYPI
    except Exception:
        # Package not found via importlib.metadata - likely development
        return InstallationType.DEVELOPMENT


def compare_versions(current: str, latest: str) -> bool:
    """
    Compare semver versions, return True if latest > current.

    Handles version strings like "0.1.5", "v0.2.0", "1.0.0-beta".
    """
    def normalize(v: str) -> tuple:
        # Remove leading 'v' if present
        v = v.lstrip('v')
        # Split on common separators and convert to comparable tuple
        parts = v.replace('-', '.').replace('_', '.').split('.')
        result = []
        for part in parts:
            try:
                result.append((0, int(part)))  # Numeric parts sort first
            except ValueError:
                result.append((1, part))  # String parts sort after
        return tuple(result)

    try:
        # Try using packaging library if available
        from packaging.version import Version
        return Version(latest.lstrip('v')) > Version(current.lstrip('v'))
    except ImportError:
        # Fallback to simple comparison
        return normalize(latest) > normalize(current)
    except Exception:
        # If all else fails, simple string comparison
        return latest.lstrip('v') != current.lstrip('v')


class UpdateChecker(QObject):
    """Background update checker with thread-safe signals"""

    # Signals for thread-safe communication
    update_available = Signal(object)  # VersionInfo
    check_complete = Signal(bool)      # has_update
    check_failed = Signal(str)         # error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_version = get_current_version()
        self.installation_type = detect_installation_type()

    def check_for_updates(self):
        """Start background update check (spawns thread)"""
        thread = threading.Thread(target=self._do_check, daemon=True)
        thread.start()

    def _do_check(self):
        """Perform the actual update check (runs in background thread)"""
        try:
            if self.installation_type == InstallationType.BINARY:
                version_info = self._check_github_releases()
            else:
                version_info = self._check_pypi()

            if version_info and compare_versions(self.current_version, version_info.version):
                self.update_available.emit(version_info)
                self.check_complete.emit(True)
            else:
                self.check_complete.emit(False)
        except Exception as e:
            logger.warning(f"Update check failed: {e}")
            self.check_failed.emit(str(e))

    def _check_pypi(self) -> Optional[VersionInfo]:
        """Query PyPI JSON API for latest version"""
        try:
            request = urllib.request.Request(
                PYPI_API_URL,
                headers={'Accept': 'application/json', 'User-Agent': 'Shoggoth-Updater'}
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

            info = data.get('info', {})
            return VersionInfo(
                version=info.get('version', ''),
                release_notes=info.get('summary', ''),
            )
        except Exception as e:
            logger.warning(f"PyPI check failed: {e}")
            raise

    def _check_github_releases(self) -> Optional[VersionInfo]:
        """Query GitHub Releases API for latest version"""
        try:
            request = urllib.request.Request(
                GITHUB_API_URL,
                headers={
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'Shoggoth-Updater'
                }
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

            # Find appropriate asset for this platform
            download_url = None
            assets = data.get('assets', [])
            system = platform.system().lower()

            for asset in assets:
                name = asset.get('name', '').lower()
                # Match platform-specific installers
                if system == 'windows' and ('win' in name or name.endswith('.exe') or name.endswith('.msi')):
                    download_url = asset.get('browser_download_url')
                    break
                elif system == 'darwin' and ('mac' in name or 'darwin' in name or name.endswith('.dmg')):
                    download_url = asset.get('browser_download_url')
                    break
                elif system == 'linux' and ('linux' in name or name.endswith('.AppImage')):
                    download_url = asset.get('browser_download_url')
                    break

            return VersionInfo(
                version=data.get('tag_name', '').lstrip('v'),
                download_url=download_url,
                release_notes=data.get('body', ''),
                published_at=data.get('published_at', ''),
            )
        except Exception as e:
            logger.warning(f"GitHub check failed: {e}")
            raise


class UpdateDialog(QDialog):
    """Dialog shown when an update is available"""

    # Result codes
    UPDATE_NOW = 1
    NOT_NOW = 2
    SKIP_VERSION = 3

    def __init__(self, version_info: VersionInfo, current_version: str, parent=None):
        super().__init__(parent)
        self.version_info = version_info
        self.current_version = current_version
        self.result_action = self.NOT_NOW

        self.setWindowTitle("Update Available")
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)

        self.setup_ui()

    def setup_ui(self):
        """Build the dialog layout"""
        layout = QVBoxLayout()

        # Header
        header = QLabel("A new version of Shoggoth is available!")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        # Version info
        version_layout = QFormLayout()
        version_layout.addRow("Current version:", QLabel(self.current_version))
        version_layout.addRow("New version:", QLabel(f"<b>{self.version_info.version}</b>"))
        layout.addLayout(version_layout)

        # Release notes
        if self.version_info.release_notes:
            notes_label = QLabel("Release Notes:")
            notes_label.setStyleSheet("margin-top: 10px; font-weight: bold;")
            layout.addWidget(notes_label)

            notes_browser = QTextBrowser()
            notes_browser.setMarkdown(self.version_info.release_notes)
            notes_browser.setMaximumHeight(200)
            layout.addWidget(notes_browser)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()

        update_btn = QPushButton("Update Now")
        update_btn.setDefault(True)
        update_btn.clicked.connect(self._on_update_now)
        button_layout.addWidget(update_btn)

        later_btn = QPushButton("Not Now")
        later_btn.clicked.connect(self._on_not_now)
        button_layout.addWidget(later_btn)

        skip_btn = QPushButton("Skip This Version")
        skip_btn.clicked.connect(self._on_skip_version)
        button_layout.addWidget(skip_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _on_update_now(self):
        self.result_action = self.UPDATE_NOW
        self.accept()

    def _on_not_now(self):
        self.result_action = self.NOT_NOW
        self.reject()

    def _on_skip_version(self):
        self.result_action = self.SKIP_VERSION
        self.reject()


class UpdateProgressDialog(QDialog):
    """Shows update download/install progress"""

    def __init__(self, version_info: VersionInfo, installation_type: InstallationType, parent=None):
        super().__init__(parent)
        self.version_info = version_info
        self.installation_type = installation_type
        self.process = None
        self.download_path = None

        self.setWindowTitle("Updating Shoggoth")
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        self.setModal(True)

        self.setup_ui()

    def setup_ui(self):
        """Build the dialog layout"""
        layout = QVBoxLayout()

        # Status label
        self.status_label = QLabel("Preparing update...")
        self.status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Output log
        self.output_log = QPlainTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setMaximumHeight(150)
        layout.addWidget(self.output_log)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setVisible(False)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def start_update(self):
        """Begin the update process"""
        if self.installation_type == InstallationType.PYPI:
            self._start_pip_upgrade()
        elif self.installation_type == InstallationType.BINARY:
            self._start_binary_download()

    def _start_pip_upgrade(self):
        """Run pip upgrade for PyPI installation"""
        self.status_label.setText("Installing update via pip...")
        self.progress_bar.setRange(0, 0)  # Indeterminate progress

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_pip_finished)

        # Use sys.executable to ensure correct Python
        self.process.start(sys.executable, ["-m", "pip", "install", "--upgrade", PYPI_PACKAGE])

    def _on_stdout(self):
        """Handle stdout from pip"""
        if self.process:
            data = self.process.readAllStandardOutput().data().decode('utf-8', errors='replace')
            self.output_log.appendPlainText(data.strip())

    def _on_stderr(self):
        """Handle stderr from pip"""
        if self.process:
            data = self.process.readAllStandardError().data().decode('utf-8', errors='replace')
            self.output_log.appendPlainText(data.strip())

    def _on_pip_finished(self, exit_code, exit_status):
        """Handle pip completion"""
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.cancel_btn.setVisible(False)
        self.close_btn.setVisible(True)

        if exit_code == 0:
            self.status_label.setText("Update complete! Please restart Shoggoth.")
            self.output_log.appendPlainText("\n--- Update successful ---")
        else:
            self.status_label.setText("Update failed. See log for details.")
            self.output_log.appendPlainText(f"\n--- Update failed (exit code {exit_code}) ---")
            self.output_log.appendPlainText("You can try manually: pip install --upgrade shoggoth")

    def _start_binary_download(self):
        """Download binary update"""
        if not self.version_info.download_url:
            self.status_label.setText("No download available for your platform.")
            self.output_log.appendPlainText("Could not find a compatible download.")
            self.output_log.appendPlainText(f"Please visit: https://github.com/{GITHUB_REPO}/releases/latest")
            self.cancel_btn.setVisible(False)
            self.close_btn.setVisible(True)
            return

        self.status_label.setText("Downloading update...")

        # Download in background thread
        thread = threading.Thread(target=self._download_binary, daemon=True)
        thread.start()

    def _download_binary(self):
        """Download binary file (runs in background thread)"""
        try:
            # Determine filename from URL
            url = self.version_info.download_url
            filename = url.split('/')[-1]

            # Download to temp directory
            temp_dir = Path(tempfile.gettempdir())
            self.download_path = temp_dir / filename

            def report_progress(block_num, block_size, total_size):
                if total_size > 0:
                    downloaded = block_num * block_size
                    percent = min(100, int(downloaded * 100 / total_size))
                    # Update UI from main thread
                    QTimer.singleShot(0, lambda: self._update_download_progress(percent, downloaded, total_size))

            urllib.request.urlretrieve(url, self.download_path, reporthook=report_progress)

            # Download complete - update UI from main thread
            QTimer.singleShot(0, self._on_download_complete)

        except Exception as e:
            QTimer.singleShot(0, lambda: self._on_download_error(str(e)))

    def _update_download_progress(self, percent, downloaded, total):
        """Update download progress (called on main thread)"""
        self.progress_bar.setValue(percent)
        mb_downloaded = downloaded / (1024 * 1024)
        mb_total = total / (1024 * 1024)
        self.status_label.setText(f"Downloading... {mb_downloaded:.1f} / {mb_total:.1f} MB")

    def _on_download_complete(self):
        """Handle download completion"""
        self.progress_bar.setValue(100)
        self.status_label.setText("Download complete!")
        self.cancel_btn.setVisible(False)
        self.close_btn.setVisible(True)

        self.output_log.appendPlainText(f"Downloaded to: {self.download_path}")
        self.output_log.appendPlainText("\nClick 'Run Installer' to install the update.")

        # Add run installer button
        run_btn = QPushButton("Run Installer")
        run_btn.clicked.connect(self._run_installer)
        self.layout().itemAt(self.layout().count() - 1).layout().insertWidget(0, run_btn)

    def _on_download_error(self, error: str):
        """Handle download error"""
        self.status_label.setText("Download failed")
        self.output_log.appendPlainText(f"Error: {error}")
        self.output_log.appendPlainText(f"\nPlease download manually from:")
        self.output_log.appendPlainText(f"https://github.com/{GITHUB_REPO}/releases/latest")
        self.cancel_btn.setVisible(False)
        self.close_btn.setVisible(True)

    def _run_installer(self):
        """Run the downloaded installer"""
        if not self.download_path or not self.download_path.exists():
            return

        try:
            if sys.platform == 'win32':
                import os
                os.startfile(str(self.download_path))
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(self.download_path)])
            else:
                # Linux - try to make executable and run
                self.download_path.chmod(self.download_path.stat().st_mode | 0o111)
                subprocess.Popen([str(self.download_path)])

            # Quit the application
            QApplication.quit()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Could not run installer:\n{e}\n\nPlease run it manually from:\n{self.download_path}"
            )

    def _on_cancel(self):
        """Cancel the update"""
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
        self.reject()


class UpdateManager(QObject):
    """Coordinates update checking and UI"""

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings = settings_manager
        self.parent_widget = parent
        self.checker = UpdateChecker(self)

        # Connect signals
        self.checker.update_available.connect(self._on_update_available)
        self.checker.check_failed.connect(self._on_check_failed)

        self._is_manual_check = False

    def should_check_for_updates(self) -> bool:
        """Check if we should perform an automatic update check"""
        # Skip in development mode
        if self.checker.installation_type == InstallationType.DEVELOPMENT:
            logger.info("Skipping update check in development mode")
            return False

        # Check if auto-updates are enabled
        if not self.settings.getboolean('Shoggoth', 'auto_check_updates', True):
            return False

        return True

    def check_for_updates_async(self):
        """Trigger background update check (for startup)"""
        self._is_manual_check = False
        self.checker.check_for_updates()

    def check_for_updates_manual(self):
        """Trigger manual update check (from menu)"""
        self._is_manual_check = True

        # For development mode, show a message
        if self.checker.installation_type == InstallationType.DEVELOPMENT:
            QMessageBox.information(
                self.parent_widget,
                "Development Mode",
                "Update checking is disabled in development mode.\n\n"
                "You are running Shoggoth from source code."
            )
            return

        self.checker.check_for_updates()

    def _on_update_available(self, version_info: VersionInfo):
        """Handle update available signal"""
        # Check if this version should be skipped
        skipped = self.settings.get('Shoggoth', 'skipped_version', '')
        if not self._is_manual_check and skipped == version_info.version:
            logger.info(f"Skipping update notification for version {version_info.version}")
            return

        # Show update dialog
        dialog = UpdateDialog(version_info, self.checker.current_version, self.parent_widget)
        dialog.exec()

        if dialog.result_action == UpdateDialog.UPDATE_NOW:
            self._perform_update(version_info)
        elif dialog.result_action == UpdateDialog.SKIP_VERSION:
            self.settings.set('Shoggoth', 'skipped_version', version_info.version)
            self.settings.save()

    def _on_check_failed(self, error: str):
        """Handle check failed signal"""
        if self._is_manual_check:
            QMessageBox.warning(
                self.parent_widget,
                "Update Check Failed",
                f"Could not check for updates:\n{error}"
            )

    def _perform_update(self, version_info: VersionInfo):
        """Execute the update"""
        dialog = UpdateProgressDialog(version_info, self.checker.installation_type, self.parent_widget)
        dialog.show()
        dialog.start_update()
        dialog.exec()
