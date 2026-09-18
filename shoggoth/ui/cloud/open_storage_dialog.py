"""Dialog for opening a cloud storage project (owned, or shared-with-me) as
a local project file. Only fetches the project's JSON blob here -- its
images/fonts resources are never downloaded eagerly, they resolve lazily via
cloud:// the first time something actually renders them (see
shoggoth.cloud.storage_cache) -- so this is a single small network call, no
progress dialog needed."""
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QDialogButtonBox,
    QMessageBox, QFileDialog, QLabel,
)

from shoggoth.cloud import client, sync
from shoggoth.i18n import tr


class OpenStorageProjectDialog(QDialog):
    def __init__(self, window, config, parent=None):
        super().__init__(parent or window)
        self.window = window
        self.config = config
        self.setWindowTitle(tr("DLG_OPEN_SHARED_PROJECT"))
        self.setMinimumSize(420, 320)
        self._setup_ui()
        self._load_projects()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("MSG_SELECT_CLOUD_PROJECT")))

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _: self._on_open())
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Open).clicked.connect(self._on_open)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _base_url_token(self):
        base_url = self.config.get('Shoggoth', 'publish_base_url', '')
        token = self.config.get('Shoggoth', 'publish_token', '')
        return base_url, token

    def _load_projects(self):
        base_url, token = self._base_url_token()
        try:
            projects = client.list_storage_projects(base_url, token)
        except client.PublishError as exc:
            QMessageBox.warning(self, tr("DLG_OPEN_SHARED_PROJECT"), str(exc))
            projects = []
        for project in projects:
            item = QListWidgetItem(f"{project['title']}  ({project['role']})")
            item.setData(Qt.UserRole, project['id'])
            self.list_widget.addItem(item)
        if not projects:
            placeholder = QListWidgetItem(tr("MSG_NO_CLOUD_PROJECTS"))
            placeholder.setFlags(Qt.NoItemFlags)
            self.list_widget.addItem(placeholder)

    def _on_open(self):
        item = self.list_widget.currentItem()
        if item is None or item.data(Qt.UserRole) is None:
            return
        storage_project_id = item.data(Qt.UserRole)
        base_url, token = self._base_url_token()
        try:
            detail = client.get_storage_project(base_url, token, storage_project_id)
        except client.PublishError as exc:
            QMessageBox.warning(self, tr("DLG_OPEN_SHARED_PROJECT"), str(exc))
            return

        default_name = f"{detail['title']}.shoggoth"
        path_str, _ = QFileDialog.getSaveFileName(
            self, tr("DLG_SAVE_CLOUD_PROJECT_AS"), default_name, "Shoggoth Project (*.shoggoth)"
        )
        if not path_str:
            return

        data = sync.project_data_from_wire(detail['data'])
        data.setdefault('encounter_sets', [])
        data.setdefault('meta', {})['cloud_storage_location'] = f"cloud://{storage_project_id}"

        path = Path(path_str)
        path.write_text(json.dumps(data, indent=2), encoding='utf-8')

        self.window.open_project(str(path))
        self.window.cloud.start(storage_project_id)
        self.accept()
