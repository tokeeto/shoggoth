"""
FaceEditor base class for Shoggoth face editors
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QComboBox,
    QLabel, QCompleter
)
from PySide6.QtCore import Signal, Qt

from shoggoth.ui.editor_widgets import NoScrollComboBox, ALL_CARD_TYPES, FULLART_CARD_TYPES
from shoggoth.ui.field_widgets import LabeledLineEdit, LabeledTraitEdit, LabeledTextEdit
from shoggoth.ui.card_widgets import IllustrationWidget, IconsWidget
from shoggoth.i18n import tr

# Map raw card type identifiers to translation keys
_TYPE_TR_KEYS = {
    'asset': 'TYPE_ASSET', 'event': 'TYPE_EVENT', 'skill': 'TYPE_SKILL',
    'investigator': 'TYPE_INVESTIGATOR', 'investigator_back': 'TYPE_INVESTIGATOR_BACK',
    'enemy': 'TYPE_ENEMY', 'treachery': 'TYPE_TREACHERY',
    'location': 'TYPE_LOCATION', 'location_back': 'TYPE_LOCATION_BACK',
    'act': 'TYPE_ACT', 'act_back': 'TYPE_ACT_BACK',
    'agenda': 'TYPE_AGENDA', 'agenda_back': 'TYPE_AGENDA_BACK',
    'scenario': 'TYPE_SCENARIO', 'chaos': 'TYPE_CHAOS',
    'customizable': 'TYPE_CUSTOMIZABLE', 'customizable_back': 'TYPE_CUSTOMIZABLE_BACK',
    'story': 'TYPE_STORY', 'player': 'TYPE_PLAYER',
    'encounter': 'TYPE_ENCOUNTER', 'enemy_deck': 'TYPE_ENEMY_DECK',
    'act_agenda_full': 'TYPE_ACT_AGENDA_FULL', 'act_agenda_full_back': 'TYPE_ACT_AGENDA_FULL_BACK',
}


def get_type_display_name(raw_type: str) -> str:
    """Return translated display name for a card type, or raw name if no translation."""
    key = _TYPE_TR_KEYS.get(raw_type)
    return tr(key) if key else raw_type


class FaceEditor(QWidget):
    """Base class for all face editors"""

    # Signal emitted when type changes and editor should be swapped
    type_changed = Signal(object)  # Emits the face object

    # Fields that carry translatable prose content
    TRANSLATABLE_FIELDS = frozenset({'name', 'subtitle', 'text', 'flavor_text', 'traits'})

    def __init__(self, face, parent=None):
        super().__init__(parent)
        self.face = face
        self.fields = {}
        self.updating = False  # Prevent recursive updates
        self.field_containers = {}  # field_name -> outer container widget

        # Main layout
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        # Always add type selector first
        self.add_type_selector()

        # Then setup custom fields
        self.setup_ui()

        # Load data
        self.load_data()

    def add_type_selector(self):
        """Add type combobox - shown in all editors"""
        type_layout = QHBoxLayout()
        type_label = QLabel(tr("FIELD_TYPE"))
        type_label.setMinimumWidth(50)

        self.type_combo = NoScrollComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.setInsertPolicy(QComboBox.NoInsert)
        for raw_type in ALL_CARD_TYPES:
            self.type_combo.addItem(get_type_display_name(raw_type), raw_type)
        self.type_combo.addItem(tr("FULLART_VARIANTS"), "__separator__")
        for raw_type in FULLART_CARD_TYPES:
            self.type_combo.addItem(get_type_display_name(raw_type), raw_type)

        # Add autocomplete using display names
        display_names = [get_type_display_name(t) for t in ALL_CARD_TYPES + FULLART_CARD_TYPES]
        completer = QCompleter(display_names)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.type_combo.setCompleter(completer)

        # Connect to handle changes - use signals that fire on "commit" not every keystroke
        # activated: fires when user selects from dropdown
        # lineEdit().editingFinished: fires on Enter or focus loss
        self.type_combo.activated.connect(self._on_type_committed)
        self.type_combo.lineEdit().editingFinished.connect(self._on_type_committed)

        self.fields['type'] = self.type_combo

        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_combo)
        type_widget = QWidget()
        type_widget.setLayout(type_layout)
        self.main_layout.addWidget(type_widget)

    def _on_type_committed(self, _=None):
        """Handle type field commit (Enter, focus loss, or dropdown selection)"""
        if self.updating:
            return

        value = self.type_combo.currentData() or self.type_combo.currentText()
        old_type = self.face.get('type')
        if value and value != old_type:
            self.face.set('type', value)
            # Emit signal to trigger editor swap
            self.type_changed.emit(self.face)

    def setup_ui(self):
        """Override in subclasses to add custom fields"""
        pass

    def load_data(self):
        """Load data from face into fields"""
        self.updating = True
        for field_name, widget in self.fields.items():
            value = self.face.get(field_name, '')
            self.set_widget_value(widget, value)
        self.updating = False

    def set_widget_value(self, widget, value):
        """Set widget value based on type"""
        if isinstance(widget, QLineEdit):
            if isinstance(value, list):
                widget.setText(', '.join(str(v) for v in value))
            else:
                widget.setText(str(value) if value else '')
        elif isinstance(widget, QTextEdit):
            widget.setPlainText(str(value) if value else '')
        elif isinstance(widget, QComboBox):
            # Try to find by data first (for translated combos like type selector)
            str_value = str(value) if value else ''
            for i in range(widget.count()):
                if widget.itemData(i) == str_value:
                    widget.setCurrentIndex(i)
                    return
            widget.setCurrentText(str_value)

    def get_widget_value(self, widget):
        """Get widget value based on type"""
        if isinstance(widget, QLineEdit):
            return widget.text()
        elif isinstance(widget, QTextEdit):
            return widget.toPlainText()
        elif isinstance(widget, QComboBox):
            return widget.currentData() or widget.currentText()
        return ''

    # Fields that require type conversion
    INTEGER_FIELDS = {}
    FLOAT_FIELDS = {'illustration_scale', 'illustration_pan_x', 'illustration_pan_y'}
    LIST_FIELDS = {'classes'}  # Fields stored as lists but displayed as comma-separated

    def on_field_changed(self, field_name):
        """Handle field change"""
        if self.updating:
            return

        widget = self.fields.get(field_name)
        if not widget:
            return

        value = self.get_widget_value(widget)

        # Convert value to appropriate type
        if value:
            if field_name in self.INTEGER_FIELDS:
                try:
                    value = int(value)
                except ValueError:
                    return  # Invalid integer, don't update
            elif field_name in self.FLOAT_FIELDS:
                try:
                    value = float(value)
                except ValueError:
                    return  # Invalid float, don't update
            elif field_name in self.LIST_FIELDS:
                # Convert comma-separated string to list
                value = [v.strip() for v in value.split(',') if v.strip()]
            self.face.set(field_name, value)
        else:
            self.face.set(field_name, None)

        # Emit data_changed signal on parent CardEditor if it exists
        parent = self.parent()
        while parent:
            if hasattr(parent, 'data_changed'):
                parent.data_changed.emit()
                break
            parent = parent.parent()

    def add_labeled_line(self, label, field_name):
        """Helper to add a labeled line edit"""
        widget = LabeledLineEdit(label)
        widget.input.textChanged.connect(lambda: self.on_field_changed(field_name))
        self.fields[field_name] = widget.input
        self.field_containers[field_name] = widget
        self.main_layout.addWidget(widget)
        return widget

    def add_trait_field(self, label=None, field_name="traits"):
        """Helper to add a trait field with autocomplete"""
        if label is None:
            label = tr("FIELD_TRAITS")
        widget = LabeledTraitEdit(label)
        widget.input.textChanged.connect(lambda: self.on_field_changed(field_name))
        self.fields[field_name] = widget.input
        self.field_containers[field_name] = widget
        self.main_layout.addWidget(widget)
        return widget

    def add_labeled_text(self, label, field_name, use_arkham=False):
        """Helper to add a labeled text edit"""
        widget = LabeledTextEdit(label, use_arkham_editor=use_arkham)
        widget.input.textChanged.connect(lambda: self.on_field_changed(field_name))
        self.fields[field_name] = widget.input
        self.field_containers[field_name] = widget
        self.main_layout.addWidget(widget)
        return widget

    def add_copyright_collection_row(self):
        """Add copyright and collection fields side by side at the bottom"""
        row_widget = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)

        # Copyright field
        copyright_input = LabeledLineEdit(tr("FIELD_COPYRIGHT"))
        copyright_input.input.textChanged.connect(lambda: self.on_field_changed('copyright'))
        self.fields['copyright'] = copyright_input.input
        row_layout.addWidget(copyright_input)

        # Collection field
        collection_input = LabeledLineEdit(tr("FIELD_COLLECTION"))
        collection_input.input.textChanged.connect(lambda: self.on_field_changed('collection'))
        self.fields['collection'] = collection_input.input
        row_layout.addWidget(collection_input)

        row_widget.setLayout(row_layout)
        self.main_layout.addWidget(row_widget)

    def add_illustration_widget(self):
        """Add illustration widget"""
        # Determine which side this face is on
        face_side = 'front' if self.face == self.face.card.front else 'back'
        illustration = IllustrationWidget(face_side=face_side, project=self.face.card.project)
        self.illustration_widget = illustration

        # Add fields
        self.fields['illustration'] = illustration.path_input.input
        self.fields['illustration_pan_y'] = illustration.pan_y_input.input
        self.fields['illustration_pan_x'] = illustration.pan_x_input.input
        self.fields['illustration_scale'] = illustration.scale_input.input
        self.fields['illustrator'] = illustration.artist_input.input

        # Connect signals
        illustration.path_input.input.textChanged.connect(lambda: self.on_field_changed('illustration'))
        illustration.pan_y_input.input.textChanged.connect(lambda: self.on_field_changed('illustration_pan_y'))
        illustration.pan_x_input.input.textChanged.connect(lambda: self.on_field_changed('illustration_pan_x'))
        illustration.scale_input.input.textChanged.connect(lambda: self.on_field_changed('illustration_scale'))
        illustration.artist_input.input.textChanged.connect(lambda: self.on_field_changed('illustrator'))

        self.main_layout.addWidget(illustration)
        return illustration

    def enter_translation_mode(self):
        """Hide non-translatable fields."""
        translatable_containers = {
            w for name, w in self.field_containers.items()
            if name in self.TRANSLATABLE_FIELDS
        }
        for i in range(self.main_layout.count()):
            item = self.main_layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None:
                w.setVisible(w in translatable_containers)

    def exit_translation_mode(self):
        """Restore all fields."""
        for i in range(self.main_layout.count()):
            item = self.main_layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None:
                w.setVisible(True)
        self.load_data()
