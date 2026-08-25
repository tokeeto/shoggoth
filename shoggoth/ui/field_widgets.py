"""
Field widgets for Shoggoth using PySide6

Compact style: every field is a small static uppercase label directly above its input
(no floating-label animation) — see compact_theme.py / the "Card Editor Style Guide" doc.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit, QComboBox, QLabel, QPushButton, QFrame
)
from PySide6.QtCore import Signal

from shoggoth.ui.text_editor import ArkhamTextEdit, ArkhamTextHighlighter
from shoggoth.ui.compact_widgets import TagChipsField, ClassChipsField
from shoggoth.i18n import tr

# Known traits for autocomplete (loaded from highlighter)
KNOWN_TRAITS = sorted(ArkhamTextHighlighter(None).known_traits)


class FieldWidget:
    """Base class for field widgets that sync with card data"""

    def __init__(self, widget, card_key, converter=str, deconverter=str):
        self.widget = widget
        self.card_key = card_key
        self.converter = converter
        self.deconverter = deconverter
        self._updating = False

    def update_from_card(self, card_data):
        """Update widget from card data"""
        self._updating = True
        value = card_data.data.get(self.card_key)

        if value == '<copy>':
            self.set_widget_value(value)
        else:
            self.set_widget_value(self.deconverter(value) if value else '')
        self._updating = False

    def update_card(self, card_data, value):
        """Update card from widget value"""
        if self._updating:
            return False

        try:
            if value == '<copy>':
                card_data.set(self.card_key, value)
            else:
                card_data.set(self.card_key, self.converter(value) if value else None)
            return True
        except ValueError as e:
            print(f'Error updating card: {e}')
            return False

    def set_widget_value(self, value):
        """Set the widget's value - override in subclasses"""
        if isinstance(self.widget, QLineEdit):
            self.widget.setText(str(value))
        elif isinstance(self.widget, QTextEdit):
            self.widget.setPlainText(str(value))
        elif isinstance(self.widget, QComboBox):
            # For editable comboboxes, set the text directly
            if self.widget.isEditable():
                self.widget.setCurrentText(str(value))
            else:
                self.widget.setCurrentText(str(value))

    def get_widget_value(self):
        """Get the widget's current value"""
        if isinstance(self.widget, QLineEdit):
            return self.widget.text()
        elif isinstance(self.widget, QTextEdit):
            return self.widget.toPlainText()
        elif isinstance(self.widget, QComboBox):
            return self.widget.currentText()
        return ''


class CompactLabeledField(QWidget):
    """Base for the compact "small uppercase label above the field" wrapper widgets.

    Subclasses set self.input to the real editing widget and add it to the layout.
    Common marker class so FaceEditor can detect "this field has a label wrapper that
    supports placeholder-style fallback display" without knowing every concrete subclass.
    """

    def __init__(self, label_text):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.label = QLabel(label_text.upper())
        self.label.setProperty("role", "field-label")
        layout.addWidget(self.label)

        self._field_layout = layout
        self._has_placeholder = False

    def _add_input(self, widget):
        self._field_layout.addWidget(widget)


class LabeledLineEdit(CompactLabeledField):
    """A labeled line edit widget with a compact static label"""

    textChanged = Signal(str)

    def __init__(self, label_text):
        super().__init__(label_text)
        self.input = QLineEdit()
        self.input.textChanged.connect(self.textChanged.emit)
        self._add_input(self.input)

    def text(self):
        return self.input.text()

    def setText(self, text):
        self.input.setText(text)

    def setPlaceholderText(self, text):
        self.input.setPlaceholderText(text)
        self._has_placeholder = bool(text)


UNIQUE_TAG = "<unique>"


class UniqueNameField(CompactLabeledField):
    """Name field with a toggleable "unique" star to its left.

    Many cards are unique — printed as "<unique>Count Dracula" (or "<unique><name>")
    rather than just "Count Dracula". The star toggles that literal "<unique>" prefix
    on the *stored* value; the display field itself only ever shows the name text.
    No trimming beyond the exact "<unique>" tag — whatever else is in the value is
    respected as-is.
    """

    textChanged = Signal(str)

    def __init__(self, label_text):
        super().__init__(label_text)
        self._unique = False
        self._updating = False

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self.unique_btn = QPushButton("★")
        self.unique_btn.setCheckable(True)
        self.unique_btn.setProperty("role", "unique-btn")
        self.unique_btn.setFixedSize(28, 28)
        self.unique_btn.setToolTip(tr("TOOLTIP_UNIQUE"))
        self.unique_btn.toggled.connect(self._on_toggle_unique)
        row.addWidget(self.unique_btn)

        self.input = QLineEdit()
        self.input.textChanged.connect(self._on_changed)
        row.addWidget(self.input)

        row_widget = QWidget()
        row_widget.setLayout(row)
        self._add_input(row_widget)

    def _on_changed(self, *_):
        if not self._updating:
            self.textChanged.emit(self.text())

    def _on_toggle_unique(self, checked):
        """Turning the star on with no name text yet: pull in the placeholder (the
        "<name>" render macro, or an inherited name) as real text, so the stored
        value reads "<unique><name>" rather than just "<unique>" with nothing to show."""
        if checked and not self.input.text() and self.input.placeholderText():
            self._updating = True
            self.input.setText(self.input.placeholderText())
            self._updating = False
        self._on_changed()

    def text(self):
        """The raw stored value: the <unique> tag (if toggled) plus the field text, verbatim."""
        prefix = UNIQUE_TAG if self.unique_btn.isChecked() else ""
        return prefix + self.input.text()

    def setText(self, value):
        """Load a raw stored value: a literal leading "<unique>" (if present) becomes the
        toggle state; everything else goes into the field untouched — no trimming."""
        self._updating = True
        value = value or ""
        unique = value.startswith(UNIQUE_TAG)
        self.unique_btn.setChecked(unique)
        self.input.setText(value[len(UNIQUE_TAG):] if unique else value)
        self._updating = False

    def setPlaceholderText(self, text):
        text = text or ""
        if text.startswith(UNIQUE_TAG):
            text = text[len(UNIQUE_TAG):]
        self.input.setPlaceholderText(text)
        self._has_placeholder = bool(text)


class LabeledTraitEdit(CompactLabeledField):
    """A labeled trait chip editor with autocomplete and a compact static label."""

    textChanged = Signal(str)

    def __init__(self, label_text="Traits"):
        super().__init__(label_text)
        self.input = TagChipsField(add_label=f"+ {tr('FIELD_TRAITS').lower()}", completions=KNOWN_TRAITS)
        self.input.textChanged.connect(self.textChanged.emit)
        self._add_input(self.input)

    def text(self):
        return self.input.text()

    def setText(self, text):
        self.input.setText(text)

    def setPlaceholderText(self, text):
        self.input.set_placeholder(text)
        self._has_placeholder = bool(text)


class ClassSelectorWidget(QWidget):
    """Class selector: colored chips (semantic per-class colors) with a "+" suggestion
    popup offering Guardian/Seeker/Rogue/Survivor/Mystic/Neutral/Specialist/Weakness/
    Basic Weakness. See ClassChipsField (compact_widgets.py) for the chip/popup itself —
    this wrapper just adds the compact field label above it.
    """

    classesChanged = Signal()

    def __init__(self, parent=None, default_classes=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel(tr("FIELD_CLASSES").upper())
        label.setProperty("role", "field-label")
        layout.addWidget(label)

        self.chips = ClassChipsField(default_classes=default_classes)
        self.chips.changed.connect(self.classesChanged.emit)
        layout.addWidget(self.chips)

    def get_classes(self):
        return self.chips.get_classes()

    def set_classes(self, value):
        self.chips.set_classes(value)


class LabeledTextEdit(CompactLabeledField):
    """A labeled text edit widget with a compact static label"""

    textChanged = Signal()

    def __init__(self, label_text, use_arkham_editor=False):
        super().__init__(label_text)

        self.input = ArkhamTextEdit() if use_arkham_editor else QTextEdit()
        # Drop the native sunken scroll-area frame — it reads as a heavier box than a
        # QLineEdit's own border, and its reserved frame width was throwing off vertical
        # alignment against line-edit siblings in the same row (e.g. Flavor vs Victory).
        self.input.setFrameShape(QFrame.NoFrame)
        if use_arkham_editor:
            self.input.setMinimumHeight(136)
            self.input.setMaximumHeight(176)
        else:
            self.input.setMinimumHeight(60)
        self.input.textChanged.connect(self.textChanged.emit)
        self._add_input(self.input)

    def toPlainText(self):
        return self.input.toPlainText()

    def setPlainText(self, text):
        self.input.setPlainText(text)

    def setPlaceholderText(self, text):
        self.input.setPlaceholderText(text)
        self._has_placeholder = bool(text)
