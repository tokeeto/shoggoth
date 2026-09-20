"""Minimal dialog for File > Cloud > New Cloud Project: just a name and an
abbreviation. Unlike a local New Project there's no save location to pick --
a cloud project always lives in the cloud folder."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit

from shoggoth.i18n import tr


class NewCloudProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("MENU_CLOUD_NEW_PROJECT").rstrip('.'))
        self.setMinimumWidth(380)

        layout = QFormLayout(self)
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText(tr("PLACEHOLDER_ABC"))
        self.code_input.setMaxLength(5)
        layout.addRow(tr("FIELD_ABBREVIATION"), self.code_input)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(tr("PLACEHOLDER_EXAMPLE_PROJECT"))
        layout.addRow(tr("FIELD_NAME"), self.name_input)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        layout.addRow(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _accept(self):
        if not self.name_input.text().strip():
            self.error_label.setText(tr("MSG_ENTER_PROJECT_NAME"))
            return
        if not self.code_input.text().strip():
            self.error_label.setText(tr("MSG_ENTER_ABBREVIATION"))
            return
        self.accept()

    def get_result(self):
        return self.name_input.text().strip(), self.code_input.text().strip()
