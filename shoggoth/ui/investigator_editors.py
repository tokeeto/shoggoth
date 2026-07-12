"""
Investigator card editors for Shoggoth
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLineEdit, QPlainTextEdit, QLabel
)

from shoggoth.ui.face_editor import FaceEditor
from shoggoth.ui.field_widgets import LabeledLineEdit, ClassSelectorWidget
from shoggoth.ui.editor_widgets import NoScrollComboBox
from shoggoth.i18n import tr


class InvestigatorEditor(FaceEditor):
    """Editor for investigator cards (front side)"""

    def setup_ui(self):
        self.add_labeled_line(tr("FIELD_NAME"), "name")
        self.add_labeled_line(tr("FIELD_SUBTITLE"), "subtitle")
        self.add_trait_field()

        # Classes
        classes_widget = ClassSelectorWidget()
        classes_widget.classesChanged.connect(lambda: self.on_field_changed('classes'))
        self.fields['classes'] = classes_widget
        self.field_containers['classes'] = classes_widget
        self.main_layout.addWidget(classes_widget)

        # Stats in a grid
        box_widget = QWidget()
        box_layout = QHBoxLayout()

        for field, label in [
            ("willpower", tr("FIELD_WILLPOWER")),
            ("intellect", tr("FIELD_INTELLECT")),
            ("combat", tr("FIELD_COMBAT")),
            ("agility", tr("FIELD_AGILITY")),
        ]:
            widget = LabeledLineEdit(label)
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
            ("health", tr("FIELD_HEALTH")),
            ("sanity", tr("FIELD_SANITY")),
        ]:
            widget = LabeledLineEdit(label)
            self.fields[field] = widget.input

            def make_callback(field_name):
                return lambda: self.on_field_changed(field_name)
            widget.input.textChanged.connect(make_callback(field))
            box_layout.addWidget(widget)

        box_widget.setLayout(box_layout)
        self.main_layout.addWidget(box_widget)

        # Text fields
        self.add_labeled_text(tr("FIELD_TEXT"), "text", use_arkham=True)
        self.add_labeled_text(tr("FIELD_FLAVOR"), "flavor_text")

        # Illustration
        self.add_illustration_widget()

        # Mask template dropdown
        mask_row = QWidget()
        mask_layout = QHBoxLayout()
        mask_layout.setContentsMargins(0, 0, 0, 0)
        mask_label = QLabel(tr("FIELD_APPLY_MASK"))
        mask_label.setMinimumWidth(80)
        self._mask_combo = NoScrollComboBox()
        self._mask_combo.addItem(tr("OPTION_DEFAULT"), userData=None)
        self._mask_combo.addItem(tr("OPTION_TRUE"), userData=True)
        self._mask_combo.addItem(tr("OPTION_FALSE"), userData=False)
        self._mask_combo.currentIndexChanged.connect(self._on_mask_changed)
        mask_layout.addWidget(mask_label)
        mask_layout.addWidget(self._mask_combo)
        mask_layout.addStretch()
        mask_row.setLayout(mask_layout)
        self.main_layout.addWidget(mask_row)

        # Copyright and extra text fields
        self.add_footer_row()

        self.main_layout.addStretch()

    def _on_mask_changed(self):
        if self.updating:
            return
        value = self._mask_combo.currentData()
        self.face.set('mask_template', value)
        parent = self.parent()
        while parent:
            if hasattr(parent, 'data_changed'):
                parent.data_changed.emit()
                break
            parent = parent.parent()

    def load_data(self):
        super().load_data()
        self.updating = True
        value = self.face.get('mask_template')
        if value is True:
            self._mask_combo.setCurrentIndex(1)
        elif value is False:
            self._mask_combo.setCurrentIndex(2)
        else:
            self._mask_combo.setCurrentIndex(0)
        self.updating = False


class InvestigatorBackEditor(FaceEditor):
    """Editor for investigator cards (back side) with deck building entries"""

    NUM_ENTRIES = 8

    def setup_ui(self):
        self.add_labeled_line(tr("FIELD_NAME"), "name")
        self.add_labeled_line(tr("FIELD_SUBTITLE"), "subtitle")
        self.add_trait_field()

        # Classes
        classes_widget = ClassSelectorWidget()
        classes_widget.classesChanged.connect(lambda: self.on_field_changed('classes'))
        self.fields['classes'] = classes_widget
        self.field_containers['classes'] = classes_widget
        self.main_layout.addWidget(classes_widget)

        # Deck building entries section
        self._entries_group = QGroupBox(tr("GROUP_DECK_BUILDING_OPTIONS"))
        entries_group = self._entries_group
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
            header_input.setPlaceholderText(tr("PLACEHOLDER_HEADER").format(n=i+1))
            header_input.textChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(header_input)

            # Value input (multi-line text field)
            value_input = QPlainTextEdit()
            value_input.setPlaceholderText(tr("PLACEHOLDER_VALUE").format(n=i+1))
            value_input.setFixedHeight(54)  # ~3 lines
            value_input.textChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(value_input)

            entry_widget.setLayout(entry_layout)
            entries_layout.addWidget(entry_widget)

            self.entry_widgets.append((header_input, value_input))

        entries_group.setLayout(entries_layout)
        self.main_layout.addWidget(entries_group)

        # Flavor text
        self.add_labeled_text(tr("FIELD_FLAVOR"), "flavor_text")

        # Illustration
        self.add_illustration_widget()

        # Copyright and extra text fields
        self.add_footer_row()

        self.main_layout.addStretch()

    def enter_translation_mode(self):
        super().enter_translation_mode()
        # _entries_group is not in field_containers; show it explicitly
        self._entries_group.setVisible(True)

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

        # Collect entries from widgets
        entries = []
        for header_input, value_input in self.entry_widgets:
            header = header_input.text().strip()
            value = value_input.toPlainText().strip()
            if header or value:
                entries.append([header, value])

        # Save to face
        text_parts = [
            f"{h} {v}" for h, v in entries if h and v
        ]
        self.face.set('entries', entries if entries else None)
        self.face.set('text', "\n".join(text_parts) if text_parts else None)

        # Emit data_changed signal
        parent = self.parent()
        while parent:
            if hasattr(parent, 'data_changed'):
                parent.data_changed.emit()
                break
            parent = parent.parent()


class MiniInvestigatorEditor(FaceEditor):
    """Editor for mini investigator cards (front and back) - illustration only"""

    def setup_ui(self):
        self.add_illustration_widget()
        self.main_layout.addStretch()
