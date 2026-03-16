"""
Card editor widget for Shoggoth using PySide6
"""
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QPushButton, QLabel, QComboBox,
    QScrollArea, QGroupBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve

from shoggoth.ui.field_widgets import LabeledLineEdit, FieldWidget
from shoggoth.ui.text_editor import ArkhamTextEdit
from shoggoth.ui.face_editor_factory import get_editor_for_face
from shoggoth.i18n import tr


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

        # Basic info section (collapsible)
        basic_group = QWidget()
        basic_layout = QVBoxLayout()
        basic_layout.setContentsMargins(0, 0, 0, 0)
        basic_layout.setSpacing(4)

        # Header row with Name field and toggle button on the right
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)

        self.name_input = LabeledLineEdit(tr("FIELD_NAME"))
        header_row.addWidget(self.name_input)

        self.basic_toggle_btn = QPushButton("\u25b6")  # Right arrow
        self.basic_toggle_btn.setFixedWidth(28)
        self.basic_toggle_btn.setCheckable(True)
        self.basic_toggle_btn.setChecked(False)
        self.basic_toggle_btn.setToolTip(tr("TOOLTIP_TOGGLE_BASIC_INFO"))
        self.basic_toggle_btn.clicked.connect(self.toggle_basic_info)
        header_row.addWidget(self.basic_toggle_btn)

        basic_layout.addLayout(header_row)

        # Collapsible content (hidden by default)
        self.basic_info_content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.copyright_input = LabeledLineEdit(tr("FIELD_COPYRIGHT"))
        content_layout.addWidget(self.copyright_input)

        # Numbers
        numbers_layout = QHBoxLayout()
        self.amount_input = LabeledLineEdit(tr("FIELD_AMOUNT_IN_SET"))
        self.collection_input = LabeledLineEdit(tr("FIELD_COLLECTION_NUM"))
        self.encounter_input = LabeledLineEdit(tr("FIELD_ENCOUNTER_SET_NUM"))
        numbers_layout.addWidget(self.amount_input)
        numbers_layout.addWidget(self.collection_input)
        numbers_layout.addWidget(self.encounter_input)
        content_layout.addLayout(numbers_layout)

        self.investigator_input = LabeledLineEdit(tr("FIELD_INVESTIGATOR_LINK"))
        content_layout.addWidget(self.investigator_input)

        self.id_input = LabeledLineEdit(tr("ID"))
        self.id_input.input.setReadOnly(True)
        content_layout.addWidget(self.id_input)

        self.basic_info_content.setLayout(content_layout)
        self.basic_info_content.setMaximumHeight(0)
        basic_layout.addWidget(self.basic_info_content)

        # Animation for collapsible content
        self.basic_info_animation = QPropertyAnimation(self.basic_info_content, b"maximumHeight")
        self.basic_info_animation.setDuration(150)
        self.basic_info_animation.setEasingCurve(QEasingCurve.OutCubic)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # Add JSON view toggle at card level
        json_button_row = QHBoxLayout()
        self.json_view_btn = QPushButton(tr("BTN_VIEW_JSON"))
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
        front_group = QGroupBox(tr("TAB_FRONT"))
        self.front_layout = QVBoxLayout()
        self.front_editor = None
        self.create_front_editor()
        front_group.setLayout(self.front_layout)
        self.editor_layout.addWidget(front_group)

        # Back face editor
        back_group = QGroupBox(tr("TAB_BACK"))
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
        json_group = QGroupBox(tr("CARD_DATA_JSON"))
        json_layout = QVBoxLayout()

        # Info
        info = QLabel(tr("HELP_EDIT_CARD_JSON"))
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; padding: 5px;")
        json_layout.addWidget(info)

        # JSON editor
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
        format_btn = QPushButton(tr("BTN_FORMAT_JSON"))
        format_btn.clicked.connect(self.format_json)
        button_row.addWidget(format_btn)

        validate_btn = QPushButton(tr("BTN_VALIDATE"))
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
            self.json_view_btn.setText(tr("BTN_VIEW_FORM"))
            self.create_json_editor()
        else:
            self.json_view_btn.setText(tr("BTN_VIEW_JSON"))
            self.create_form_editors()

    def toggle_basic_info(self, checked):
        """Toggle visibility of basic info fields with animation"""
        # Update arrow icon
        self.basic_toggle_btn.setText("\u25bc" if checked else "\u25b6")  # Down / Right arrow

        # Animate the content height
        self.basic_info_animation.stop()
        if checked:
            # Expanding: animate from 0 to full height
            target_height = self.basic_info_content.sizeHint().height()
            self.basic_info_animation.setStartValue(0)
            self.basic_info_animation.setEndValue(target_height)
        else:
            # Collapsing: animate from current height to 0
            self.basic_info_animation.setStartValue(self.basic_info_content.height())
            self.basic_info_animation.setEndValue(0)
        self.basic_info_animation.start()

    def load_json_data(self):
        """Load card data into JSON editor"""
        try:
            # Get entire card data
            card_data = {
                'name': self.card.name,
                'id': self.card.id,
                'amount': self.card.amount,
                'project_number': self.card.project_number,
                'encounter_number': self.card.encounter_number,
                'investigator': self.card.get('investigator'),
                'front': self.card.front.data,
                'back': self.card.back.data,
            }
            # Remove None values
            card_data = {k: v for k, v in card_data.items() if v is not None}

            json_text = json.dumps(card_data, indent=2)
            self.json_editor.setPlainText(json_text)
            self.json_status.setText(tr("STATUS_JSON_LOADED"))
            self.json_status.setStyleSheet("color: green; padding: 5px;")
        except Exception as e:
            self.json_status.setText(tr("STATUS_LOAD_ERROR").format(error=e))
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
            if 'project_number' in data:
                self.card.project_number = data['project_number']
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

            self.json_status.setText(tr("STATUS_JSON_SAVED"))
            self.json_status.setStyleSheet("color: green; padding: 5px;")

        except json.JSONDecodeError as e:
            self.json_status.setText(tr("STATUS_JSON_INVALID").format(error=str(e)[:50]))
            self.json_status.setStyleSheet("color: red; padding: 5px;")

    def format_json(self):
        """Format the JSON"""
        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                data = json.loads(text)
                formatted = json.dumps(data, indent=2)
                self.json_editor.setPlainText(formatted)
                self.json_status.setText(tr("STATUS_JSON_FORMATTED"))
                self.json_status.setStyleSheet("color: green; padding: 5px;")
        except json.JSONDecodeError as e:
            self.json_status.setText(tr("STATUS_JSON_INVALID").format(error=e))
            self.json_status.setStyleSheet("color: red; padding: 5px;")

    def validate_json(self):
        """Validate the JSON"""
        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                json.loads(text)
                self.json_status.setText(tr("STATUS_JSON_VALID"))
                self.json_status.setStyleSheet("color: green; padding: 5px;")
            else:
                self.json_status.setText(tr("STATUS_JSON_EMPTY"))
                self.json_status.setStyleSheet("color: orange; padding: 5px;")
        except json.JSONDecodeError as e:
            self.json_status.setText(tr("STATUS_JSON_INVALID").format(error=e))
            self.json_status.setStyleSheet("color: red; padding: 5px;")

    def create_front_editor(self):
        """Create/recreate front face editor"""
        # Remove old editor if exists
        if self.front_editor:
            self.front_layout.removeWidget(self.front_editor)
            self.front_editor.setParent(None)
            self.front_editor.deleteLater()

        # Create new editor
        self.front_editor = get_editor_for_face(self.card.front)
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
        self.back_editor = get_editor_for_face(self.card.back)
        self.back_editor.type_changed.connect(lambda: self.on_type_changed('back'))
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
            FieldWidget(self.collection_input.input, 'project_number'),
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
        if field.update_card(self.card, value):
            self.data_changed.emit()

    def enter_translation_mode(self):
        """Switch both face editors into translation mode."""
        if self.front_editor:
            self.front_editor.enter_translation_mode()
        if self.back_editor:
            self.back_editor.enter_translation_mode()

    def exit_translation_mode(self):
        """Restore both face editors to normal editing mode."""
        if self.front_editor:
            self.front_editor.exit_translation_mode()
        if self.back_editor:
            self.back_editor.exit_translation_mode()

    def cleanup(self):
        """Cleanup editor resources"""
        if self.front_editor and hasattr(self.front_editor, 'cleanup'):
            self.front_editor.cleanup()
        if self.back_editor and hasattr(self.back_editor, 'cleanup'):
            self.back_editor.cleanup()
