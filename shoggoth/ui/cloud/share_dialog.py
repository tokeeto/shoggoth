"""Manage a cloud storage project's share grants (viewer/editor), reachable
from the project's right-click context menu (Share...) once it's backed by
a cloud storage project -- see tree_context_menu.py's share_project()."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QListWidget, QListWidgetItem,
    QLineEdit, QComboBox, QPushButton, QDialogButtonBox, QMessageBox, QLabel,
)

from shoggoth.cloud import client
from shoggoth.i18n import tr


class ShareProjectDialog(QDialog):
    def __init__(self, project, config, parent=None):
        super().__init__(parent)
        self.project = project
        self.config = config
        self.storage_project_id = project.data['meta']['celaeno_id']
        self.setWindowTitle(tr("DLG_SHARE_PROJECT"))
        self.setMinimumWidth(420)
        self._setup_ui()
        self._load_shares()

    def _base_url_token(self):
        base_url = self.config.get('Shoggoth', 'publish_base_url', '')
        token = self.config.get('Shoggoth', 'publish_token', '')
        return base_url, token

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("MSG_SHARE_PROJECT_INTRO").format(name=self.project.name)))

        self.share_list = QListWidget()
        layout.addWidget(self.share_list)

        remove_btn = QPushButton(tr("BTN_REMOVE_SHARE"))
        remove_btn.clicked.connect(self._on_remove)
        layout.addWidget(remove_btn)

        add_form = QFormLayout()
        self.email_input = QLineEdit()
        add_form.addRow(tr("LABEL_SHARE_EMAIL"), self.email_input)
        self.role_combo = QComboBox()
        self.role_combo.addItem(tr("ROLE_VIEWER"), "viewer")
        self.role_combo.addItem(tr("ROLE_EDITOR"), "editor")
        add_form.addRow(tr("LABEL_SHARE_ROLE"), self.role_combo)
        layout.addLayout(add_form)

        add_row = QHBoxLayout()
        add_row.addStretch()
        add_btn = QPushButton(tr("BTN_ADD_SHARE"))
        add_btn.clicked.connect(self._on_add)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _load_shares(self):
        self.share_list.clear()
        base_url, token = self._base_url_token()
        try:
            shares = client.list_storage_shares(base_url, token, self.storage_project_id)
        except client.PublishError as exc:
            QMessageBox.warning(self, tr("DLG_SHARE_PROJECT"), str(exc))
            return
        for share in shares:
            item = QListWidgetItem(f"{share['email']}  ({share['role']})")
            item.setData(Qt.UserRole, share['user_id'])
            self.share_list.addItem(item)

    def _on_add(self):
        email = self.email_input.text().strip()
        if not email:
            return
        role = self.role_combo.currentData()
        base_url, token = self._base_url_token()
        try:
            client.add_storage_share(base_url, token, self.storage_project_id, email, role)
        except client.PublishError as exc:
            QMessageBox.warning(self, tr("DLG_SHARE_PROJECT"), str(exc))
            return
        self.email_input.clear()
        self._load_shares()

    def _on_remove(self):
        item = self.share_list.currentItem()
        if item is None:
            return
        user_id = item.data(Qt.UserRole)
        base_url, token = self._base_url_token()
        try:
            client.remove_storage_share(base_url, token, self.storage_project_id, user_id)
        except client.PublishError as exc:
            QMessageBox.warning(self, tr("DLG_SHARE_PROJECT"), str(exc))
            return
        self._load_shares()
