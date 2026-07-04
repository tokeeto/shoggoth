"""
Field widgets for Shoggoth using PySide6
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit, QComboBox, QCompleter,
    QLabel, QPushButton, QCheckBox, QStackedWidget, QFrame
)
from PySide6.QtCore import Qt, Signal

from shoggoth.ui.text_editor import ArkhamTextEdit, ArkhamTextHighlighter
from shoggoth.ui.floating_label_widget import FloatingLabelTextEdit, FloatingLabelLineEdit
from shoggoth.ui.editor_widgets import NoScrollComboBox
from shoggoth.i18n import tr

# Known traits for autocomplete (loaded from highlighter)
KNOWN_TRAITS = sorted(ArkhamTextHighlighter(None).known_traits)

# Known card classes for autocomplete
KNOWN_CLASSES = [
    "seeker", "guardian", "rogue", "mystic", "survivor", "specialist",
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
        if not self.hasFocus():
            return
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


class ClassSelectorWidget(QWidget):
    """Class selector with mode dropdown and context-specific controls.

    Modes:
      None         → classes = None
      Player       → 5 class toggle buttons plus Specialist; none selected = ['neutral'], else selected list
      Weakness     → Basic checkbox; ['weakness'] or ['basic weakness']
      Story        → ['story'], no extra controls
      Custom       → free-text field (comma-separated)
    """

    classesChanged = Signal()

    PLAYER_CLASSES = ['guardian', 'seeker', 'rogue', 'mystic', 'survivor']
    SPECIALIST_CLASS = 'specialist'

    MODE_NONE = 0
    MODE_PLAYER = 1
    MODE_WEAKNESS = 2
    MODE_STORY = 3
    MODE_CUSTOM = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Top row: label + mode dropdown
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        label = QLabel(tr("FIELD_CLASSES"))
        label.setMinimumWidth(50)

        self.mode_combo = NoScrollComboBox()
        self.mode_combo.addItems([
            tr("CLASS_MODE_NONE"),
            tr("CLASS_MODE_PLAYER"),
            tr("CLASS_MODE_WEAKNESS"),
            tr("CLASS_MODE_STORY"),
            tr("CLASS_MODE_CUSTOM"),
        ])

        top_row.addWidget(label)
        top_row.addWidget(self.mode_combo, 1)
        top_widget = QWidget()
        top_widget.setLayout(top_row)
        layout.addWidget(top_widget)

        # Stacked content area (hidden when mode has no extra controls)
        self.stack = QStackedWidget()

        # Page 0: None — empty
        self.stack.addWidget(QWidget())

        # Page 1: Player classes — 5 toggle buttons, separator, then Specialist
        player_page = QWidget()
        player_layout = QHBoxLayout()
        player_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.setSpacing(2)
        self._class_buttons = {}
        for cls in self.PLAYER_CLASSES:
            key = f"CLASS_{cls.upper()}"
            btn = QPushButton(tr(key))
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.clicked.connect(self._on_player_changed)
            player_layout.addWidget(btn)
            self._class_buttons[cls] = btn

        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        player_layout.addWidget(separator)

        specialist_btn = QPushButton(tr("CLASS_SPECIALIST"))
        specialist_btn.setCheckable(True)
        specialist_btn.setFixedHeight(26)
        specialist_btn.clicked.connect(self._on_player_changed)
        player_layout.addWidget(specialist_btn)
        self._class_buttons[self.SPECIALIST_CLASS] = specialist_btn

        player_page.setLayout(player_layout)
        self.stack.addWidget(player_page)

        # Page 2: Weakness — checkbox
        weakness_page = QWidget()
        weakness_layout = QHBoxLayout()
        weakness_layout.setContentsMargins(0, 0, 0, 0)
        self.basic_checkbox = QCheckBox(tr("CLASS_WEAKNESS_BASIC"))
        self.basic_checkbox.stateChanged.connect(self._on_weakness_changed)
        weakness_layout.addWidget(self.basic_checkbox)
        weakness_layout.addStretch()
        weakness_page.setLayout(weakness_layout)
        self.stack.addWidget(weakness_page)

        # Page 3: Story — no extra controls
        self.stack.addWidget(QWidget())

        # Page 4: Custom — free-text input
        custom_page = QWidget()
        custom_layout = QVBoxLayout()
        custom_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_input = ClassLineEdit()
        self.custom_input.textChanged.connect(self._on_custom_changed)
        custom_layout.addWidget(self.custom_input)
        custom_page.setLayout(custom_layout)
        self.stack.addWidget(custom_page)

        layout.addWidget(self.stack)
        self.setLayout(layout)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._update_stack_visibility(self.MODE_NONE)

    def _update_stack_visibility(self, index):
        has_content = index in (self.MODE_PLAYER, self.MODE_WEAKNESS, self.MODE_CUSTOM)
        self.stack.setVisible(has_content)
        if has_content:
            self.stack.setCurrentIndex(index)

    def _on_mode_changed(self, index):
        self._update_stack_visibility(index)
        if not self._updating:
            self.classesChanged.emit()

    def _on_player_changed(self):
        if not self._updating:
            self.classesChanged.emit()

    def _on_weakness_changed(self):
        if not self._updating:
            self.classesChanged.emit()

    def _on_custom_changed(self):
        if not self._updating:
            self.classesChanged.emit()

    def get_classes(self):
        """Return the current classes as a list, or None."""
        mode = self.mode_combo.currentIndex()
        if mode == self.MODE_NONE:
            return None
        elif mode == self.MODE_PLAYER:
            all_classes = self.PLAYER_CLASSES + [self.SPECIALIST_CLASS]
            selected = [c for c in all_classes if self._class_buttons[c].isChecked()]
            return selected if selected else ['neutral']
        elif mode == self.MODE_WEAKNESS:
            return ['basic weakness'] if self.basic_checkbox.isChecked() else ['weakness']
        elif mode == self.MODE_STORY:
            return ['story']
        else:  # Custom
            text = self.custom_input.text().strip()
            if not text:
                return None
            return [v.strip() for v in text.split(',') if v.strip()]

    def set_classes(self, value):
        """Set widget state from a classes list value (or None)."""
        self._updating = True
        if not value:  # None or empty string or empty list
            self._set_mode(self.MODE_NONE)
        elif isinstance(value, list):
            player_set = set(self.PLAYER_CLASSES) | {self.SPECIALIST_CLASS}
            value_set = set(value)
            if value_set <= (player_set | {'neutral'}):
                self._set_mode(self.MODE_PLAYER)
                for cls, btn in self._class_buttons.items():
                    btn.setChecked(cls in value_set)
            elif value == ['weakness']:
                self._set_mode(self.MODE_WEAKNESS)
                self.basic_checkbox.setChecked(False)
            elif value == ['basic weakness']:
                self._set_mode(self.MODE_WEAKNESS)
                self.basic_checkbox.setChecked(True)
            elif value == ['story']:
                self._set_mode(self.MODE_STORY)
            else:
                self._set_mode(self.MODE_CUSTOM)
                self.custom_input.setText(', '.join(str(v) for v in value))
        else:
            self._set_mode(self.MODE_CUSTOM)
            self.custom_input.setText(str(value) if value else '')
        self._updating = False

    def _set_mode(self, index):
        self.mode_combo.setCurrentIndex(index)
        self._update_stack_visibility(index)


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
