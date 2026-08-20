"""
Investigator card editors for Shoggoth
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPlainTextEdit, QLabel
)

from shoggoth.ui.face_editor import FaceEditor
from shoggoth.ui.field_widgets import ClassSelectorWidget
from shoggoth.ui.editor_widgets import NoScrollComboBox
from shoggoth.i18n import tr


class InvestigatorEditor(FaceEditor):
    """Editor for investigator cards (front side)"""

    def setup_ui(self):
        self.start_band(tr("BAND_IDENTITY"))
        self.add_identity_row()

        # Classes
        classes_widget = ClassSelectorWidget()
        classes_widget.classesChanged.connect(lambda: self.on_field_changed('classes'))
        self.fields['classes'] = classes_widget
        self.field_containers['classes'] = classes_widget
        self._target_layout().addWidget(classes_widget)

        self.start_band(tr("BAND_NUMBERS"))
        self.add_numbers_panel([
            (tr("FIELD_WILLPOWER") + " / " + tr("FIELD_INTELLECT") + " / "
             + tr("FIELD_COMBAT") + " / " + tr("FIELD_AGILITY"),
             ["willpower", "intellect", "combat", "agility"]),
            (tr("FIELD_HEALTH") + " / " + tr("FIELD_SANITY"),
             self.add_icon_field_pair("damage", "health", "horror", "sanity")),
        ])

        self.start_band(tr("BAND_RULES_TEXT"))
        self.add_rules_text_row(include_victory=False)

        self.start_band(tr("BAND_PRINT_CREDITS"))
        self.add_illustration_widget()

        # Mask template dropdown
        mask_row = QWidget()
        mask_layout = QHBoxLayout()
        mask_layout.setContentsMargins(0, 0, 0, 0)
        mask_label = QLabel(tr("FIELD_APPLY_MASK"))
        mask_label.setProperty("role", "field-label")
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
        self._target_layout().addWidget(mask_row)

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
        self.start_band(tr("BAND_IDENTITY"))
        self.add_identity_row()

        # Classes
        classes_widget = ClassSelectorWidget()
        classes_widget.classesChanged.connect(lambda: self.on_field_changed('classes'))
        self.fields['classes'] = classes_widget
        self.field_containers['classes'] = classes_widget
        self._target_layout().addWidget(classes_widget)

        # Deck building entries section
        self._entries_group = self.start_band(tr("GROUP_DECK_BUILDING_OPTIONS"))
        entries_layout = QVBoxLayout()
        entries_layout.setSpacing(12)
        entries_layout.setContentsMargins(0, 0, 0, 0)

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

        self._target_layout().addLayout(entries_layout)

        self.start_band(tr("BAND_RULES_TEXT"))
        self.add_labeled_text(tr("FIELD_FLAVOR"), "flavor_text")

        self.start_band(tr("BAND_PRINT_CREDITS"))
        self.add_illustration_widget()
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
