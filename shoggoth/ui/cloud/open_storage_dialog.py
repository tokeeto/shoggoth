"""Dialog for opening a cloud project (owned, or shared with you).

The project list is fetched on a background thread so the dialog appears
instantly. Picking one just opens it from the cloud folder (see
ui/main_window/cloud.py::open_cloud_project) -- no download happens here at
all; sync fills the project in after it's open."""
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QDialogButtonBox, QLabel,
)

from shoggoth.cloud import client
from shoggoth.i18n import tr


class OpenStorageProjectDialog(QDialog):
    _loaded = Signal(object, str)  # projects (or None), error message

    def __init__(self, window, config, parent=None):
        super().__init__(parent or window)
        self.window = window
        self.config = config
        self.setWindowTitle(tr("DLG_OPEN_SHARED_PROJECT"))
        self.setMinimumSize(420, 320)
        self._setup_ui()
        self._loaded.connect(self._show_projects)
        self._load_projects()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("MSG_SELECT_CLOUD_PROJECT")))

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _: self._on_open())
        layout.addWidget(self.list_widget)
        self._set_placeholder(tr("MSG_LOADING_CLOUD_PROJECTS"))

        buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Open).clicked.connect(self._on_open)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_placeholder(self, text):
        self.list_widget.clear()
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)
        self.list_widget.addItem(item)

    def _load_projects(self):
        base_url = self.config.get('Shoggoth', 'publish_base_url', '')
        token = self.config.get('Shoggoth', 'publish_token', '')

        def task():
            try:
                self._loaded.emit(client.list_storage_projects(base_url, token), '')
            except client.PublishError as exc:
                self._loaded.emit(None, str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _show_projects(self, projects, error):
        if projects is None:
            self._set_placeholder(error)
            return
        if not projects:
            self._set_placeholder(tr("MSG_NO_CLOUD_PROJECTS"))
            return
        self.list_widget.clear()
        for project in projects:
            item = QListWidgetItem(f"{project['title']}  ({project['role']})")
            item.setData(Qt.UserRole, project)
            self.list_widget.addItem(item)

    def _on_open(self):
        item = self.list_widget.currentItem()
        project = item.data(Qt.UserRole) if item else None
        if not project:
            return
        from shoggoth.ui.main_window import cloud
        cloud.open_cloud_project(self.window, project['id'], project['title'], project['role'])
        self.accept()
