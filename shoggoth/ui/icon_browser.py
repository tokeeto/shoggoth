"""Browse project icons and insert their inline-image references."""
from __future__ import annotations

import html
import os
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QSize, QRect, QTimer
from PySide6.QtGui import QColor, QIcon, QPen, QPalette
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QListView, QMessageBox, QPushButton, QPlainTextEdit, QStyledItemDelegate,
    QStyle, QTextEdit, QVBoxLayout,
)

from shoggoth.i18n import tr


class IconFileModel(QAbstractListModel):
    """Icon paths with thumbnails loaded only when the view requests them."""

    def __init__(self, project_folder, icon_folder, parent=None):
        super().__init__(parent)
        self.project_folder = project_folder
        self.icon_folder = icon_folder
        self._paths = []
        self._icons = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._paths)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._paths):
            return None

        path = self._paths[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return path.relative_to(self.icon_folder).as_posix()
        if role == Qt.ItemDataRole.UserRole:
            return path.relative_to(self.project_folder).as_posix()
        if role == Qt.ItemDataRole.DecorationRole:
            if path not in self._icons:
                self._icons[path] = QIcon(str(path))
            return self._icons[path]
        if role == Qt.ItemDataRole.ToolTipRole:
            return path.relative_to(self.project_folder).as_posix()
        return None

    def append_paths(self, paths):
        if not paths:
            return
        start = len(self._paths)
        self.beginInsertRows(QModelIndex(), start, start + len(paths) - 1)
        self._paths.extend(paths)
        self.endInsertRows()


class IconItemDelegate(QStyledItemDelegate):
    """Draw consistent square previews and a frame-only selection state."""

    _PREVIEW_SIZE = 76
    _ICON_SIZE = 64

    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect
        preview = QSize(self._PREVIEW_SIZE, self._PREVIEW_SIZE)
        left = rect.left() + (rect.width() - preview.width()) // 2
        preview_rect = QRect(left, rect.top() + 3, preview.width(), preview.height())

        painter.fillRect(preview_rect, QColor("#e8e8e8"))
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon is not None and not icon.isNull():
            pixmap = icon.pixmap(QSize(self._ICON_SIZE, self._ICON_SIZE))
            pixmap = pixmap.scaled(
                QSize(self._ICON_SIZE, self._ICON_SIZE),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon_rect = QRect(
                preview_rect.center().x() - pixmap.width() // 2,
                preview_rect.center().y() - pixmap.height() // 2,
                pixmap.width(),
                pixmap.height(),
            )
            painter.drawPixmap(icon_rect, pixmap)

        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor("#4285c5"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(preview_rect.adjusted(1, 1, -1, -1))

        text_rect = rect.adjusted(2, self._PREVIEW_SIZE + 5, -2, 0)
        label = index.data(Qt.ItemDataRole.DisplayRole) or ""
        label = option.fontMetrics.elidedText(
            label, Qt.TextElideMode.ElideMiddle, text_rect.width()
        )
        painter.setPen(option.palette.color(QPalette.ColorRole.Text))
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            label,
        )
        painter.restore()

    def sizeHint(self, _option, _index):
        return QSize(120, 112)


class IconBrowserDialog(QDialog):
    """Visual picker for SVG/PNG icons in a project's ``icons`` directory."""

    def __init__(self, project, insert_target=None, parent=None):
        super().__init__(parent)
        self.project = project
        self._insert_target = None
        self._active_project_changed_slot: Callable | None = None
        self.setWindowTitle(tr("DLG_ICON_BROWSER"))
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("HELP_ICON_BROWSER")))

        self.icon_list = QListView()
        self.icon_list.setViewMode(QListView.ViewMode.IconMode)
        self.icon_list.setFlow(QListView.Flow.LeftToRight)
        self.icon_list.setWrapping(True)
        self.icon_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.icon_list.setMovement(QListView.Movement.Static)
        self.icon_list.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.icon_list.setGridSize(QSize(120, 112))
        self.icon_list.setUniformItemSizes(True)
        self.icon_list.setLayoutMode(QListView.LayoutMode.Batched)
        self.icon_list.setBatchSize(100)
        self.icon_model = IconFileModel(
            Path(self.project.folder), Path(self.project.folder) / "icons", self.icon_list
        )
        self.icon_list.setModel(self.icon_model)
        self.icon_list.setItemDelegate(IconItemDelegate(self.icon_list))
        self.icon_list.selectionModel().currentChanged.connect(self._update_reference)
        layout.addWidget(self.icon_list, 1)

        self.empty_label = QLabel(tr("MSG_ICON_BROWSER_EMPTY"))
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setText(tr("MSG_ICON_BROWSER_LOADING"))
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

        self._scan_stack = []
        self._scan_errors = []
        self._scan_stopped = False
        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(0)
        self._scan_timer.timeout.connect(self._scan_icon_batch)
        self.finished.connect(self._stop_icon_scan)
        self.set_insert_target(insert_target)
        QTimer.singleShot(0, self._start_icon_scan)

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

    def _start_icon_scan(self):
        if self._scan_stopped:
            return
        icon_dir = self.icon_model.icon_folder
        if not icon_dir.is_dir():
            self._finish_icon_scan()
            return
        try:
            self._scan_stack.append(os.scandir(icon_dir))
        except OSError as exc:
            self._scan_errors.append(str(exc))
            self._finish_icon_scan()
            return
        self._scan_timer.start()

    def _scan_icon_batch(self):
        paths = []
        deadline = time.perf_counter() + 0.008
        inspected = 0
        while self._scan_stack and inspected < 100 and time.perf_counter() < deadline:
            current = self._scan_stack[-1]
            try:
                entry = next(current)
            except StopIteration:
                current.close()
                self._scan_stack.pop()
                continue
            except OSError as exc:
                current.close()
                self._scan_stack.pop()
                self._scan_errors.append(str(exc))
                continue

            inspected += 1
            try:
                if entry.is_dir(follow_symlinks=False):
                    self._scan_stack.append(os.scandir(entry.path))
                elif (entry.is_file(follow_symlinks=False)
                      and Path(entry.name).suffix.lower() in {".svg", ".png"}):
                    paths.append(Path(entry.path))
            except OSError as exc:
                self._scan_errors.append(str(exc))

        previous_count = self.icon_model.rowCount()
        self.icon_model.append_paths(paths)
        if previous_count == 0 and paths:
            self.icon_list.setCurrentIndex(self.icon_model.index(0, 0))
            self.empty_label.hide()
        if not self._scan_stack:
            self._finish_icon_scan()

    def _finish_icon_scan(self):
        self._scan_timer.stop()
        for iterator in self._scan_stack:
            iterator.close()
        self._scan_stack.clear()
        if self.icon_model.rowCount() == 0:
            self.empty_label.setText(tr("MSG_ICON_BROWSER_EMPTY"))
            self.empty_label.show()
            self.copy_button.setEnabled(False)
            self.insert_button.setEnabled(False)
        if self._scan_errors:
            errors = "\n".join(self._scan_errors[:5])
            if len(self._scan_errors) > 5:
                errors += f"\n... and {len(self._scan_errors) - 5} more"
            QMessageBox.warning(
                self,
                tr("DLG_ICON_BROWSER"),
                tr("MSG_ICON_BROWSER_SCAN_ERROR").format(errors=errors),
            )

    def _stop_icon_scan(self, *_args):
        self._scan_stopped = True
        self._scan_timer.stop()
        for iterator in self._scan_stack:
            iterator.close()
        self._scan_stack.clear()

    def _update_reference(self, *_args):
        index = self.icon_list.currentIndex()
        if not index.isValid():
            self.reference.clear()
            self.copy_button.setEnabled(False)
            self.insert_button.setEnabled(False)
            return

        path = html.escape(index.data(Qt.ItemDataRole.UserRole), quote=True)
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
