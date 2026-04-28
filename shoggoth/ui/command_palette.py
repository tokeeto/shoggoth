"""
Command palette with fuzzy search over all available commands.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QLabel, QWidget, QHBoxLayout
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from shoggoth.i18n import tr
from shoggoth.ui.goto_dialog import fuzzy_match


@dataclass
class Command:
    name: str
    category: str
    action: Callable[[], None]
    shortcut: str = ""
    enabled: Callable[[], bool] = field(default_factory=lambda: (lambda: True))

    @property
    def is_enabled(self) -> bool:
        try:
            return bool(self.enabled())
        except Exception:
            return False

    @property
    def search_text(self) -> str:
        return f"{self.category} {self.name}"


class CommandListItem(QWidget):
    """Widget for a single command entry in the palette list."""

    def __init__(self, command: Command, search_term: str = ""):
        super().__init__()

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        cat_label = QLabel(command.category)
        cat_font = QFont()
        cat_font.setPointSize(8)
        cat_label.setFont(cat_font)
        cat_label.setFixedWidth(110)
        cat_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(cat_label)

        self.name_label = QLabel()
        name_font = QFont()
        name_font.setPointSize(10)
        self.name_label.setFont(name_font)
        self._set_highlighted(command.name, search_term)
        layout.addWidget(self.name_label, stretch=1)

        if command.shortcut:
            kbd = QLabel(command.shortcut)
            kbd_font = QFont()
            kbd_font.setPointSize(8)
            kbd.setFont(kbd_font)
            kbd.setStyleSheet(
                "color: #aaa; background-color: rgba(128,128,128,40);"
                " border-radius: 3px; padding: 1px 5px;"
            )
            layout.addWidget(kbd)

        self.setLayout(layout)

    def _set_highlighted(self, name: str, search_term: str):
        if not search_term:
            self.name_label.setText(name)
            return
        score, indices = fuzzy_match(search_term, name)
        if score == 0:
            self.name_label.setText(name)
            return
        html = ""
        for i, ch in enumerate(name):
            esc = ch.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            if i in indices:
                html += f'<span style="background-color:#ffeb3b;color:#000;">{esc}</span>'
            else:
                html += esc
        self.name_label.setText(html)


class CommandPaletteDialog(QDialog):
    """
    Global command palette opened with Ctrl+P.
    Lists all registered commands with fuzzy search.
    """

    def __init__(self, commands: list[Command], parent=None):
        super().__init__(parent)
        self.all_commands = commands

        self.setWindowTitle(tr("CMD_PALETTE_TITLE"))
        self.setModal(True)
        self.resize(660, 440)

        self._setup_ui()
        self._update_results("")
        self.search_input.setFocus()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("CMD_PALETTE_PLACEHOLDER"))
        search_font = QFont()
        search_font.setPointSize(12)
        self.search_input.setFont(search_font)
        self.search_input.setMinimumHeight(40)
        self.search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.search_input)

        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self._execute_current)
        layout.addWidget(self.results_list)

        self.hint_label = QLabel()
        self.hint_label.setStyleSheet("color: #888; font-size: 9pt; padding: 4px 10px;")
        layout.addWidget(self.hint_label)

        self.setLayout(layout)

    def _on_text_changed(self, text: str):
        if hasattr(self, "_debounce"):
            self._debounce.stop()
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(lambda: self._update_results(text))
        self._debounce.start(80)

    def _update_results(self, search_term: str):
        self.results_list.clear()

        if not search_term:
            ranked = list(self.all_commands)
        else:
            scored = []
            for cmd in self.all_commands:
                score, _ = fuzzy_match(search_term, cmd.name)
                if score == 0:
                    cat_score, _ = fuzzy_match(search_term, cmd.search_text)
                    score = max(0, cat_score - 10)
                if score > 0:
                    scored.append((cmd, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            ranked = [cmd for cmd, _ in scored]

        ranked = ranked[:200]
        self.hint_label.setText(f"{len(ranked)} / {len(self.all_commands)}")

        first_selectable = -1
        for i, cmd in enumerate(ranked):
            item = QListWidgetItem()
            widget = CommandListItem(cmd, search_term)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.UserRole, cmd)
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, widget)
            if not cmd.is_enabled:
                item.setFlags(item.flags() & ~(Qt.ItemIsSelectable | Qt.ItemIsEnabled))
            elif first_selectable == -1:
                first_selectable = i

        if first_selectable >= 0:
            self.results_list.setCurrentRow(first_selectable)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self.reject()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self._execute_current()
        elif key == Qt.Key_Down:
            self._nudge(1)
        elif key == Qt.Key_Up:
            self._nudge(-1)
        else:
            super().keyPressEvent(event)

    def _nudge(self, direction: int):
        count = self.results_list.count()
        if count == 0:
            return
        row = self.results_list.currentRow()
        for _ in range(count):
            row = (row + direction) % count
            item = self.results_list.item(row)
            if item and (item.flags() & Qt.ItemIsEnabled):
                self.results_list.setCurrentRow(row)
                return

    def _execute_current(self):
        item = self.results_list.currentItem()
        if not item:
            return
        cmd: Command = item.data(Qt.UserRole)
        if cmd and cmd.is_enabled:
            self.accept()
            cmd.action()

    def showEvent(self, event):
        super().showEvent(event)
        self.search_input.setFocus()
        self.search_input.selectAll()
