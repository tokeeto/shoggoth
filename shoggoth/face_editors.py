"""
Face editors for different card types - Consolidated
"""
from PySide6.QtWidgets import (
    QBoxLayout, QSpacerItem, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QPlainTextEdit, QPushButton, QComboBox,
    QLabel, QFileDialog, QGridLayout, QGroupBox, QCompleter, QSpinBox
)
from PySide6.QtCore import Signal, Qt, QSize
from pathlib import Path
import json

# Import helper widgets from editors.py
from shoggoth import editors

# All available card types
ALL_CARD_TYPES = [
    'asset', 'event', 'skill',
    'investigator', 'investigator_back',
    'enemy', 'treachery', 'location', 'location_back',
    'act', 'act_back', 'agenda', 'agenda_back',
    'scenario', 'chaos',
    'customizable', 'story',
    'player', 'encounter',
]
FULLART_CARD_TYPES = [
    'fullart_asset',
    'fullart_event',
    'fullart_skill',
    'fullart_investigator',
    'fullart_enemy',
    'fullart_treachery',
]


class FaceEditor(QWidget):
    """Base class for all face editors"""

    # Signal emitted when type changes and editor should be swapped
    type_changed = Signal(object)  # Emits the face object

    def __init__(self, face, parent=None):
        super().__init__(parent)
        self.face = face
        self.fields = {}
        self.updating = False  # Prevent recursive updates

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
        type_label = QLabel("Type")
        type_label.setMinimumWidth(110)

        self.type_combo = QComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.setInsertPolicy(QComboBox.NoInsert)
        self.type_combo.addItems(ALL_CARD_TYPES)
        self.type_combo.addItem("--- fullart variants ---")
        self.type_combo.addItems(FULLART_CARD_TYPES)

        # Add autocomplete
        completer = QCompleter(ALL_CARD_TYPES+FULLART_CARD_TYPES)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.type_combo.setCompleter(completer)

        # Connect to handle changes
        self.type_combo.currentTextChanged.connect(self.on_type_field_changed)
        self.type_combo.editTextChanged.connect(self.on_type_field_changed)

        self.fields['type'] = self.type_combo

        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_combo)
        type_widget = QWidget()
        type_widget.setLayout(type_layout)
        self.main_layout.addWidget(type_widget)

    def on_type_field_changed(self, value):
        """Handle type field change specially"""
        if self.updating:
            return

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
            widget.setCurrentText(str(value) if value else '')

    def get_widget_value(self, widget):
        """Get widget value based on type"""
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        elif isinstance(widget, QTextEdit):
            return widget.toPlainText().strip()
        elif isinstance(widget, QComboBox):
            return widget.currentText().strip()
        return ''

    # Fields that require type conversion
    INTEGER_FIELDS = {'illustration_pan_x', 'illustration_pan_y'}
    FLOAT_FIELDS = {'illustration_scale'}
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
        widget = editors.LabeledLineEdit(label)
        widget.input.textChanged.connect(lambda: self.on_field_changed(field_name))
        self.fields[field_name] = widget.input
        self.main_layout.addWidget(widget)
        return widget

    def add_labeled_text(self, label, field_name, use_arkham=False):
        """Helper to add a labeled text edit"""
        widget = editors.LabeledTextEdit(label, use_arkham_editor=use_arkham)
        widget.input.textChanged.connect(lambda: self.on_field_changed(field_name))
        self.fields[field_name] = widget.input
        self.main_layout.addWidget(widget)
        return widget

    def add_illustration_widget(self):
        """Add illustration widget"""
        # Determine which side this face is on
        face_side = 'front' if self.face == self.face.card.front else 'back'
        illustration = editors.IllustrationWidget(face_side=face_side)
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


class BaseEditor(FaceEditor):
    """Basic editor with just type field"""

    def setup_ui(self):
        """Type is already added by base class"""
        self.main_layout.addStretch()


class AssetEditor(FaceEditor):
    """Editor for asset cards"""

    def setup_ui(self):
        # Basic fields
        self.add_labeled_line("Name", "name")
        self.add_labeled_line("Subtitle", "subtitle")

        # Grid for compact fields
        grid_widget = QWidget()
        grid_layout = QFormLayout()

        # Traits
        traits_input = editors.LabeledLineEdit("Traits")
        traits_input.input.textChanged.connect(lambda: self.on_field_changed('traits'))
        self.fields['traits'] = traits_input.input
        grid_layout.addRow(traits_input)

        # Classes
        classes_input = editors.LabeledLineEdit("Classes")
        classes_input.input.setPlaceholderText("Comma-separated")
        classes_input.textChanged.connect(lambda: self.on_field_changed('classes'))
        self.fields['classes'] = classes_input.input
        grid_layout.addRow(classes_input)

        # Cost
        cost_input = editors.LabeledLineEdit("Cost")
        cost_input.input.textChanged.connect(lambda: self.on_field_changed('cost'))
        self.fields['cost'] = cost_input.input
        grid_layout.addRow(cost_input)

        # Level
        level_combo = QComboBox()
        level_combo.addItems(['None', '0', '1', '2', '3', '4', '5', 'Custom'])
        level_combo.currentTextChanged.connect(lambda: self.on_field_changed('level'))
        self.fields['level'] = level_combo
        grid_layout.addRow("Level", level_combo)

        grid_widget.setLayout(grid_layout)
        self.main_layout.addWidget(grid_widget)

        # Icons widget (separate from grid)
        self.icons_widget = editors.IconsWidget()
        self.icons_widget.iconsChanged.connect(self.on_icons_changed)
        self.main_layout.addWidget(self.icons_widget)

        # Continue with more grid fields
        grid_widget2 = QWidget()
        grid_layout2 = QFormLayout()

        # Health
        health_input = editors.LabeledLineEdit("Health")
        health_input.input.textChanged.connect(lambda: self.on_field_changed('health'))
        self.fields['health'] = health_input.input
        grid_layout2.addRow(health_input)

        # Sanity
        sanity_input = editors.LabeledLineEdit("Sanity")
        sanity_input.input.textChanged.connect(lambda: self.on_field_changed('sanity'))
        self.fields['sanity'] = sanity_input.input
        grid_layout2.addRow(sanity_input)

        # Slots
        slots_input = editors.LabeledLineEdit("Slots")
        slots_input.input.setPlaceholderText("hand, hands, arcane, etc.")
        slots_input.textChanged.connect(lambda: self.on_field_changed('slots'))
        self.fields['slots'] = slots_input.input
        grid_layout2.addRow(slots_input)

        grid_widget2.setLayout(grid_layout2)
        self.main_layout.addWidget(grid_widget2)

        # Text fields
        self.add_labeled_text("Text", "text", use_arkham=True)
        self.add_labeled_text("Flavor", "flavor_text")

        # Illustration
        self.add_illustration_widget()

        self.main_layout.addStretch()

    def load_data(self):
        """Load data including icons widget"""
        super().load_data()
        # Load icons separately
        icons_value = self.face.get('icons', '')
        self.icons_widget.set_icons_string(icons_value)

    def on_icons_changed(self, icons_str):
        """Handle icons widget change"""
        if self.updating:
            return
        if icons_str:
            self.face.set('icons', icons_str)
        else:
            self.face.set('icons', None)


class EventEditor(FaceEditor):
    """Editor for event cards"""

    def setup_ui(self):
        self.add_labeled_line("Name", "name")
        self.add_labeled_line("Subtitle", "subtitle")

        # Grid for compact fields
        grid_widget = QWidget()
        grid_layout = QFormLayout()

        traits_input = editors.LabeledLineEdit("Traits")
        traits_input.input.textChanged.connect(lambda: self.on_field_changed('traits'))
        self.fields['traits'] = traits_input.input
        grid_layout.addRow(traits_input)

        classes_input = editors.LabeledLineEdit("Classes")
        classes_input.input.textChanged.connect(lambda: self.on_field_changed('classes'))
        self.fields['classes'] = classes_input.input
        grid_layout.addRow(classes_input)

        cost_input = editors.LabeledLineEdit("Cost")
        cost_input.input.textChanged.connect(lambda: self.on_field_changed('cost'))
        self.fields['cost'] = cost_input.input
        grid_layout.addRow(cost_input)

        level_combo = QComboBox()
        level_combo.addItems(['None', '0', '1', '2', '3', '4', '5'])
        level_combo.currentTextChanged.connect(lambda: self.on_field_changed('level'))
        self.fields['level'] = level_combo
        grid_layout.addRow("Level", level_combo)

        grid_widget.setLayout(grid_layout)
        self.main_layout.addWidget(grid_widget)

        # Icons widget (separate from grid)
        self.icons_widget = editors.IconsWidget()
        self.icons_widget.iconsChanged.connect(self.on_icons_changed)
        self.main_layout.addWidget(self.icons_widget)

        self.add_labeled_text("Text", "text", use_arkham=True)
        self.add_labeled_text("Flavor", "flavor_text")
        self.add_illustration_widget()

        self.main_layout.addStretch()

    def load_data(self):
        """Load data including icons widget"""
        super().load_data()
        # Load icons separately
        icons_value = self.face.get('icons', '')
        self.icons_widget.set_icons_string(icons_value)

    def on_icons_changed(self, icons_str):
        """Handle icons widget change"""
        if self.updating:
            return
        if icons_str:
            self.face.set('icons', icons_str)
        else:
            self.face.set('icons', None)


# Skill editor is similar to event
SkillEditor = EventEditor


class EnemyEditor(FaceEditor):
    """Editor for enemy cards"""

    def setup_ui(self):
        self.add_labeled_line("Name", "name")
        self.add_labeled_line("Subtitle", "subtitle")

        grid_widget = QWidget()
        grid_layout = QFormLayout()

        for field, label in [
            ("traits", "Traits"),
            ("classes", "Classes"),
            ("attack", "Attack"),
            ("health", "Health"),
            ("evade", "Evade"),
            ("damage", "Damage"),
            ("horror", "Horror"),
            ("victory", "Victory"),
        ]:
            widget = editors.LabeledLineEdit(label)
            self.fields[field] = widget.input
            # Use a factory function to create proper closure
            def make_callback(field_name):
                return lambda: self.on_field_changed(field_name)
            widget.input.textChanged.connect(make_callback(field))
            grid_layout.addRow(widget)

        grid_widget.setLayout(grid_layout)
        self.main_layout.addWidget(grid_widget)

        self.add_labeled_text("Text", "text", use_arkham=True)
        self.add_labeled_text("Flavor", "flavor_text")
        self.add_illustration_widget()

        self.main_layout.addStretch()


class TreacheryEditor(FaceEditor):
    """Editor for treachery cards"""

    def setup_ui(self):
        self.add_labeled_line("Name", "name")
        self.add_labeled_line("Subtitle", "subtitle")
        self.add_labeled_line("Traits", "traits")
        self.add_labeled_line("Classes", "classes")
        self.add_labeled_line("Victory", "victory")

        self.add_labeled_text("Text", "text", use_arkham=True)
        self.add_labeled_text("Flavor", "flavor_text")
        self.add_illustration_widget()

        self.main_layout.addStretch()


class IconComboBox(QComboBox):
    """ComboBox that displays icons for connection symbols"""

    CONNECTION_SYMBOLS = [
        'None',
        'circle', 'circle_alt',
        'clover',
        'cross', 'cross_alt',
        'diamond', 'diamond_alt',
        'equals', 'equals_alt',
        'heart', 'heart_alt',
        'hourglass', 'hourglass_alt',
        'moon', 'moon_alt',
        'spade',
        'square', 'square_alt',
        'squiggle', 'squiggle_alt',
        'star', 'star_alt',
        't', 't_alt',
        'tear',
        'triangle', 'triangle_alt',
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        # Set fixed narrow width
        self.setFixedWidth(55)
        self.setIconSize(QSize(28, 28))

        # Add all symbols with icons
        from shoggoth.files import overlay_dir
        from PySide6.QtGui import QIcon, QPixmap

        for symbol in self.CONNECTION_SYMBOLS:
            if symbol == 'None':
                # Empty option - show dash
                self.addItem('—', userData=None)
            else:
                icon_path = overlay_dir / f"location_hi_{symbol}.png"
                if icon_path.exists():
                    icon = QIcon(str(icon_path))
                    self.addItem(icon, '', userData=symbol)
                else:
                    # Fallback to text if icon missing
                    self.addItem(symbol[:1].upper(), userData=symbol)

    def setCurrentSymbol(self, symbol):
        """Set current selection by symbol name"""
        if not symbol or symbol == 'None':
            self.setCurrentIndex(0)
        else:
            for i in range(self.count()):
                if self.itemData(i) == symbol:
                    self.setCurrentIndex(i)
                    break

    def currentSymbol(self):
        """Get current symbol name"""
        return self.itemData(self.currentIndex())


class LocationEditor(FaceEditor):
    """Editor for location cards"""

    # Available connection symbols
    CONNECTION_SYMBOLS = [
        'None',
        'circle', 'circle_alt',
        'clover',
        'cross', 'cross_alt',
        'diamond', 'diamond_alt',
        'equals', 'equals_alt',
        'heart', 'heart_alt',
        'hourglass', 'hourglass_alt',
        'moon', 'moon_alt',
        'spade',
        'square', 'square_alt',
        'squiggle', 'squiggle_alt',
        'star', 'star_alt',
        't', 't_alt',
        'tear',
        'triangle', 'triangle_alt',
    ]

    def setup_ui(self):
        # Connection symbol (this location's own symbol)
        conn_layout = QHBoxLayout()
        conn_label = QLabel("Connection Symbol")
        conn_label.setMinimumWidth(110)

        self.connection_combo = IconComboBox()
        self.connection_combo.currentIndexChanged.connect(lambda: self.on_connection_changed())
        self.fields['connection'] = self.connection_combo

        conn_layout.addWidget(conn_label)
        conn_layout.addWidget(self.connection_combo)
        conn_layout.addStretch()  # Push to left
        conn_widget = QWidget()
        conn_widget.setLayout(conn_layout)
        self.main_layout.addWidget(conn_widget)

        # Basic fields
        self.add_labeled_line("Name", "name")
        self.add_labeled_line("Subtitle", "subtitle")

        self.add_labeled_line("Shroud", "shroud")
        self.add_labeled_line("Traits", "traits")
        self.add_labeled_line("Clues", "clues")
        self.add_labeled_line("Victory", "victory")

        # Connections section - single row of icon dropdowns
        connections_row = QHBoxLayout()
        connections_label = QLabel("Connections")
        connections_label.setMinimumWidth(110)
        connections_row.addWidget(connections_label)

        # Store connection combos for easy access
        self.connection_combos = []

        for i in range(6):
            combo = IconComboBox()
            combo.currentIndexChanged.connect(lambda: self.on_connections_changed())
            self.connection_combos.append(combo)
            connections_row.addWidget(combo)

        connections_row.addStretch()  # Push to left
        connections_widget = QWidget()
        connections_widget.setLayout(connections_row)
        self.main_layout.addWidget(connections_widget)

        # Text fields
        self.add_labeled_text("Text", "text", use_arkham=True)
        self.add_labeled_text("Flavor", "flavor_text")
        self.add_illustration_widget()

        self.main_layout.addStretch()

    def on_connection_changed(self):
        """Handle connection symbol change"""
        if self.updating:
            return

        value = self.connection_combo.currentSymbol()
        self.face.set('connection', value)

    def on_connections_changed(self):
        """Handle connections list change"""
        if self.updating:
            return

        # Collect all connection values
        connections = []
        for combo in self.connection_combos:
            value = combo.currentSymbol()
            if value:
                connections.append(value)

        # Store as list or None if empty
        if connections:
            self.face.set('connections', connections)
        else:
            self.face.set('connections', None)

    def load_data(self):
        """Load data from face into fields - override to handle connections specially"""
        self.updating = True

        # Load regular fields
        for field_name, widget in self.fields.items():
            if field_name == 'connection':
                # Handle connection symbol
                value = self.face.get(field_name, '')
                self.connection_combo.setCurrentSymbol(value)
            elif field_name != 'connections':
                # Regular fields
                value = self.face.get(field_name, '')
                self.set_widget_value(widget, value)

        # Load connections list
        connections = self.face.get('connections', [])
        if not connections:
            connections = []
        elif isinstance(connections, str):
            # Handle comma-separated string format
            connections = [c.strip() for c in connections.split(',') if c.strip()]

        # Set combo boxes
        for i, combo in enumerate(self.connection_combos):
            if i < len(connections):
                combo.setCurrentSymbol(connections[i])
            else:
                combo.setCurrentSymbol(None)

        self.updating = False


class JsonEditor(FaceEditor):
    """Raw JSON editor for unknown types or manual editing"""

    def setup_ui(self):
        # Add a header explaining this is raw JSON mode
        header = QLabel("<b>Raw JSON Editor</b>")
        header.setStyleSheet("font-size: 14pt; padding: 5px;")
        self.main_layout.addWidget(header)

        info = QLabel("Edit the card face data directly as JSON. Changes update automatically when valid.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; padding: 5px;")
        self.main_layout.addWidget(info)

        # Create the JSON editor with syntax highlighting
        self.json_editor = editors.ArkhamTextEdit()
        self.json_editor.setPlaceholderText("{\n  \"type\": \"asset\",\n  \"name\": \"Card Name\"\n}")

        # Enable JSON syntax highlighting
        try:
            from pygments.lexers import JsonLexer
            self.json_editor.set_lexer(JsonLexer())
        except:
            pass  # Syntax highlighting optional

        self.json_editor.textChanged.connect(self.on_json_changed)
        self.main_layout.addWidget(self.json_editor)

        # Validation status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("padding: 5px;")
        self.main_layout.addWidget(self.status_label)

        # Format button
        button_row = QHBoxLayout()

        format_btn = QPushButton("Format JSON")
        format_btn.clicked.connect(self.format_json)
        button_row.addWidget(format_btn)

        validate_btn = QPushButton("Validate")
        validate_btn.clicked.connect(self.validate_json)
        button_row.addWidget(validate_btn)

        button_row.addStretch()

        button_widget = QWidget()
        button_widget.setLayout(button_row)
        self.main_layout.addWidget(button_widget)

    def format_json(self):
        """Format the JSON text"""
        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                data = json.loads(text)
                formatted = json.dumps(data, indent=2)
                self.json_editor.setPlainText(formatted)
                self.status_label.setText("✓ JSON formatted")
                self.status_label.setStyleSheet("color: green; padding: 5px;")
        except json.JSONDecodeError as e:
            self.status_label.setText(f"✗ Invalid JSON: {e}")
            self.status_label.setStyleSheet("color: red; padding: 5px;")

    def validate_json(self):
        """Validate the JSON"""
        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                json.loads(text)
                self.status_label.setText("✓ Valid JSON")
                self.status_label.setStyleSheet("color: green; padding: 5px;")
            else:
                self.status_label.setText("⚠ Empty JSON")
                self.status_label.setStyleSheet("color: orange; padding: 5px;")
        except json.JSONDecodeError as e:
            self.status_label.setText(f"✗ Invalid JSON: {e}")
            self.status_label.setStyleSheet("color: red; padding: 5px;")

    def load_data(self):
        """Load face data as JSON"""
        super().load_data()  # load type field
        self.updating = True
        try:
            json_text = json.dumps(self.face.data, indent=2)
            self.json_editor.setPlainText(json_text)
            self.status_label.setText("✓ JSON loaded")
            self.status_label.setStyleSheet("color: green; padding: 5px;")
        except Exception as e:
            self.json_editor.setPlainText(f"# Error loading JSON: {e}")
            self.status_label.setText(f"✗ Load error: {e}")
            self.status_label.setStyleSheet("color: red; padding: 5px;")
        self.updating = False

    def on_json_changed(self):
        """Save JSON back to face"""
        if self.updating:
            return

        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                data = json.loads(text)
                # Update face data
                self.face.data = data
                # Emit type_changed if type changed (to potentially switch editor)
                if 'type' in data and data['type'] != self.face.get('type'):
                    self.type_changed.emit()
                self.status_label.setText("✓ Saved")
                self.status_label.setStyleSheet("color: green; padding: 5px;")
        except json.JSONDecodeError as e:
            self.status_label.setText(f"✗ Invalid JSON: {str(e)[:50]}...")
            self.status_label.setStyleSheet("color: red; padding: 5px;")



class ActEditor(FaceEditor):
    """Editor for act cards (front side)"""

    def setup_ui(self):
        self.add_labeled_line("Name", "name")
        self.add_labeled_line("Index", "index")
        self.add_labeled_line("Clues", "clues")

        self.add_labeled_text("Text", "text", use_arkham=True)
        self.add_labeled_text("Flavor", "flavor_text")
        self.add_illustration_widget()

        self.main_layout.addStretch()


class ActBackEditor(FaceEditor):
    """Editor for act cards (back side)"""

    def setup_ui(self):
        self.add_labeled_line("Name", "name")
        self.add_labeled_line("Index", "index")

        self.add_labeled_text("Text", "text", use_arkham=True)
        self.add_labeled_text("Flavor", "flavor_text")

        self.main_layout.addStretch()


class AgendaEditor(FaceEditor):
    """Editor for agenda cards (front side)"""

    def setup_ui(self):
        self.add_labeled_line("Name", "name")
        self.add_labeled_line("Index", "index")
        self.add_labeled_line("Doom", "doom")

        self.add_labeled_text("Text", "text", use_arkham=True)
        self.add_labeled_text("Flavor", "flavor_text")
        self.add_illustration_widget()

        self.main_layout.addStretch()


class AgendaBackEditor(FaceEditor):
    """Editor for agenda cards (back side)"""

    def setup_ui(self):
        self.add_labeled_line("Name", "name")
        self.add_labeled_line("Index", "index")

        self.add_labeled_text("Text", "text", use_arkham=True)
        self.add_labeled_text("Flavor", "flavor_text")

        self.main_layout.addStretch()


class InvestigatorEditor(FaceEditor):
    """Editor for investigator cards (front side)"""

    def setup_ui(self):
        self.add_labeled_line("Name", "name")
        self.add_labeled_line("Subtitle", "subtitle")

        # Classes
        classes_input = editors.LabeledLineEdit("Classes")
        classes_input.input.textChanged.connect(lambda: self.on_field_changed('classes'))
        self.fields['classes'] = classes_input.input
        self.main_layout.addWidget(classes_input)

        # Stats in a grid
        box_widget = QWidget()
        box_layout = QHBoxLayout()

        for field, label in [
            ("willpower", "Willpower"),
            ("intellect", "Intellect"),
            ("combat", "Combat"),
            ("agility", "Agility"),
        ]:
            widget = editors.LabeledLineEdit(label)
            self.fields[field] = widget.input

            def make_callback(field_name):
                return lambda: self.on_field_changed(field_name)
            widget.input.textChanged.connect(make_callback(field))
            box_layout.addWidget(widget)

        box_widget.setLayout(box_layout)
        self.main_layout.addWidget(box_widget)

        # Stats in a grid
        box_widget = QWidget()
        box_layout = QHBoxLayout()
        for field, label in [
            ("health", "Health"),
            ("sanity", "Sanity"),
        ]:
            widget = editors.LabeledLineEdit(label)
            self.fields[field] = widget.input

            def make_callback(field_name):
                return lambda: self.on_field_changed(field_name)
            widget.input.textChanged.connect(make_callback(field))
            box_layout.addWidget(widget)

        box_widget.setLayout(box_layout)
        self.main_layout.addWidget(box_widget)

        # Text fields
        self.add_labeled_text("Text", "text", use_arkham=True)
        self.add_labeled_text("Flavor", "flavor_text")

        # Illustration
        self.add_illustration_widget()

        self.main_layout.addStretch()


class InvestigatorBackEditor(FaceEditor):
    """Editor for investigator cards (back side) with deck building entries"""

    NUM_ENTRIES = 8

    def setup_ui(self):
        self.add_labeled_line("Name", "name")
        self.add_labeled_line("Subtitle", "subtitle")

        # Classes
        classes_input = editors.LabeledLineEdit("Classes")
        classes_input.input.setPlaceholderText("Comma-separated")
        classes_input.input.textChanged.connect(lambda: self.on_field_changed('classes'))
        self.fields['classes'] = classes_input.input
        self.main_layout.addWidget(classes_input)

        # Deck building entries section
        entries_group = QGroupBox("Deck Building Options")
        entries_layout = QVBoxLayout()
        entries_layout.setSpacing(15)
        entries_layout.setContentsMargins(6, 6, 6, 6)

        self.entry_widgets = []  # Store (header_input, text_input) pairs

        for i in range(self.NUM_ENTRIES):
            entry_widget = QWidget()
            entry_layout = QVBoxLayout()
            entry_layout.setContentsMargins(0, 0, 0, 0)

            # Header input (narrow)
            header_input = QLineEdit()
            header_input.setPlaceholderText(f"Header {i+1}")
            header_input.textChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(header_input)

            # Value input (multi-line text field)
            value_input = QPlainTextEdit()
            value_input.setPlaceholderText(f"Value {i+1}")
            value_input.setFixedHeight(54)  # ~3 lines
            value_input.textChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(value_input)

            entry_widget.setLayout(entry_layout)
            entries_layout.addWidget(entry_widget)

            self.entry_widgets.append((header_input, value_input))

        entries_group.setLayout(entries_layout)
        self.main_layout.addWidget(entries_group)

        # Flavor text
        self.add_labeled_text("Flavor", "flavor_text")

        # Illustration
        self.add_illustration_widget()

        self.main_layout.addStretch()

    def load_data(self):
        """Load data from face into fields, including special entries handling"""
        self.updating = True

        # Load regular fields
        for field_name, widget in self.fields.items():
            value = self.face.get(field_name, '')
            self.set_widget_value(widget, value)

        # Load entries
        entries = self.face.get('entries', [])
        if not entries:
            entries = []

        for i, (header_input, value_input) in enumerate(self.entry_widgets):
            if i < len(entries) and isinstance(entries[i], list) and len(entries[i]) >= 2:
                header_input.setText(str(entries[i][0]) if entries[i][0] else '')
                # QPlainTextEdit uses setPlainText instead of setText
                value_input.setPlainText(str(entries[i][1]) if entries[i][1] else '')
            else:
                header_input.setText('')
                value_input.setPlainText('')

        self.updating = False

    def on_entries_changed(self):
        """Handle changes to entry fields"""
        if self.updating:
            return

        # Collect all entries
        entries = []
        text_parts = []

        for header_input, value_input in self.entry_widgets:
            header = header_input.text().strip()
            # QPlainTextEdit uses toPlainText() instead of text()
            value = value_input.toPlainText().strip()

            if header or value:
                entries.append([header, value])
                # Only add to text if BOTH header and value have content
                if header and value:
                    text_parts.append(f"<b>{header}</b> {value}")

        # Save entries list
        if entries:
            self.face.set('entries', entries)
        else:
            self.face.set('entries', None)

        # Save combined text field
        if text_parts:
            combined_text = "\n".join(text_parts)
            self.face.set('text', combined_text)
        else:
            self.face.set('text', None)

        # Emit data_changed signal
        parent = self.parent()
        while parent:
            if hasattr(parent, 'data_changed'):
                parent.data_changed.emit()
                break
            parent = parent.parent()


# Create aliases for similar editors
LocationBackEditor = LocationEditor


class ChaosEditor(FaceEditor):
    """Editor for chaos bag reference cards"""

    NUM_ENTRIES = 10

    def setup_ui(self):
        self.add_labeled_line("Difficulty", "difficulty")

        # Entries section
        entries_group = QGroupBox("Chaos Bag Entries")
        entries_layout = QVBoxLayout()
        entries_layout.setSpacing(8)
        entries_layout.setContentsMargins(6, 6, 6, 6)

        self.entry_widgets = []  # Store (token_input, text_input) pairs

        for i in range(self.NUM_ENTRIES):
            entry_widget = QWidget()
            entry_layout = QHBoxLayout()
            entry_layout.setContentsMargins(0, 0, 0, 0)

            # Token input (comma-separated list of tokens)
            token_input = QLineEdit()
            token_input.setPlaceholderText(f"Tokens (e.g. -1, -2)")
            token_input.setMaximumWidth(150)
            token_input.textChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(token_input)

            # Text input
            text_input = QLineEdit()
            text_input.setPlaceholderText(f"Effect text")
            text_input.textChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(text_input)

            entry_widget.setLayout(entry_layout)
            entries_layout.addWidget(entry_widget)

            self.entry_widgets.append((token_input, text_input))

        entries_group.setLayout(entries_layout)
        self.main_layout.addWidget(entries_group)

        self.main_layout.addStretch()

    def load_data(self):
        """Load data from face into fields"""
        self.updating = True

        # Load regular fields
        for field_name, widget in self.fields.items():
            value = self.face.get(field_name, '')
            self.set_widget_value(widget, value)

        # Load entries
        entries = self.face.get('entries', [])
        if not entries:
            entries = []

        for i, (token_input, text_input) in enumerate(self.entry_widgets):
            if i < len(entries) and isinstance(entries[i], dict):
                # Token is a list, join with comma
                tokens = entries[i].get('token', [])
                if isinstance(tokens, list):
                    token_input.setText(', '.join(str(t) for t in tokens))
                else:
                    token_input.setText(str(tokens) if tokens else '')
                text_input.setText(str(entries[i].get('text', '')))
            else:
                token_input.setText('')
                text_input.setText('')

        self.updating = False

    def on_entries_changed(self):
        """Handle changes to entry fields"""
        if self.updating:
            return

        entries = []
        for token_input, text_input in self.entry_widgets:
            token_str = token_input.text().strip()
            text = text_input.text().strip()

            if token_str or text:
                # Parse tokens as comma-separated list
                tokens = [t.strip() for t in token_str.split(',') if t.strip()]
                entries.append({'token': tokens, 'text': text})

        if entries:
            self.face.set('entries', entries)
        else:
            self.face.set('entries', None)

        # Emit data_changed signal
        parent = self.parent()
        while parent:
            if hasattr(parent, 'data_changed'):
                parent.data_changed.emit()
                break
            parent = parent.parent()


class CustomizableEditor(FaceEditor):
    """Editor for customizable cards with upgrade options"""

    NUM_ENTRIES = 12

    def setup_ui(self):
        self.add_labeled_line("Name", "name")
        self.add_labeled_text("Text", "text", use_arkham=True)

        # Entries section (customization options)
        entries_group = QGroupBox("Customization Options")
        entries_layout = QVBoxLayout()
        entries_layout.setSpacing(6)
        entries_layout.setContentsMargins(6, 6, 6, 6)

        self.entry_widgets = []  # Store (cost_input, name_input, text_input) tuples

        for i in range(self.NUM_ENTRIES):
            entry_widget = QWidget()
            entry_layout = QHBoxLayout()
            entry_layout.setContentsMargins(0, 0, 0, 0)
            entry_layout.setSpacing(4)

            # Cost input (small integer field)
            cost_input = QSpinBox()
            cost_input.setRange(0, 10)
            cost_input.setFixedWidth(50)
            cost_input.setToolTip("XP Cost")
            cost_input.valueChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(cost_input)

            # Name input
            name_input = QLineEdit()
            name_input.setPlaceholderText(f"Option name")
            name_input.setMaximumWidth(150)
            name_input.textChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(name_input)

            # Text input
            text_input = QLineEdit()
            text_input.setPlaceholderText(f"Option effect")
            text_input.textChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(text_input)

            entry_widget.setLayout(entry_layout)
            entries_layout.addWidget(entry_widget)

            self.entry_widgets.append((cost_input, name_input, text_input))

        entries_group.setLayout(entries_layout)
        self.main_layout.addWidget(entries_group)
        self.main_layout.addStretch()

    def load_data(self):
        """Load data from face into fields"""
        self.updating = True

        # Load regular fields
        for field_name, widget in self.fields.items():
            value = self.face.get(field_name, '')
            self.set_widget_value(widget, value)

        # Load entries
        entries = self.face.get('entries', [])
        if not entries:
            entries = []

        for i, (cost_input, name_input, text_input) in enumerate(self.entry_widgets):
            if i < len(entries) and isinstance(entries[i], list) and len(entries[i]) >= 3:
                cost_input.setValue(int(entries[i][0]) if entries[i][0] else 0)
                name_input.setText(str(entries[i][1]) if entries[i][1] else '')
                text_input.setText(str(entries[i][2]) if entries[i][2] else '')
            else:
                cost_input.setValue(0)
                name_input.setText('')
                text_input.setText('')

        self.updating = False

    def on_entries_changed(self):
        """Handle changes to entry fields"""
        if self.updating:
            return

        entries = []
        for cost_input, name_input, text_input in self.entry_widgets:
            cost = cost_input.value()
            name = name_input.text().strip()
            text = text_input.text().strip()

            if name or text or cost > 0:
                entries.append([cost, name, text])

        if entries:
            self.face.set('entries', entries)
        else:
            self.face.set('entries', None)

        # Emit data_changed signal
        parent = self.parent()
        while parent:
            if hasattr(parent, 'data_changed'):
                parent.data_changed.emit()
                break
            parent = parent.parent()


class StoryEditor(FaceEditor):
    """Editor for story cards"""

    def setup_ui(self):
        self.add_labeled_line("Name", "name")
        self.add_labeled_line("Classes", "classes")

        self.add_labeled_text("Text", "text", use_arkham=True)
        self.main_layout.addStretch()


# Mapping of editor types to classes
EDITOR_MAPPING = {
    'player': BaseEditor,
    'customizable_back': BaseEditor,
    'encounter': BaseEditor,
    'asset': AssetEditor,
    'event': EventEditor,
    'skill': SkillEditor,
    'investigator': InvestigatorEditor,
    'investigator_back': InvestigatorBackEditor,
    'location': LocationEditor,
    'location_back': LocationBackEditor,
    'treachery': TreacheryEditor,
    'enemy': EnemyEditor,
    'act': ActEditor,
    'act_back': ActBackEditor,
    'agenda': AgendaEditor,
    'agenda_back': AgendaBackEditor,
    'chaos': ChaosEditor,
    'customizable': CustomizableEditor,
    'story': StoryEditor,
}


def get_editor_for_face(face, parent=None):
    """Get the appropriate editor for a face"""
    editor_type = face.get_editor()
    editor_class = EDITOR_MAPPING.get(editor_type, JsonEditor)
    return editor_class(face, parent)