"""
Card editors for modification projects (see shoggoth.modification).

- TranslationEditor ("Translation View"): only the fields a translator
  works on, each next to the parent's original value.
- ModificationCompareEditor ("Modification View"): the full card editor,
  next to a locked editor showing the parent's original card.

Both edit the modification's own card; the original is a detached copy (see
ModificationProject.original_card), so nothing here can change the parent.
"""
import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QSplitter,
    QToolButton, QVBoxLayout, QWidget,
)

from shoggoth.i18n import tr
from shoggoth.ui import compact_theme
from shoggoth.ui.card_editor import CardEditor
from shoggoth.ui.compact_widgets import Band
from shoggoth.ui.text_editor import ArkhamTextEdit


LINE, RICH, ENTRIES = 'line', 'rich', 'entries'

# The face fields the Translation View shows, in order: (field, label key, kind).
# A field is only listed for a face when the original or the translation has a
# value for it. Label None shows the field name itself.
TRANSLATION_FACE_FIELDS = [
    ('name', 'FIELD_NAME', LINE),
    ('subtitle', 'FIELD_SUBTITLE', LINE),
    ('traits', 'FIELD_TRAITS', LINE),
    ('label', None, LINE),
    ('text', 'FIELD_TEXT', RICH),
    ('text1', None, RICH),
    ('text2', None, RICH),
    ('text3', None, RICH),
    ('flavor_text', 'FIELD_FLAVOR', RICH),
    ('victory', 'FIELD_VICTORY', LINE),
    ('difficulty', 'FIELD_DIFFICULTY', RICH),
    ('chaos_extra', 'FIELD_TOKEN_AREA_TITLE', LINE),
    ('tracking', 'FIELD_TOKEN_AREA_TITLE', LINE),
    ('entries', 'FIELD_ENTRIES', ENTRIES),
    ('checkbox_entries', 'FIELD_ENTRIES', ENTRIES),
]

# Keys inside entry lists that are data rather than text (chaos token names)
_NON_TEXT_ENTRY_KEYS = {'token'}


def _text_leaves(value, path=()):
    """(path, text) for every translatable string inside an entries list --
    e.g. an investigator back's [header, text] pairs, a chaos entry's 'text',
    a customizable option's name and effect (but not its cost)."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _text_leaves(item, path + (index,))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in _NON_TEXT_ENTRY_KEYS:
                yield from _text_leaves(item, path + (key,))


def _set_leaf(value, path, text):
    target = value
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = text


def _leaf_label(label, path):
    parts = [str(step + 1) if isinstance(step, int) else str(step) for step in path]
    return f"{label} {' · '.join(parts)}"


def _extra_text_fields(face):
    """User-defined text fields of this face (a '<name>_region' the renderer
    treats as text), which the manual list above can't know about."""
    from shoggoth.renderer import discovered_text_fields
    known = {field for field, _, _ in TRANSLATION_FACE_FIELDS}
    try:
        return sorted(set(discovered_text_fields(face)) - known)
    except Exception:
        return []


class _TranslationRow:
    """One field: label | original (read-only) | translation | status + reset."""

    def __init__(self, grid, row, label, original, current, rich, on_change):
        self.original = original or ''
        self.on_change = on_change
        self._loading = False

        label_widget = QLabel(label.upper())
        label_widget.setProperty("role", "field-label")
        label_widget.setAlignment(Qt.AlignRight | Qt.AlignTop)
        label_widget.setContentsMargins(0, 6, 0, 0)
        grid.addWidget(label_widget, row, 0)

        if rich:
            self.original_widget = ArkhamTextEdit()
            self.original_widget.setPlainText(self.original)
            self.input = ArkhamTextEdit()
            for widget in (self.original_widget, self.input):
                widget.setMinimumHeight(90)
                widget.setMaximumHeight(200)
            self.input.textChanged.connect(self._changed)
        else:
            self.original_widget = QLineEdit(self.original)
            self.input = QLineEdit()
            self.input.textChanged.connect(self._changed)
        self.original_widget.setReadOnly(True)
        self.original_widget.setProperty("role", "original-value")
        self.original_widget.setToolTip(tr("TOOLTIP_ORIGINAL_VALUE"))

        grid.addWidget(self.original_widget, row, 1)
        grid.addWidget(self.input, row, 2)

        side = QVBoxLayout()
        side.setContentsMargins(0, 4, 0, 0)
        side.setSpacing(2)
        self.status = QLabel("●")
        self.status.setToolTip(tr("TOOLTIP_UNTRANSLATED"))
        self.status.setStyleSheet("color: #d08a1e;")
        reset = QToolButton()
        reset.setText("↺")
        reset.setAutoRaise(True)
        reset.setToolTip(tr("TOOLTIP_RESET_TO_ORIGINAL"))
        reset.clicked.connect(lambda: self._set_text(self.original, emit=True))
        side.addWidget(self.status, 0, Qt.AlignHCenter)
        side.addWidget(reset, 0, Qt.AlignHCenter)
        side.addStretch()
        grid.addLayout(side, row, 3)
        self._set_text(current or '')

    def text(self):
        if isinstance(self.input, QLineEdit):
            return self.input.text()
        return self.input.toPlainText()

    def _set_text(self, text, emit=False):
        self._loading = not emit
        if isinstance(self.input, QLineEdit):
            self.input.setText(text)
        else:
            self.input.setPlainText(text)
        self._loading = False
        self._update_status()

    @property
    def untranslated(self):
        return bool(self.original) and self.text() == self.original

    def _update_status(self):
        self.status.setVisible(self.untranslated)

    def _changed(self, *args):
        self._update_status()
        if not self._loading:
            self.on_change(self.text())


class TranslationEditor(QWidget):
    """The Translation View of a modification's card."""

    data_changed = Signal()

    def __init__(self, card, parent=None):
        super().__init__(parent)
        self.card = card
        self.original = card.project.original_card(card.id)
        self.rows = []
        # No face editors here; see PreviewController.connect_illustration_widgets
        self.front_editor = None
        self.back_editor = None

        outer = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setProperty("role", "band-hint")
        outer.addWidget(self.summary)

        if self.original is None:
            note = QLabel(tr("MSG_CARD_NOT_IN_ORIGINAL"))
            note.setWordWrap(True)
            outer.addWidget(note)

        # Card-level name (what the tree and most lists show)
        self._add_band(outer, tr("BAND_CARD"), [
            (tr("FIELD_NAME"), self._original_card_value('name'), card.data.get('name', ''),
             False, lambda text: self._set_card_value('name', text)),
        ])

        for side, title in (('front', tr("TAB_FRONT")), ('back', tr("TAB_BACK"))):
            rows = self._face_rows(side)
            if rows:
                self._add_band(outer, title, rows)

        outer.addStretch()
        self.setStyleSheet(compact_theme.EDITOR_QSS)
        self._update_summary()

    # ── Building ──────────────────────────────────────────────────────────

    def _add_band(self, layout, title, rows):
        band = Band(title)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        header_original = QLabel(tr("COL_ORIGINAL").upper())
        header_translation = QLabel(tr("COL_TRANSLATION").upper())
        for column, header in ((1, header_original), (2, header_translation)):
            header.setProperty("role", "band-hint")
            grid.addWidget(header, 0, column)
        for index, (label, original, current, rich, setter) in enumerate(rows, start=1):
            row = _TranslationRow(grid, index, label, original, current, rich,
                                  lambda text, s=setter: self._on_row_changed(s, text))
            self.rows.append(row)
        band.content_layout.addLayout(grid)
        layout.addWidget(band)

    def _original_card_value(self, key):
        return self.original.data.get(key, '') if self.original else ''

    def _face_rows(self, side):
        face = getattr(self.card, side)
        original_face = getattr(self.original, side) if self.original else None
        original_data = original_face.data if original_face else {}
        is_investigator_back = face.get_editor() == 'investigator_back'

        fields = list(TRANSLATION_FACE_FIELDS)
        fields += [(name, None, LINE) for name in _extra_text_fields(face)]

        rows = []
        for field, label_key, kind in fields:
            if field == 'text' and is_investigator_back:
                continue  # written from the entries, see _set_entry_leaf
            label = tr(label_key) if label_key else field
            original = original_data.get(field)
            current = face.data.get(field)
            if not original and not current:
                continue
            if kind == ENTRIES:
                rows += self._entry_rows(face, field, label, original, current)
            elif isinstance(original or current, str):
                rows.append((label, original or '', current or '', kind == RICH,
                             lambda text, f=face, k=field: self._set_face_value(f, k, text)))
        return rows

    def _entry_rows(self, face, field, label, original, current):
        original_leaves = dict(_text_leaves(original or []))
        rows = []
        for path, text in _text_leaves(current or []):
            rows.append((_leaf_label(label, path), original_leaves.get(path, ''), text, True,
                         lambda value, f=face, k=field, p=path: self._set_entry_leaf(f, k, p, value)))
        return rows

    # ── Writing ───────────────────────────────────────────────────────────

    def _set_card_value(self, key, text):
        self.card.set(key, text or None)

    def _set_face_value(self, face, key, text):
        face.set(key, text or None)

    def _set_entry_leaf(self, face, key, path, text):
        entries = copy.deepcopy(face.data.get(key) or [])
        _set_leaf(entries, path, text)
        face.set(key, entries)
        if key == 'entries' and face.get_editor() == 'investigator_back':
            # Same as InvestigatorBackEditor: the rendered text is built from the entries
            parts = [f"{entry[0]} {entry[1]}" for entry in entries
                     if isinstance(entry, list) and len(entry) >= 2 and entry[0] and entry[1]]
            face.set('text', "\n".join(parts) if parts else None)

    def _on_row_changed(self, setter, text):
        setter(text)
        self._update_summary()
        self.data_changed.emit()

    def _update_summary(self):
        total = sum(1 for row in self.rows if row.original)
        done = sum(1 for row in self.rows if row.original and not row.untranslated)
        self.summary.setText(tr("MSG_TRANSLATION_PROGRESS").format(done=done, total=total))

    def cleanup(self):
        pass


class ModificationCompareEditor(QWidget):
    """The Modification View of a modification's card: the full editor,
    with the parent's original card locked beside it."""

    data_changed = Signal()

    def __init__(self, card, parent=None):
        super().__init__(parent)
        self.card = card
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)

        self.editor = CardEditor(card)
        self.editor.data_changed.connect(self.data_changed.emit)
        splitter.addWidget(self._titled(tr("LABEL_MODIFIED_CARD"), self.editor))

        self.original_editor = None
        original = card.project.original_card(card.id)
        if original is not None:
            self.original_editor = CardEditor(original)
            self._lock(self.original_editor)
            splitter.addWidget(self._titled(tr("LABEL_ORIGINAL_CARD"), self.original_editor))
            self.editor.view_toggle.valueChanged.connect(self._follow_view)
            self._sync_scrolling(self.editor, self.original_editor)
        else:
            note = QLabel(tr("MSG_CARD_NOT_IN_ORIGINAL"))
            note.setWordWrap(True)
            note.setAlignment(Qt.AlignTop)
            splitter.addWidget(self._titled(tr("LABEL_ORIGINAL_CARD"), note))

    @property
    def front_editor(self):
        return self.editor.front_editor

    @property
    def back_editor(self):
        return self.editor.back_editor

    @staticmethod
    def _titled(title, widget):
        box = QWidget()
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title.upper())
        label.setProperty("role", "band-label")
        label.setContentsMargins(10, 6, 0, 0)
        box_layout.addWidget(label)
        box_layout.addWidget(widget, 1)
        return box

    @staticmethod
    def _lock(editor):
        """Everything that edits is disabled; the Front/Back/Meta/JSON toggle
        and collapsible bands still work, so the original can be browsed.
        Face editors rebuilt later are created inside editor_container and
        inherit its disabled state."""
        editor.name_input.setEnabled(False)
        editor.basic_info_band.content.setEnabled(False)
        editor.editor_container.setEnabled(False)

    def _follow_view(self, value):
        self.original_editor.view_toggle.set_current_value(value)
        self.original_editor._on_view_toggle_changed(value)

    @staticmethod
    def _sync_scrolling(left, right):
        left_scroll = left.findChild(QScrollArea)
        right_scroll = right.findChild(QScrollArea)
        if not left_scroll or not right_scroll:
            return
        a, b = left_scroll.verticalScrollBar(), right_scroll.verticalScrollBar()
        a.valueChanged.connect(lambda value: b.setValue(value) if b.value() != value else None)
        b.valueChanged.connect(lambda value: a.setValue(value) if a.value() != value else None)

    def cleanup(self):
        self.editor.cleanup()
        if self.original_editor:
            self.original_editor.cleanup()
