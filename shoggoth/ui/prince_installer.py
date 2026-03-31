"""
Modal dialog for downloading and installing Prince XML locally.
"""
import io
import platform
import stat
import tarfile
import threading
import zipfile
from pathlib import Path

import requests
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton,
)

from shoggoth.files import prince_dir
from shoggoth.i18n import tr

PRINCE_URLS = {
    'Windows': 'https://www.princexml.com/download/prince-16.2-win64.zip',
    'Darwin':  'https://www.princexml.com/download/prince-16.2-macos.zip',
    'Linux':   'https://www.princexml.com/download/prince-16.2-linux-generic-x86_64.tar.gz',
}


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _Worker(QObject):
    progress = Signal(int, str)   # (percent 0-100, status label)
    finished = Signal(bool, str)  # (success, error message)

    def run(self):
        try:
            system = platform.system()
            url = PRINCE_URLS.get(system)
            if url is None:
                self.finished.emit(False, f"Unsupported platform: {system}")
                return

            # --- download ---------------------------------------------------
            self.progress.emit(0, tr("PRINCE_INSTALL_DOWNLOADING"))
            response = requests.get(url, stream=True, timeout=120)
            response.raise_for_status()

            total = int(response.headers.get('content-length', 0))
            downloaded = 0
            chunks = []
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int(downloaded / total * 80)
                        self.progress.emit(pct, tr("PRINCE_INSTALL_DOWNLOADING"))

            data = b''.join(chunks)

            # --- extract ----------------------------------------------------
            self.progress.emit(80, tr("PRINCE_INSTALL_EXTRACTING"))
            prince_dir.mkdir(parents=True, exist_ok=True)

            if url.endswith('.tar.gz'):
                _extract_tar_gz(data, prince_dir)
            else:
                _extract_zip(data, prince_dir)

            # Make binary executable on Unix
            if system in ('Linux', 'Darwin'):
                bin_path = prince_dir / 'lib' / 'prince' / 'bin' / 'prince'
                if bin_path.exists():
                    bin_path.chmod(bin_path.stat().st_mode
                                   | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            self.progress.emit(100, tr("PRINCE_INSTALL_DONE"))
            self.finished.emit(True, "")

        except Exception as exc:
            self.finished.emit(False, str(exc))


# ---------------------------------------------------------------------------
# Archive helpers
# ---------------------------------------------------------------------------

def _strip_top(name: str) -> str:
    """Remove the top-level directory prefix from an archive member path."""
    parts = name.replace('\\', '/').split('/', 1)
    return parts[1] if len(parts) > 1 else ''


def _extract_zip(data: bytes, target: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for member in zf.infolist():
            rel = _strip_top(member.filename)
            if not rel:
                continue
            dest = target / rel
            if member.filename.endswith('/'):
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(member))


def _extract_tar_gz(data: bytes, target: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tf:
        for member in tf.getmembers():
            rel = _strip_top(member.name)
            if not rel:
                continue
            dest = target / rel
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                dest.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(member)
                if src is not None:
                    dest.write_bytes(src.read())
                dest.chmod(member.mode)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class PrinceInstallerDialog(QDialog):
    """Downloads and extracts Prince XML into the application data directory."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("DLG_PRINCE_INSTALLER"))
        self.setMinimumWidth(460)
        self.setWindowModality(Qt.ApplicationModal)
        self._success = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        intro = QLabel(tr("PRINCE_INSTALL_INTRO"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._install_btn = QPushButton(tr("BTN_INSTALL_PRINCE"))
        self._install_btn.setDefault(True)
        self._install_btn.clicked.connect(self._start_install)
        btn_row.addWidget(self._install_btn)
        self._close_btn = QPushButton(tr("BTN_CANCEL"))
        self._close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

    def _start_install(self):
        self._install_btn.setEnabled(False)
        self._close_btn.setEnabled(False)
        self._progress.setVisible(True)

        worker = _Worker()
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        # Keep a reference so it isn't GC'd before the thread finishes
        self._worker = worker

        threading.Thread(target=worker.run, daemon=True).start()

    def _on_progress(self, pct: int, message: str):
        self._progress.setValue(pct)
        self._status_label.setText(message)

    def _on_finished(self, success: bool, error: str):
        if success:
            self._success = True
            self._status_label.setText(tr("PRINCE_INSTALL_DONE"))
            self._progress.setValue(100)
            self._close_btn.setText(tr("BTN_CLOSE"))
            self._close_btn.setEnabled(True)
            self._close_btn.clicked.disconnect(self.reject)
            self._close_btn.clicked.connect(self.accept)
        else:
            self._status_label.setText(
                tr("PRINCE_INSTALL_FAILED").format(error=error)
            )
            self._install_btn.setEnabled(True)
            self._close_btn.setEnabled(True)
