"""Browse project icons and insert their inline-image references."""
from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QListView, QMessageBox, QPushButton,
    QPlainTextEdit, QTextEdit, QVBoxLayout,
)

from shoggoth.i18n import tr


class IconBrowserDialog(QDialog):
    """Visual picker for SVG/PNG icons in a project's ``icons`` directory."""

    def __init__(self, project, insert_target=None, parent=None):
        super().__init__(parent)
        self.project = project
        self._insert_target = None
        self.setWindowTitle(tr("DLG_ICON_BROWSER"))
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("HELP_ICON_BROWSER")))

        self.icon_list = QListWidget()
        self.icon_list.setViewMode(QListView.ViewMode.IconMode)
        self.icon_list.setFlow(QListView.Flow.LeftToRight)
        self.icon_list.setWrapping(True)
        self.icon_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.icon_list.setMovement(QListView.Movement.Static)
        self.icon_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.icon_list.setIconSize(QSize(64, 64))
        self.icon_list.setGridSize(QSize(120, 112))
        self.icon_list.currentItemChanged.connect(self._update_reference)
        layout.addWidget(self.icon_list, 1)

        self.empty_label = QLabel(tr("MSG_ICON_BROWSER_EMPTY"))
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

        footer = QHBoxLayout()
        self.reference = QLineEdit()
        self.reference.setReadOnly(True)
        footer.addWidget(self.reference, 1)
        self.white_checkbox = QCheckBox(tr("LABEL_ICON_BROWSER_WHITE"))
        self.white_checkbox.setChecked(True)
        self.white_checkbox.toggled.connect(self._update_reference)
        footer.addWidget(self.white_checkbox)
        layout.addLayout(footer)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.copy_button = QPushButton(tr("BTN_ICON_BROWSER_COPY"))
        self.copy_button.clicked.connect(self._copy_reference)
        buttons.addWidget(self.copy_button)
        self.insert_button = QPushButton(tr("BTN_ICON_BROWSER_INSERT"))
        self.insert_button.clicked.connect(self._insert_reference)
        buttons.addWidget(self.insert_button)
        layout.addLayout(buttons)

        self.set_insert_target(insert_target)
        self._populate_icons()

    def set_insert_target(self, widget):
        if self._insert_target is widget:
            return
        if self._insert_target is not None:
            self._insert_target.destroyed.disconnect(self._insert_target_destroyed)
        self._insert_target = widget
        self.insert_button.setEnabled(widget is not None)
        if widget is not None:
            widget.destroyed.connect(self._insert_target_destroyed)

    def _insert_target_destroyed(self, *_args):
        self._insert_target = None
        self.insert_button.setEnabled(False)

    def _populate_icons(self):
        icon_dir = Path(self.project.folder) / "icons"
        if icon_dir.is_dir():
            try:
                paths = sorted(
                    (path for path in icon_dir.rglob("*")
                     if path.is_file() and path.suffix.lower() in {".svg", ".png"}),
                    key=lambda path: path.relative_to(icon_dir).as_posix().casefold(),
                )
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    tr("DLG_ICON_BROWSER"),
                    tr("MSG_ICON_BROWSER_READ_ERROR").format(error=exc),
                )
                self.empty_label.setText(tr("MSG_ICON_BROWSER_READ_ERROR").format(error=exc))
                self.icon_list.hide()
                self.empty_label.show()
                self.copy_button.setEnabled(False)
                self.insert_button.setEnabled(False)
                return
        else:
            paths = []

        for path in paths:
            relative_path = path.relative_to(self.project.folder).as_posix()
            label = path.relative_to(icon_dir).as_posix()
            item = QListWidgetItem(QIcon(str(path)), label)
            item.setData(Qt.ItemDataRole.UserRole, relative_path)
            item.setToolTip(relative_path)
            self.icon_list.addItem(item)

        if not paths:
            self.icon_list.hide()
            self.empty_label.show()
            self.copy_button.setEnabled(False)
            self.insert_button.setEnabled(False)
        else:
            self.icon_list.setCurrentRow(0)

    def _update_reference(self, *_args):
        item = self.icon_list.currentItem()
        if item is None:
            self.reference.clear()
            self.copy_button.setEnabled(False)
            self.insert_button.setEnabled(False)
            return

        path = html.escape(item.data(Qt.ItemDataRole.UserRole), quote=True)
        color = ' color="inverted"' if self.white_checkbox.isChecked() else ""
        self.reference.setText(f'<image src="{path}"{color}>')
        self.copy_button.setEnabled(True)
        self.insert_button.setEnabled(self._insert_target is not None)

    def _copy_reference(self):
        if self.reference.text():
            QApplication.clipboard().setText(self.reference.text())

    def _insert_reference(self):
        target = self._insert_target
        if target is None or not self.reference.text():
            return

        text = self.reference.text()
        if isinstance(target, QLineEdit):
            target.insert(text)
        elif isinstance(target, (QTextEdit, QPlainTextEdit)):
            cursor = target.textCursor()
            cursor.insertText(text)
            target.setTextCursor(cursor)
        else:
            return

        self.accept()
        target.setFocus()


def open_icon_browser(window):
    """Open or raise the icon browser for the active project."""
    project = window.active_project
    if project is None:
        QMessageBox.information(
            window,
            tr("DLG_ICON_BROWSER"),
            tr("MSG_ICON_BROWSER_NO_PROJECT"),
        )
        return

    dialog = getattr(window, "_icon_browser_dialog", None)
    if dialog is not None and dialog.isVisible() and dialog.project is project:
        dialog.set_insert_target(getattr(window, "_last_edit_widget", None))
        dialog.raise_()
        dialog.activateWindow()
        return

    if dialog is not None:
        dialog.close()

    dialog = IconBrowserDialog(
        project,
        getattr(window, "_last_edit_widget", None),
        parent=window,
    )
    window._icon_browser_dialog = dialog
    dialog.finished.connect(
        lambda *_args: setattr(window, "_icon_browser_dialog", None)
        if window._icon_browser_dialog is dialog else None
    )
    if hasattr(window, "file_browser"):
        dialog._active_project_changed_slot = (
            lambda active: dialog.close() if active is not project else None
        )
        window.file_browser.active_project_changed.connect(dialog._active_project_changed_slot)

        def disconnect_project_signal(*_args):
            window.file_browser.active_project_changed.disconnect(dialog._active_project_changed_slot)

        dialog.finished.connect(disconnect_project_signal)
    dialog.show()
