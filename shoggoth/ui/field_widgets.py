"""
Field widgets for Shoggoth using PySide6
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QTextEdit, QComboBox, QCompleter
)
from PySide6.QtCore import Qt, Signal

from shoggoth.ui.text_editor import ArkhamTextEdit, ArkhamTextHighlighter
from shoggoth.ui.floating_label_widget import FloatingLabelTextEdit, FloatingLabelLineEdit
from shoggoth.i18n import tr

# Known traits for autocomplete (loaded from highlighter)
KNOWN_TRAITS = sorted(ArkhamTextHighlighter(None).known_traits)

# Known card classes for autocomplete
KNOWN_CLASSES = [
    "seeker", "guardian", "rogue", "mystic", "survivor",
    "neutral", "story", "weakness", "story weakness", "basic weakness",
]


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


class LabeledLineEdit(QWidget):
    """A labeled line edit widget with floating label"""

    textChanged = Signal(str)

    def __init__(self, label_text):
        super().__init__()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.floating_widget = FloatingLabelLineEdit(label_text)
        self.input = self.floating_widget.input
        self.input.textChanged.connect(self.textChanged.emit)

        layout.addWidget(self.floating_widget)
        self.setLayout(layout)

    def text(self):
        return self.input.text()

    def setText(self, text):
        self.floating_widget.setText(text)


class TraitLineEdit(QLineEdit):
    """Line edit with autocomplete for Arkham Horror traits.

    Supports multiple traits separated by ". " (e.g., "Humanoid. Creature. Monster.")
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create completer with known traits
        self.completer = QCompleter(KNOWN_TRAITS)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.activated.connect(self.insert_completion)

        # Connect text changes to update completer
        self.textChanged.connect(self.update_completer)

    def get_current_word_bounds(self):
        """Get the start and end positions of the current word being typed."""
        text = self.text()
        cursor_pos = self.cursorPosition()

        # Find start: look for ". " or start of string
        start = 0
        search_pos = cursor_pos - 1
        while search_pos >= 0:
            if search_pos >= 1 and text[search_pos-1:search_pos+1] == '. ':
                start = search_pos + 1
                break
            search_pos -= 1

        # Skip leading whitespace
        while start < cursor_pos and text[start] == ' ':
            start += 1

        return start, cursor_pos

    def update_completer(self):
        """Update completer prefix based on current word being typed."""
        start, end = self.get_current_word_bounds()
        current_word = self.text()[start:end].strip()

        if current_word and len(current_word) >= 1:
            self.completer.setCompletionPrefix(current_word)
            if self.completer.completionCount() > 0:
                self.completer.complete()
            else:
                self.completer.popup().hide()
        else:
            self.completer.popup().hide()

    def insert_completion(self, completion):
        """Insert the selected completion with proper formatting."""
        text = self.text()
        start, end = self.get_current_word_bounds()

        # Format trait: capitalize first letter, add dot
        formatted_trait = completion[0].upper() + completion[1:] + '.'

        # Build new text
        before = text[:start]
        after = text[end:]

        new_text = before + formatted_trait + after
        self.setText(new_text)

        # Position cursor after the inserted trait
        new_cursor_pos = start + len(formatted_trait)
        self.setCursorPosition(new_cursor_pos)

    def keyPressEvent(self, event):
        """Handle key press events for completer interaction."""
        if self.completer.popup().isVisible():
            if event.key() in (Qt.Key_Enter, Qt.Key_Return):
                if self.completer.currentCompletion():
                    self.insert_completion(self.completer.currentCompletion())
                    self.completer.popup().hide()
                    return

        super().keyPressEvent(event)


class LabeledTraitEdit(QWidget):
    """A labeled line edit widget with trait autocomplete and floating label."""

    textChanged = Signal(str)

    def __init__(self, label_text="Traits"):
        super().__init__()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Use FloatingLabelLineEdit but replace the input with TraitLineEdit
        self.floating_widget = FloatingLabelLineEdit(label_text)

        # Replace the standard QLineEdit with TraitLineEdit
        old_input = self.floating_widget.input
        self.floating_widget.input = TraitLineEdit()
        self.floating_widget.input.setStyleSheet(old_input.styleSheet())

        # Replace in layout
        self.floating_widget.layout().removeWidget(old_input)
        old_input.deleteLater()
        self.floating_widget.layout().addWidget(self.floating_widget.input)

        # Reconnect events
        self.floating_widget.input.textChanged.connect(self.floating_widget.on_text_changed)
        self.floating_widget.input.installEventFilter(self.floating_widget)

        self.input = self.floating_widget.input
        self.input.textChanged.connect(self.textChanged.emit)

        layout.addWidget(self.floating_widget)
        self.setLayout(layout)

    def text(self):
        return self.input.text()

    def setText(self, text):
        self.floating_widget.setText(text)


class ClassLineEdit(QLineEdit):
    """Line edit with autocomplete for Arkham Horror card classes (comma-separated)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.completer = QCompleter(KNOWN_CLASSES)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.activated.connect(self.insert_completion)

        self.textChanged.connect(self.update_completer)

    def _current_token_bounds(self):
        text = self.text()
        cursor_pos = self.cursorPosition()
        before_cursor = text[:cursor_pos]
        last_comma = before_cursor.rfind(',')
        start = last_comma + 1
        while start < cursor_pos and text[start] == ' ':
            start += 1
        return start, cursor_pos

    def update_completer(self):
        start, end = self._current_token_bounds()
        prefix = self.text()[start:end].strip()
        if prefix:
            self.completer.setCompletionPrefix(prefix)
            if self.completer.completionCount() > 0:
                self.completer.complete()
            else:
                self.completer.popup().hide()
        else:
            self.completer.popup().hide()

    def insert_completion(self, completion):
        text = self.text()
        start, end = self._current_token_bounds()
        new_text = text[:start] + completion + text[end:]
        self.setText(new_text)
        self.setCursorPosition(start + len(completion))

    def keyPressEvent(self, event):
        if self.completer.popup().isVisible():
            if event.key() in (Qt.Key_Enter, Qt.Key_Return):
                if self.completer.currentCompletion():
                    self.insert_completion(self.completer.currentCompletion())
                    self.completer.popup().hide()
                    return
        super().keyPressEvent(event)


class LabeledClassEdit(QWidget):
    """A labeled line edit with class autocomplete and floating label."""

    textChanged = Signal(str)

    def __init__(self, label_text="Classes"):
        super().__init__()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.floating_widget = FloatingLabelLineEdit(label_text)

        old_input = self.floating_widget.input
        self.floating_widget.input = ClassLineEdit()
        self.floating_widget.input.setStyleSheet(old_input.styleSheet())

        self.floating_widget.layout().removeWidget(old_input)
        old_input.deleteLater()
        self.floating_widget.layout().addWidget(self.floating_widget.input)

        self.floating_widget.input.textChanged.connect(self.floating_widget.on_text_changed)
        self.floating_widget.input.installEventFilter(self.floating_widget)

        self.input = self.floating_widget.input
        self.input.textChanged.connect(self.textChanged.emit)

        layout.addWidget(self.floating_widget)
        self.setLayout(layout)

    def text(self):
        return self.input.text()

    def setText(self, text):
        self.floating_widget.setText(text)


class LabeledTextEdit(QWidget):
    """A labeled text edit widget with floating label"""

    textChanged = Signal()

    def __init__(self, label_text, use_arkham_editor=False):
        super().__init__()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # For Arkham text editor, we need to replace the input after creation
        self.floating_widget = FloatingLabelTextEdit(label_text)

        if use_arkham_editor:
            # Replace the standard QTextEdit with ArkhamTextEdit
            old_input = self.floating_widget.input
            self.floating_widget.input = ArkhamTextEdit()
            self.floating_widget.input.setStyleSheet(old_input.styleSheet())
            self.floating_widget.input.setMinimumHeight(136)
            self.floating_widget.input.setMaximumHeight(176)

            # Replace in layout
            self.floating_widget.layout().removeWidget(old_input)
            old_input.deleteLater()
            self.floating_widget.layout().addWidget(self.floating_widget.input)

            # Reconnect events
            self.floating_widget.input.textChanged.connect(self.floating_widget.on_text_changed)
            self.floating_widget.input.installEventFilter(self.floating_widget)

        self.input = self.floating_widget.input
        self.input.textChanged.connect(self.textChanged.emit)

        layout.addWidget(self.floating_widget)
        self.setLayout(layout)

    def toPlainText(self):
        return self.input.toPlainText()

    def setPlainText(self, text):
        self.floating_widget.setPlainText(text)
