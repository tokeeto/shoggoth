"""Standalone Sign In dialog, reachable from the Cloud menu (Cloud > Sign In)
without going through Settings. Shares the actual login call with
SettingsDialog's Publishing tab via shoggoth.cloud.auth.login -- this dialog
only owns the form + persisting the result."""
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QMessageBox,
)

from shoggoth.cloud import auth as cloud_auth
from shoggoth.cloud import client
from shoggoth.i18n import tr


class SignInDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(tr("DLG_CLOUD_SIGN_IN"))
        self.setMinimumWidth(360)
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)

        self.base_url_input = QLineEdit(
            self.config.get('Shoggoth', 'publish_base_url', 'https://celaeno.cards')
        )
        layout.addRow(tr("LABEL_CLOUD_BASE_URL"), self.base_url_input)

        self.email_input = QLineEdit(self.config.get('Shoggoth', 'publish_email', ''))
        layout.addRow(tr("LABEL_CLOUD_EMAIL"), self.email_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addRow(tr("LABEL_CLOUD_PASSWORD"), self.password_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("BTN_CLOUD_LOG_IN"))
        buttons.accepted.connect(self._on_sign_in)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_sign_in(self):
        base_url = self.base_url_input.text().strip()
        email = self.email_input.text().strip()
        password = self.password_input.text()
        try:
            token, user = cloud_auth.login(base_url, email, password)
        except client.PublishError as exc:
            QMessageBox.warning(self, tr("DLG_CLOUD_SIGN_IN"), str(exc))
            return

        self.config.set('Shoggoth', 'publish_base_url', base_url)
        self.config.set('Shoggoth', 'publish_email', user.get('email') or email)
        self.config.set('Shoggoth', 'publish_token', token)
        self.config.set('Shoggoth', 'publish_has_access', bool(user.get('has_access')))
        self.config.save()
        self.accept()
