"""
QApplication-level event filter driving Ctrl+Space snippet sequences: a short
mnemonic key-chain that expands into a standard card-text phrase (see
ui/text_snippets.py for the sequence tree and ui/snippet_overlay.py for the
on-screen key reminder).
"""
from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit

from shoggoth.ui.text_snippets import ROOT, Leaf, CallLeaf
from shoggoth.ui.snippet_overlay import SnippetOverlay
from shoggoth.ui.snippet_loader import load_user_snippets, merge_snippets

_TEXT_WIDGET_TYPES = (QLineEdit, QTextEdit, QPlainTextEdit)


class SnippetSequenceFilter(QObject):
    """Install on a QApplication to enable Ctrl+Space snippet sequences app-wide."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overlay = SnippetOverlay()
        self._reset()
        merge_snippets(ROOT, load_user_snippets())

    def _reset(self):
        self._active = False
        self._node = None
        self._path_labels = []
        self._target = None

    def eventFilter(self, obj, event):
        event_type = event.type()

        if self._active and event_type == QEvent.FocusOut and obj is self._target:
            self._cancel()
            return False

        if event_type != QEvent.KeyPress:
            return False

        if not self._active:
            return self._maybe_start(event)

        return self._handle_key(event)

    def _maybe_start(self, event):
        if event.key() != Qt.Key_Space or not (event.modifiers() & Qt.ControlModifier):
            return False

        target = QApplication.focusWidget()
        if not isinstance(target, _TEXT_WIDGET_TYPES):
            return False

        self._active = True
        self._target = target
        self._node = ROOT
        self._path_labels = []
        self._show_current()
        return True

    def _handle_key(self, event):
        if event.key() == Qt.Key_Escape:
            self._cancel()
            return True

        text = event.text().lower()
        if not text:
            # Modifier-only key press (e.g. holding Ctrl) - swallow and keep waiting.
            return True

        choice = self._node.options.get(text)
        if choice is None:
            return True

        label, child = choice
        if isinstance(child, Leaf):
            self._insert_text(child.build())
            self._cancel()
        elif isinstance(child, CallLeaf):
            self._invoke_call_leaf(child)
            self._cancel()
        else:
            self._node = child
            self._path_labels.append(label)
            self._show_current()
        return True

    def _invoke_call_leaf(self, leaf):
        face, card, project = self._resolve_context()
        try:
            result = leaf.fn(face, card, project)
        except Exception as exc:
            print(f'Snippet function raised an error: {exc}')
            return
        if isinstance(result, str):
            self._insert_text(result)

    def _resolve_context(self):
        from shoggoth.ui.face_editor import FaceEditor
        import shoggoth

        face = None
        widget = self._target
        while widget is not None:
            if isinstance(widget, FaceEditor):
                face = widget.face
                break
            widget = widget.parent()

        app = getattr(shoggoth, 'app', None)
        card = face.card if face is not None else getattr(app, 'current_card', None)
        project = card.project if card is not None else (app.current_project() if app else None)
        return face, card, project

    def _show_current(self):
        if self._path_labels:
            breadcrumb = ' > '.join(self._path_labels)
            text = f'{breadcrumb}\n{self._node.title}: {self._node.hint}'
        else:
            text = self._node.hint
        self.overlay.show_text(text, self._target)

    def _cancel(self):
        self.overlay.hide_overlay()
        self._reset()

    def _insert_text(self, text):
        widget = self._target
        if isinstance(widget, QLineEdit):
            widget.insert(text)
        else:
            cursor = widget.textCursor()
            cursor.insertText(text)
            widget.setTextCursor(cursor)
