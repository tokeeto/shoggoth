"""Translation editor widget for Shoggoth.

Shows original field values (greyed, read-only) above editable translation
fields.  Changes are persisted to the Translation object immediately.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QGroupBox, QFrame,
)
from PySide6.QtCore import Qt

from shoggoth.i18n import tr


# Face-level fields that are worth translating: (field_name, display_label, multiline)
FACE_TEXT_FIELDS = [
    ('title',       'Title',    False),
    ('subtitle',    'Subtitle', False),
    ('text',        'Text',     True),
    ('flavor_text', 'Flavor',   True),
]


class TranslationFieldPair(QWidget):
    """Shows a read-only original value above an editable translation field."""

    def __init__(self, label, original, translated='', multiline=False, parent=None):
        super().__init__(parent)
        self.multiline = multiline

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(2)

        layout.addWidget(QLabel(f'<b>{label}</b>'))

        # Original value — greyed, read-only
        if multiline:
            orig = QPlainTextEdit()
            orig.setPlainText(original or '')
            orig.setMaximumHeight(70)
        else:
            orig = QLineEdit()
            orig.setText(original or '')
        orig.setReadOnly(True)
        orig.setStyleSheet('color: grey;')
        layout.addWidget(orig)

        # Editable translation input
        if multiline:
            self.input = QPlainTextEdit()
            self.input.setPlainText(translated or '')
            self.input.setMaximumHeight(100)
        else:
            self.input = QLineEdit()
            self.input.setText(translated or '')
        layout.addWidget(self.input)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        self.setLayout(layout)

    def value(self):
        if self.multiline:
            return self.input.toPlainText()
        return self.input.text()

    def connect_changed(self, slot):
        if self.multiline:
            self.input.textChanged.connect(slot)
        else:
            self.input.textChanged.connect(slot)


class TranslationEditor(QWidget):
    """Editor panel for translating a single card.

    Displays original field values (greyed, read-only) above editable
    translation fields.  Changes are written to the Translation object and
    persisted to disk immediately on each keystroke.
    """

    def __init__(self, card, translation, parent=None):
        super().__init__(parent)
        self.card = card
        self.translation = translation
        self._fields = {}   # key -> TranslationFieldPair

        overlay = translation.get_overlay(card.id) or {}
        front_overlay = overlay.get('front', {})
        back_overlay = overlay.get('back', {})

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Card-level fields ───────────────────────────────────────────────
        card_group = QGroupBox('Card')
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(8, 8, 8, 8)

        w = TranslationFieldPair('Name', card.data.get('name', ''), overlay.get('name', ''))
        w.connect_changed(self._save)
        self._fields['name'] = w
        card_layout.addWidget(w)

        card_group.setLayout(card_layout)
        layout.addWidget(card_group)

        # ── Front face fields ───────────────────────────────────────────────
        front_group = QGroupBox(tr('TAB_FRONT'))
        front_layout = QVBoxLayout()
        front_layout.setContentsMargins(8, 8, 8, 8)

        for field, label, multiline in FACE_TEXT_FIELDS:
            original = card.front.get(field, '')
            if not original:
                continue
            w = TranslationFieldPair(label, original, front_overlay.get(field, ''), multiline)
            w.connect_changed(self._save)
            self._fields[f'front.{field}'] = w
            front_layout.addWidget(w)

        front_group.setLayout(front_layout)
        layout.addWidget(front_group)

        # ── Back face fields ────────────────────────────────────────────────
        back_group = QGroupBox(tr('TAB_BACK'))
        back_layout = QVBoxLayout()
        back_layout.setContentsMargins(8, 8, 8, 8)

        for field, label, multiline in FACE_TEXT_FIELDS:
            original = card.back.get(field, '')
            if not original:
                continue
            w = TranslationFieldPair(label, original, back_overlay.get(field, ''), multiline)
            w.connect_changed(self._save)
            self._fields[f'back.{field}'] = w
            back_layout.addWidget(w)

        back_group.setLayout(back_layout)
        layout.addWidget(back_group)

        layout.addStretch()
        self.setLayout(layout)

    def _save(self):
        """Rebuild overlay from all current field values and persist to disk."""
        overlay = {}
        for key, widget in self._fields.items():
            val = widget.value()
            if not val:
                continue
            if '.' in key:
                face, field = key.split('.', 1)
                overlay.setdefault(face, {})[field] = val
            else:
                overlay[key] = val

        self.translation.set_overlay(self.card.id, overlay)
        self.translation.save()
