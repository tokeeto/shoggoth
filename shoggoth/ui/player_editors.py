"""
Player card editors for Shoggoth (asset, event, skill, customizable)
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLineEdit, QSpinBox
)

from shoggoth.ui.face_editor import FaceEditor
from shoggoth.ui.editor_widgets import SlotsWidget
from shoggoth.ui.field_widgets import LabeledLineEdit
from shoggoth.ui.card_widgets import IconsWidget
from shoggoth.i18n import tr


class AssetEditor(FaceEditor):
    """Editor for asset cards"""

    def setup_ui(self):
        # Basic fields
        self.add_labeled_line(tr("FIELD_NAME"), "name")
        self.add_labeled_line(tr("FIELD_SUBTITLE"), "subtitle")

        # Traits with autocomplete
        self.add_trait_field()

        # Grid for compact fields
        grid_widget = QWidget()
        grid_layout = QFormLayout()

        # Classes
        classes_input = LabeledLineEdit(tr("FIELD_CLASSES"))
        classes_input.input.setPlaceholderText(tr("PLACEHOLDER_COMMA_SEPARATED"))
        classes_input.textChanged.connect(lambda: self.on_field_changed('classes'))
        self.fields['classes'] = classes_input.input
        grid_layout.addRow(classes_input)

        # Cost
        cost_input = LabeledLineEdit(tr("FIELD_COST"))
        cost_input.input.textChanged.connect(lambda: self.on_field_changed('cost'))
        self.fields['cost'] = cost_input.input
        grid_layout.addRow(cost_input)

        # Level
        level_combo = QComboBox()
        level_combo.addItems([tr('OPTION_NONE'), '0', '1', '2', '3', '4', '5', tr('OPTION_CUSTOM')])
        level_combo.setItemData(0, 'None')
        level_combo.setItemData(7, 'Custom')
        level_combo.currentTextChanged.connect(lambda: self.on_field_changed('level'))
        self.fields['level'] = level_combo
        grid_layout.addRow(tr("FIELD_LEVEL"), level_combo)

        grid_widget.setLayout(grid_layout)
        self.main_layout.addWidget(grid_widget)

        # Icons widget (separate from grid)
        self.icons_widget = IconsWidget()
        self.icons_widget.iconsChanged.connect(self.on_icons_changed)
        self.main_layout.addWidget(self.icons_widget)

        # Continue with more grid fields
        grid_widget2 = QWidget()
        grid_layout2 = QFormLayout()

        # Health
        health_input = LabeledLineEdit(tr("FIELD_HEALTH"))
        health_input.input.textChanged.connect(lambda: self.on_field_changed('health'))
        self.fields['health'] = health_input.input
        grid_layout2.addRow(health_input)

        # Sanity
        sanity_input = LabeledLineEdit(tr("FIELD_SANITY"))
        sanity_input.input.textChanged.connect(lambda: self.on_field_changed('sanity'))
        self.fields['sanity'] = sanity_input.input
        grid_layout2.addRow(sanity_input)

        grid_widget2.setLayout(grid_layout2)
        self.main_layout.addWidget(grid_widget2)

        # Slots widget (separate from grid for better layout)
        self.slots_widget = SlotsWidget()
        self.slots_widget.slotsChanged.connect(self.on_slots_changed)
        self.main_layout.addWidget(self.slots_widget)

        # Text fields
        self.add_labeled_text(tr("FIELD_TEXT"), "text", use_arkham=True)
        self.add_labeled_text(tr("FIELD_FLAVOR"), "flavor_text")

        # Illustration
        self.add_illustration_widget()

        # Copyright and collection
        self.add_copyright_collection_row()

        self.main_layout.addStretch()

    def load_data(self):
        """Load data including icons and slots widgets"""
        super().load_data()
        # Load icons separately
        icons_value = self.face.get('icons', '')
        self.icons_widget.set_icons_string(icons_value)
        # Load slots separately
        slots_value = self.face.get('slots')
        self.slots_widget.set_slots(slots_value)

    def on_icons_changed(self, icons_str):
        """Handle icons widget change"""
        if self.updating:
            return
        if icons_str:
            self.face.set('icons', icons_str)
        else:
            self.face.set('icons', None)

    def on_slots_changed(self, slots):
        """Handle slots widget change"""
        if self.updating:
            return
        self.face.set('slots', slots)


class EventEditor(FaceEditor):
    """Editor for event cards"""

    def setup_ui(self):
        self.add_labeled_line(tr("FIELD_NAME"), "name")
        self.add_labeled_line(tr("FIELD_SUBTITLE"), "subtitle")

        # Traits with autocomplete
        self.add_trait_field()

        # Grid for compact fields
        grid_widget = QWidget()
        grid_layout = QFormLayout()

        classes_input = LabeledLineEdit(tr("FIELD_CLASSES"))
        classes_input.input.textChanged.connect(lambda: self.on_field_changed('classes'))
        self.fields['classes'] = classes_input.input
        grid_layout.addRow(classes_input)

        cost_input = LabeledLineEdit(tr("FIELD_COST"))
        cost_input.input.textChanged.connect(lambda: self.on_field_changed('cost'))
        self.fields['cost'] = cost_input.input
        grid_layout.addRow(cost_input)

        level_combo = QComboBox()
        level_combo.addItems([tr('OPTION_NONE'), '0', '1', '2', '3', '4', '5', tr('OPTION_CUSTOM')])
        level_combo.currentTextChanged.connect(lambda: self.on_field_changed('level'))
        self.fields['level'] = level_combo
        grid_layout.addRow(tr("FIELD_LEVEL"), level_combo)

        grid_widget.setLayout(grid_layout)
        self.main_layout.addWidget(grid_widget)

        # Icons widget (separate from grid)
        self.icons_widget = IconsWidget()
        self.icons_widget.iconsChanged.connect(self.on_icons_changed)
        self.main_layout.addWidget(self.icons_widget)

        self.add_labeled_text(tr("FIELD_TEXT"), "text", use_arkham=True)
        self.add_labeled_text(tr("FIELD_FLAVOR"), "flavor_text")
        self.add_illustration_widget()

        # Copyright and collection
        self.add_copyright_collection_row()

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


class CustomizableEditor(FaceEditor):
    """Editor for customizable cards with upgrade options"""

    NUM_ENTRIES = 12

    def setup_ui(self):
        self.add_labeled_line(tr("FIELD_NAME"), "name")
        self.add_labeled_text(tr("FIELD_TEXT"), "text", use_arkham=True)

        # Entries section (customization options)
        from PySide6.QtWidgets import QGroupBox, QLineEdit as _QLineEdit
        entries_group = QGroupBox(tr("GROUP_CUSTOMIZATION_OPTIONS"))
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
            cost_input.setToolTip(tr("TOOLTIP_XP_COST"))
            cost_input.valueChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(cost_input)

            # Name input
            name_input = QLineEdit()
            name_input.setPlaceholderText(tr("PLACEHOLDER_OPTION_NAME"))
            name_input.setMaximumWidth(150)
            name_input.textChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(name_input)

            # Text input
            text_input = QLineEdit()
            text_input.setPlaceholderText(tr("PLACEHOLDER_OPTION_EFFECT"))
            text_input.textChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(text_input)

            entry_widget.setLayout(entry_layout)
            entries_layout.addWidget(entry_widget)

            self.entry_widgets.append((cost_input, name_input, text_input))

        entries_group.setLayout(entries_layout)
        self.main_layout.addWidget(entries_group)

        # Copyright and collection
        self.add_copyright_collection_row()

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
