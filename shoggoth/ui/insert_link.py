"""
Ctrl+L "Insert Link".

A QApplication-level event filter (sibling of ``SnippetSequenceFilter``): when
focus is in any editable text widget it opens the shared
:class:`ElementSelectorDialog` and inserts a ``<:{id} >`` reference for the
chosen element at the cursor, replacing any selection and leaving the caret just
before the ``>`` so the user can type the field name (e.g. ``name``).

The Edit -> Insert Link menu action calls :func:`insert_link_at_focus`, which
routes to the same code path.
"""
from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit

import shoggoth
from shoggoth.i18n import tr

_TEXT_WIDGET_TYPES = (QLineEdit, QTextEdit, QPlainTextEdit)

_dialog_open = False


class InsertLinkFilter(QObject):
    """Install on the QApplication to enable Ctrl+L app-wide."""

    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress:
            return False
        if event.key() != Qt.Key_L or not (event.modifiers() & Qt.ControlModifier):
            return False

        target = QApplication.focusWidget()
        if not _is_editable_text_widget(target):
            return False

        open_insert_link(target)
        return True


def insert_link_at_focus():
    """Entry point for the menu action - act on whatever text widget has focus."""
    target = QApplication.focusWidget()
    if _is_editable_text_widget(target):
        open_insert_link(target)


def open_insert_link(widget):
    """Open the picker and, on confirm, insert the reference into ``widget``."""
    global _dialog_open
    if _dialog_open:
        return

    app = getattr(shoggoth, 'app', None)
    project = getattr(app, 'active_project', None) if app else None
    if project is None:
        return

    from shoggoth.ui.element_selector import ElementSelectorDialog

    dialog = ElementSelectorDialog(
        project,
        title=tr("DLG_INSERT_LINK"),
        instructions=tr("HELP_INSERT_LINK"),
        parent=widget.window(),
    )
    chosen = []
    dialog.element_chosen.connect(chosen.append)

    _dialog_open = True
    try:
        dialog.exec()
    finally:
        _dialog_open = False

    if chosen:
        _insert_reference(widget, chosen[0].id)


def _is_editable_text_widget(widget):
    return isinstance(widget, _TEXT_WIDGET_TYPES) and not widget.isReadOnly()


def _insert_reference(widget, element_id):
    """Insert ``<:{id} >`` at the cursor, caret left of the closing ``>``."""
    text = f"<:{element_id} >"
    if isinstance(widget, QLineEdit):
        widget.insert(text)  # replaces the current selection, if any
        widget.setCursorPosition(widget.cursorPosition() - 1)
    else:
        cursor = widget.textCursor()
        cursor.insertText(text)  # replaces the current selection, if any
        cursor.movePosition(QTextCursor.Left)
        widget.setTextCursor(cursor)
    widget.setFocus()
