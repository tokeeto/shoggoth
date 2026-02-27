"""
Qt UI layer for Shoggoth update checking and dialogs.

Imports core logic from updater.py; this module should only be imported
in UI/Qt contexts (not from tool.py CLI paths).
"""
import sys
import logging
import threading
import requests
import tempfile
import subprocess
import platform
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QProcess
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QTextBrowser, QProgressBar,
    QPlainTextEdit, QMessageBox, QApplication
)
from shoggoth.i18n import tr
from shoggoth.updater import (
    InstallationType, VersionInfo,
    get_current_version, detect_installation_type, compare_versions,
    GITHUB_API_URL, PYPI_API_URL,
)

logger = logging.getLogger(__name__)


class UpdateChecker(QObject):
    """Background update checker with thread-safe signals"""

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
            response = requests.get(
                PYPI_API_URL,
                headers={'Accept': 'application/json', 'User-Agent': 'Shoggoth-Updater'}
            )
            data = response.json()
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
            response = requests.get(
                GITHUB_API_URL,
                headers={'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'Shoggoth-Updater'}
            )
            data = response.json()

            download_url = None
            assets = data.get('assets', [])
            system = platform.system().lower()

            for asset in assets:
                name = asset.get('name', '').lower()
                if system == 'windows' and 'win' in name:
                    download_url = asset.get('browser_download_url')
                    break
                elif system == 'darwin' and 'mac' in name:
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

    UPDATE_NOW = 1
    NOT_NOW = 2
    SKIP_VERSION = 3

    def __init__(self, version_info: VersionInfo, current_version: str, parent=None):
        super().__init__(parent)
        self.version_info = version_info
        self.current_version = current_version
        self.result_action = self.NOT_NOW

        self.setWindowTitle(tr("DLG_UPDATE_AVAILABLE"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        header = QLabel(tr("MSG_NEW_VERSION_AVAILABLE"))
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        version_layout = QFormLayout()
        version_layout.addRow(tr("LABEL_CURRENT_VERSION"), QLabel(self.current_version))
        version_layout.addRow(tr("LABEL_NEW_VERSION"), QLabel(f"<b>{self.version_info.version}</b>"))
        layout.addLayout(version_layout)

        if self.version_info.release_notes:
            notes_label = QLabel(tr("LABEL_RELEASE_NOTES"))
            notes_label.setStyleSheet("margin-top: 10px; font-weight: bold;")
            layout.addWidget(notes_label)

            notes_browser = QTextBrowser()
            notes_browser.setMarkdown(self.version_info.release_notes)
            notes_browser.setMaximumHeight(200)
            layout.addWidget(notes_browser)

        layout.addStretch()

        button_layout = QHBoxLayout()

        update_btn = QPushButton(tr("BTN_UPDATE_NOW"))
        update_btn.setDefault(True)
        update_btn.clicked.connect(self._on_update_now)
        button_layout.addWidget(update_btn)

        later_btn = QPushButton(tr("BTN_NOT_NOW"))
        later_btn.clicked.connect(self._on_not_now)
        button_layout.addWidget(later_btn)

        skip_btn = QPushButton(tr("BTN_SKIP_VERSION"))
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

    # Signals for safe cross-thread UI updates from the download thread
    _download_progress = Signal(int, int, int)  # percent, downloaded_bytes, total_bytes
    _download_complete = Signal()
    _download_error = Signal(str)

    def __init__(self, version_info: VersionInfo, installation_type: InstallationType, parent=None):
        super().__init__(parent)
        self.version_info = version_info
        self.installation_type = installation_type
        self.process = None
        self.download_path = None

        self._download_progress.connect(self._update_download_progress)
        self._download_complete.connect(self._on_download_complete)
        self._download_error.connect(self._on_download_error)

        self.setWindowTitle(tr("DLG_UPDATING"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        self.setModal(True)

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        self.status_label = QLabel(tr("MSG_STARTING_UPDATE"))
        self.status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.output_log = QPlainTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setMaximumHeight(150)
        layout.addWidget(self.output_log)

        layout.addStretch()

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton(tr("BTN_CANCEL"))
        self.cancel_btn.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_btn)

        self.close_btn = QPushButton(tr("BTN_CLOSE"))
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setVisible(False)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def start_update(self):
        if self.installation_type == InstallationType.PYPI:
            self._start_pip_upgrade()
        elif self.installation_type == InstallationType.BINARY:
            self._start_binary_download()

    def _start_pip_upgrade(self):
        self.status_label.setText(tr("MSG_INSTALLING_VIA_PIP"))
        self.progress_bar.setRange(0, 0)

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_pip_finished)
        self.process.start(sys.executable, ["-m", "pip", "install", "--upgrade", 'shoggoth'])

    def _on_stdout(self):
        if self.process:
            data = self.process.readAllStandardOutput().data().decode('utf-8', errors='replace')
            self.output_log.appendPlainText(data.strip())

    def _on_stderr(self):
        if self.process:
            data = self.process.readAllStandardError().data().decode('utf-8', errors='replace')
            self.output_log.appendPlainText(data.strip())

    def _on_pip_finished(self, exit_code, exit_status):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.cancel_btn.setVisible(False)
        self.close_btn.setVisible(True)

        if exit_code == 0:
            self.status_label.setText(tr("MSG_UPDATE_COMPLETE_RESTART"))
            self.output_log.appendPlainText(tr("MSG_UPDATE_SUCCESSFUL"))
        else:
            self.status_label.setText(tr("MSG_UPDATE_FAILED"))
            self.output_log.appendPlainText(tr("MSG_UPDATE_FAILED_CODE").format(code=exit_code))
            self.output_log.appendPlainText(tr("MSG_TRY_MANUAL_PIP"))

    def _start_binary_download(self):
        if not self.version_info.download_url:
            self.status_label.setText(tr("MSG_NO_DOWNLOAD_PLATFORM"))
            self.output_log.appendPlainText(tr("MSG_NO_COMPATIBLE_DOWNLOAD"))
            self.output_log.appendPlainText(tr("MSG_PLEASE_VISIT_URL").format(url="https://github.com/tokeeto/shoggoth/releases/latest"))
            self.cancel_btn.setVisible(False)
            self.close_btn.setVisible(True)
            return

        self.status_label.setText(tr("MSG_DOWNLOADING_UPDATE"))
        thread = threading.Thread(target=self._download_binary, daemon=True)
        thread.start()

    def _download_binary(self):
        try:
            url = self.version_info.download_url
            if not url:
                raise ValueError("No download URL")
            filename = url.split('/')[-1]

            temp_dir = Path(tempfile.gettempdir())
            self.download_path = temp_dir / filename

            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(self.download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        percent = min(100, int(downloaded * 100 / total_size)) if total_size > 0 else 0
                        self._download_progress.emit(percent, downloaded, total_size)

            self._download_complete.emit()

        except Exception as e:
            self._download_error.emit(str(e))

    def _update_download_progress(self, percent, downloaded, total):
        mb_downloaded = downloaded / (1024 * 1024)
        if total > 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
            mb_total = total / (1024 * 1024)
            self.status_label.setText(tr("MSG_DOWNLOADING_PROGRESS").format(downloaded=f"{mb_downloaded:.1f}", total=f"{mb_total:.1f}"))
        else:
            self.progress_bar.setRange(0, 0)  # indeterminate
            self.status_label.setText(tr("MSG_DOWNLOADING_UPDATE") + f" ({mb_downloaded:.1f} MB)")

    def _on_download_complete(self):
        self.progress_bar.setValue(100)
        self.status_label.setText(tr("MSG_DOWNLOAD_COMPLETE"))
        self.cancel_btn.setVisible(False)
        self.close_btn.setVisible(True)

        self.output_log.appendPlainText(tr("MSG_DOWNLOADED_TO").format(path=self.download_path))
        self.output_log.appendPlainText("\n" + tr("MSG_CLICK_RUN_INSTALLER"))

        run_btn = QPushButton(tr("BTN_RUN_INSTALLER"))
        run_btn.clicked.connect(self._run_installer)
        self.layout().itemAt(self.layout().count() - 1).layout().insertWidget(0, run_btn)

    def _on_download_error(self, error: str):
        self.status_label.setText(tr("MSG_DOWNLOAD_FAILED"))
        self.output_log.appendPlainText(tr("MSG_ERROR_DETAIL").format(error=error))
        self.output_log.appendPlainText(tr("MSG_DOWNLOAD_MANUALLY"))
        self.output_log.appendPlainText("https://github.com/tokeeto/shoggoth/releases/latest")
        self.cancel_btn.setVisible(False)
        self.close_btn.setVisible(True)

    def _run_installer(self):
        if not self.download_path or not self.download_path.exists():
            return
        try:
            if sys.platform == 'win32':
                import os
                os.startfile(str(self.download_path))
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(self.download_path)])
            else:
                self.download_path.chmod(self.download_path.stat().st_mode | 0o111)
                subprocess.Popen([str(self.download_path)])
            QApplication.quit()
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("DLG_ERROR"),
                f"{tr('ERR_UPDATE_OCCURRED')}:\n{e}\n\n{tr('MSG_DOWNLOAD_MANUALLY_FROM')}\n{self.download_path}"
            )

    def _on_cancel(self):
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

        self.checker.update_available.connect(self._on_update_available)
        self.checker.check_complete.connect(self._on_check_complete)
        self.checker.check_failed.connect(self._on_check_failed)

        self._is_manual_check = False

    def should_check_for_updates(self) -> bool:
        if self.checker.installation_type == InstallationType.DEVELOPMENT:
            logger.info("Skipping update check in development mode")
            return False
        if not self.settings.getboolean('Shoggoth', 'auto_check_updates', True):
            return False
        return True

    def check_for_updates_async(self):
        self._is_manual_check = False
        self.checker.check_for_updates()

    def check_for_updates_manual(self):
        self._is_manual_check = True
        if self.checker.installation_type == InstallationType.DEVELOPMENT:
            QMessageBox.information(
                self.parent_widget,
                tr("DLG_DEVELOPMENT_MODE"),
                tr("MSG_UPDATES_DISABLED_DEV")
            )
            return
        self.checker.check_for_updates()

    def _on_check_complete(self, has_update: bool):
        if not has_update and self._is_manual_check:
            QMessageBox.information(
                self.parent_widget,
                tr("DLG_UP_TO_DATE"),
                tr("MSG_LATEST_VERSION")
            )

    def _on_update_available(self, version_info: VersionInfo):
        skipped = self.settings.get('Shoggoth', 'skipped_version', '')
        if not self._is_manual_check and skipped == version_info.version:
            logger.info(f"Skipping update notification for version {version_info.version}")
            return

        dialog = UpdateDialog(version_info, self.checker.current_version, self.parent_widget)
        dialog.exec()

        if dialog.result_action == UpdateDialog.UPDATE_NOW:
            self._perform_update(version_info)
        elif dialog.result_action == UpdateDialog.SKIP_VERSION:
            self.settings.set('Shoggoth', 'skipped_version', version_info.version)
            self.settings.save()

    def _on_check_failed(self, error: str):
        if self._is_manual_check:
            QMessageBox.warning(
                self.parent_widget,
                tr("DLG_UPDATE_CHECK_FAILED"),
                tr("MSG_CHECK_FAILED_RETRY")
            )

    def _perform_update(self, version_info: VersionInfo):
        dialog = UpdateProgressDialog(version_info, self.checker.installation_type, self.parent_widget)
        dialog.show()
        dialog.start_update()
        dialog.exec()
