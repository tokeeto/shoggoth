"""
Editor widgets for Shoggoth using PySide6
"""
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QPushButton, QLabel, QComboBox,
    QScrollArea, QGroupBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal

from shoggoth.text_editor import ArkhamTextEdit
from shoggoth.floating_label_widget import FloatingLabelTextEdit, FloatingLabelLineEdit
from shoggoth import face_editors


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
            self.floating_widget.input.setMinimumHeight(100)
            self.floating_widget.input.setMaximumHeight(140)

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


class IllustrationWidget(QWidget):
    """Widget for illustration settings"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        # Image path
        path_layout = QHBoxLayout()
        self.path_input = LabeledLineEdit("Image Path")
        path_layout.addWidget(self.path_input)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_image)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # Pan and scale
        pan_scale_layout = QHBoxLayout()
        self.pan_y_input = LabeledLineEdit("Pan Y")
        self.pan_x_input = LabeledLineEdit("Pan X")
        self.scale_input = LabeledLineEdit("Scale")
        pan_scale_layout.addWidget(self.pan_y_input)
        pan_scale_layout.addWidget(self.pan_x_input)
        pan_scale_layout.addWidget(self.scale_input)
        layout.addLayout(pan_scale_layout)

        # Artist
        self.artist_input = LabeledLineEdit("Artist")
        layout.addWidget(self.artist_input)

        self.setLayout(layout)

    def browse_image(self):
        """Browse for image file"""
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if file_path:
            self.path_input.setText(file_path)


class CardEditor(QWidget):
    """Main card editor widget"""

    # Signal emitted when card data changes
    data_changed = Signal()

    def __init__(self, card):
        super().__init__()
        self.card = card

        # Main layout with scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout()

        # Basic info section
        basic_group = QGroupBox("Basic Information")
        basic_layout = QVBoxLayout()

        self.name_input = LabeledLineEdit("Name")
        basic_layout.addWidget(self.name_input)

        self.copyright_input = LabeledLineEdit("Copyright")
        basic_layout.addWidget(self.copyright_input)

        # Numbers
        numbers_layout = QHBoxLayout()
        self.amount_input = LabeledLineEdit("Amount in set")
        self.collection_input = LabeledLineEdit("Collection #")
        self.encounter_input = LabeledLineEdit("Encounter Set #")
        numbers_layout.addWidget(self.amount_input)
        numbers_layout.addWidget(self.collection_input)
        numbers_layout.addWidget(self.encounter_input)
        basic_layout.addLayout(numbers_layout)

        self.investigator_input = LabeledLineEdit("Investigator Link")
        basic_layout.addWidget(self.investigator_input)

        self.id_input = LabeledLineEdit("ID")
        self.id_input.input.setReadOnly(True)
        basic_layout.addWidget(self.id_input)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # Add JSON view toggle at card level
        json_button_row = QHBoxLayout()
        self.json_view_btn = QPushButton("📝 View Card as JSON")
        self.json_view_btn.setMaximumWidth(200)
        self.json_view_btn.clicked.connect(self.toggle_json_view)
        json_button_row.addWidget(self.json_view_btn)
        json_button_row.addStretch()
        json_widget = QWidget()
        json_widget.setLayout(json_button_row)
        layout.addWidget(json_widget)

        # Container for face editors or JSON editor
        self.editor_container = QWidget()
        self.editor_layout = QVBoxLayout()
        self.editor_container.setLayout(self.editor_layout)
        layout.addWidget(self.editor_container)

        # Track whether showing JSON
        self.showing_json = False

        # Create initial editors (form view)
        self.create_form_editors()

        content.setLayout(layout)
        scroll.setWidget(content)

        # Main widget layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

        # Setup card field bindings
        self.fields = []
        self.setup_card_fields()
        self.load_card()

    def create_form_editors(self):
        """Create the form-based face editors"""
        # Clear container
        while self.editor_layout.count():
            item = self.editor_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Front face editor
        front_group = QGroupBox("Front")
        self.front_layout = QVBoxLayout()
        self.front_editor = None
        self.create_front_editor()
        front_group.setLayout(self.front_layout)
        self.editor_layout.addWidget(front_group)

        # Back face editor
        back_group = QGroupBox("Back")
        self.back_layout = QVBoxLayout()
        self.back_editor = None
        self.create_back_editor()
        back_group.setLayout(self.back_layout)
        self.editor_layout.addWidget(back_group)

    def create_json_editor(self):
        """Create the JSON editor for entire card"""
        # Clear container
        while self.editor_layout.count():
            item = self.editor_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Create JSON editor group
        json_group = QGroupBox("Card JSON")
        json_layout = QVBoxLayout()

        # Info
        info = QLabel("Edit the entire card data as JSON. Changes save automatically when valid.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; padding: 5px;")
        json_layout.addWidget(info)

        # JSON editor
        from editors import ArkhamTextEdit
        self.json_editor = ArkhamTextEdit()

        # Enable JSON syntax highlighting
        try:
            from pygments.lexers import JsonLexer
            self.json_editor.set_lexer(JsonLexer())
        except:
            pass

        self.json_editor.textChanged.connect(self.on_json_changed)
        json_layout.addWidget(self.json_editor)

        # Status
        self.json_status = QLabel("")
        json_layout.addWidget(self.json_status)

        # Buttons
        button_row = QHBoxLayout()
        format_btn = QPushButton("Format JSON")
        format_btn.clicked.connect(self.format_json)
        button_row.addWidget(format_btn)

        validate_btn = QPushButton("Validate")
        validate_btn.clicked.connect(self.validate_json)
        button_row.addWidget(validate_btn)

        button_row.addStretch()
        json_layout.addLayout(button_row)

        json_group.setLayout(json_layout)
        self.editor_layout.addWidget(json_group)

        # Load current card data
        self.load_json_data()

    def toggle_json_view(self):
        """Toggle between form editors and JSON editor"""
        self.showing_json = not self.showing_json

        if self.showing_json:
            self.json_view_btn.setText("📋 View as Form")
            self.create_json_editor()
        else:
            self.json_view_btn.setText("📝 View Card as JSON")
            self.create_form_editors()

    def load_json_data(self):
        """Load card data into JSON editor"""
        try:
            # Get entire card data
            card_data = {
                'name': self.card.name,
                'id': self.card.id,
                'amount': self.card.amount,
                'expansion_number': self.card.expansion_number,
                'encounter_number': self.card.encounter_number,
                'investigator': self.card.get('investigator'),
                'front': self.card.front.data,
                'back': self.card.back.data,
            }
            # Remove None values
            card_data = {k: v for k, v in card_data.items() if v is not None}

            json_text = json.dumps(card_data, indent=2)
            self.json_editor.setPlainText(json_text)
            self.json_status.setText("✓ JSON loaded")
            self.json_status.setStyleSheet("color: green; padding: 5px;")
        except Exception as e:
            self.json_status.setText(f"✗ Load error: {e}")
            self.json_status.setStyleSheet("color: red; padding: 5px;")

    def on_json_changed(self):
        """Handle JSON editor changes"""
        if not hasattr(self, 'json_editor'):
            return

        try:
            text = self.json_editor.toPlainText()
            if not text.strip():
                return

            data = json.loads(text)

            # Update card data
            if 'name' in data:
                self.card.set('name', data['name'])
            if 'amount' in data:
                self.card.set('amount', data['amount'])
            if 'expansion_number' in data:
                self.card.expansion_number = data['expansion_number']
            if 'encounter_number' in data:
                self.card.encounter_number = data['encounter_number']
            if 'investigator' in data:
                self.card.set('investigator', data['investigator'])

            # Update face data
            if 'front' in data:
                self.card.front.data = data['front']
            if 'back' in data:
                self.card.back.data = data['back']

            # Emit signal for preview update
            self.data_changed.emit()

            self.json_status.setText("✓ Saved")
            self.json_status.setStyleSheet("color: green; padding: 5px;")

        except json.JSONDecodeError as e:
            self.json_status.setText(f"✗ Invalid JSON: {str(e)[:50]}...")
            self.json_status.setStyleSheet("color: red; padding: 5px;")

    def format_json(self):
        """Format the JSON"""
        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                data = json.loads(text)
                formatted = json.dumps(data, indent=2)
                self.json_editor.setPlainText(formatted)
                self.json_status.setText("✓ Formatted")
                self.json_status.setStyleSheet("color: green; padding: 5px;")
        except json.JSONDecodeError as e:
            self.json_status.setText(f"✗ Invalid JSON: {e}")
            self.json_status.setStyleSheet("color: red; padding: 5px;")

    def validate_json(self):
        """Validate the JSON"""
        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                json.loads(text)
                self.json_status.setText("✓ Valid JSON")
                self.json_status.setStyleSheet("color: green; padding: 5px;")
            else:
                self.json_status.setText("⚠ Empty")
                self.json_status.setStyleSheet("color: orange; padding: 5px;")
        except json.JSONDecodeError as e:
            self.json_status.setText(f"✗ Invalid: {e}")
            self.json_status.setStyleSheet("color: red; padding: 5px;")

    def create_front_editor(self):
        """Create/recreate front face editor"""
        # Remove old editor if exists
        if self.front_editor:
            self.front_layout.removeWidget(self.front_editor)
            self.front_editor.setParent(None)
            self.front_editor.deleteLater()

        # Create new editor
        self.front_editor = face_editors.get_editor_for_face(self.card.front)
        self.front_editor.type_changed.connect(lambda: self.on_type_changed('front'))
        self.front_layout.addWidget(self.front_editor)

    def create_back_editor(self):
        """Create/recreate back face editor"""
        # Remove old editor if exists
        if self.back_editor:
            self.back_layout.removeWidget(self.back_editor)
            self.back_editor.setParent(None)
            self.back_editor.deleteLater()

        # Create new editor
        self.back_editor = face_editors.get_editor_for_face(self.card.back)
        self.back_editor.type_changed.connect(lambda: self.on_type_changed('back'))
        self.back_layout.addWidget(self.back_editor)

        self.back_editor.type_changed.connect(lambda f: self.on_type_changed('back'))
        self.back_layout.addWidget(self.back_editor)

    def on_type_changed(self, which_face):
        """Handle face type change - recreate the appropriate editor"""
        if which_face == 'front':
            self.create_front_editor()
        else:
            self.create_back_editor()

    def setup_card_fields(self):
        """Setup bindings for card-level fields"""
        self.fields = [
            FieldWidget(self.name_input.input, 'name'),
            FieldWidget(self.copyright_input.input, 'copyright'),
            FieldWidget(self.amount_input.input, 'amount', int),
            FieldWidget(self.collection_input.input, 'expansion_number'),
            FieldWidget(self.encounter_input.input, 'encounter_number'),
            FieldWidget(self.investigator_input.input, 'investigator'),
            FieldWidget(self.id_input.input, 'id'),
        ]

        # Connect signals
        for field in self.fields:
            widget = field.widget
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(lambda v, f=field: self.on_field_changed(f, v))

    def load_card(self):
        """Load card data into fields"""
        for field in self.fields:
            field.update_from_card(self.card)

    def on_field_changed(self, field, value):
        """Handle field value changes"""
        field.update_card(self.card, value)

    def cleanup(self):
        """Cleanup editor resources"""
        if self.front_editor and hasattr(self.front_editor, 'cleanup'):
            self.front_editor.cleanup()
        if self.back_editor and hasattr(self.back_editor, 'cleanup'):
            self.back_editor.cleanup()