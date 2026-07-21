"""
Small floating popup that reminds the user which keys are available at the
current step of a Ctrl+Space snippet sequence (see ui/snippet_input.py).
"""
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette

_COLORS_LIGHT = {'bg': '#fffbe6', 'border': '#a05020', 'text': '#332200'}
_COLORS_DARK = {'bg': '#3a3020', 'border': '#ffaa66', 'text': '#f0e6d0'}


class SnippetOverlay(QWidget):
    """Frameless, non-activating popup showing the current sequence step."""

    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        self.label = QLabel(self)
        layout.addWidget(self.label)

    def _is_dark(self):
        app = QApplication.instance()
        if app:
            return app.palette().color(QPalette.ColorRole.Window).lightness() < 128
        return False

    def show_text(self, text, anchor_widget):
        colors = _COLORS_DARK if self._is_dark() else _COLORS_LIGHT
        self.setStyleSheet(
            f"SnippetOverlay {{ background: {colors['bg']}; "
            f"border: 1px solid {colors['border']}; border-radius: 4px; }} "
            f"QLabel {{ color: {colors['text']}; background: transparent; }}"
        )
        self.label.setText(text)
        self.adjustSize()

        cursor_rect = anchor_widget.cursorRect()
        anchor_point = anchor_widget.mapToGlobal(cursor_rect.bottomLeft())
        self.move(anchor_point.x(), anchor_point.y() + 8)
        self.show()

    def hide_overlay(self):
        self.hide()
