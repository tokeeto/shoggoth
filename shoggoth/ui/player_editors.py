"""
Player card editors for Shoggoth (asset, event, skill, customizable)
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QSpinBox
)

from shoggoth.ui.face_editor import FaceEditor
from shoggoth.ui.editor_widgets import SlotChipsField
from shoggoth.ui.card_widgets import IconsWidget
from shoggoth.i18n import tr

# Level selector shared by Asset/Event/Skill: en-dash (no level) / 0-5 / C (custom).
# Values are literal strings the renderer sentinel-checks for ('None'/'Custom') — see
# renderer.py:render_level.
LEVEL_LABELS = ['–', '0', '1', '2', '3', '4', '5', 'C']
LEVEL_VALUES = ['None', '0', '1', '2', '3', '4', '5', 'Custom']


class AssetEditor(FaceEditor):
    """Editor for asset cards"""

    def setup_ui(self):
        self.start_band(tr("BAND_IDENTITY"))
        self.add_identity_row()
        self.add_class_and_level_row(LEVEL_LABELS, LEVEL_VALUES)

        self.start_band(tr("BAND_NUMBERS"))
        self.icons_widget = IconsWidget()
        self.icons_widget.iconsChanged.connect(self.on_icons_changed)
        self.slots_widget = SlotChipsField()
        self.slots_widget.slotsChanged.connect(self.on_slots_changed)
        self.add_numbers_panel([
            (tr("FIELD_COST"), "cost"),
            (tr("LABEL_ICONS"), self.icons_widget),
            (tr("FIELD_HEALTH") + " / " + tr("FIELD_SANITY"),
             self.add_icon_field_pair("damage", "health", "horror", "sanity")),
            (tr("FIELD_SLOT"), self.slots_widget),
        ])

        self.start_band(tr("BAND_RULES_TEXT"))
        self.add_rules_text_row()

        self.start_band(tr("BAND_PRINT_CREDITS"))
        self.add_illustration_widget()
        self.add_footer_row()
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
        self.start_band(tr("BAND_IDENTITY"))
        self.add_identity_row()
        self.add_class_and_level_row(LEVEL_LABELS, LEVEL_VALUES)

        self.start_band(tr("BAND_NUMBERS"))
        self.icons_widget = IconsWidget()
        self.icons_widget.iconsChanged.connect(self.on_icons_changed)
        self.add_numbers_panel([
            (tr("FIELD_COST"), "cost"),
            (tr("LABEL_ICONS"), self.icons_widget),
        ])

        self.start_band(tr("BAND_RULES_TEXT"))
        self.add_rules_text_row()

        self.start_band(tr("BAND_PRINT_CREDITS"))
        self.add_illustration_widget()
        self.add_footer_row()
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
        self.start_band(tr("BAND_IDENTITY"))
        self.add_name_field()

        self.start_band(tr("BAND_RULES_TEXT"))
        self.add_labeled_text(tr("FIELD_TEXT"), "text", use_arkham=True)

        # Entries section (customization options)
        self.start_band(tr("GROUP_CUSTOMIZATION_OPTIONS"))
        entries_layout = QVBoxLayout()
        entries_layout.setSpacing(4)
        entries_layout.setContentsMargins(0, 0, 0, 0)

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

        self._target_layout().addLayout(entries_layout)

        self.start_band(tr("BAND_PRINT_CREDITS"))
        self.add_footer_row()
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
