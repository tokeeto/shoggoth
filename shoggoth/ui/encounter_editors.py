"""
Encounter card editors for Shoggoth (enemy, treachery, location)
"""
from PySide6.QtWidgets import QLabel

from shoggoth.ui.face_editor import FaceEditor
from shoggoth.ui.compact_widgets import ConnectionSymbolField, ENCOUNTER_CLASSES
from shoggoth.files import overlay_dir
from shoggoth.i18n import tr


class EnemyEditor(FaceEditor):
    """Editor for enemy cards"""

    def setup_ui(self):
        self.start_band(tr("BAND_IDENTITY"))
        self.add_identity_row()
        self.add_class_field(default_classes=ENCOUNTER_CLASSES)

        self.start_band(tr("BAND_NUMBERS"))
        self.add_numbers_panel([
            (tr("FIELD_ATTACK") + " / " + tr("FIELD_HEALTH") + " / " + tr("FIELD_EVADE"),
             self.add_icon_stat_row(
                 (overlay_dir / 'svg' / 'skill_icon_C.svg', "attack"),
                 (overlay_dir / 'damage.png', "health"),
                 (overlay_dir / 'svg' / 'skill_icon_A.svg', "evade"),
             )),
            (tr("FIELD_DAMAGE") + " / " + tr("FIELD_HORROR"),
             self.add_icon_count_row(
                 (overlay_dir / 'damage.png', "damage"),
                 (overlay_dir / 'horror.png', "horror"),
             )),
        ])

        self.start_band(tr("BAND_RULES_TEXT"))
        self.add_rules_text_row()

        self.start_band(tr("BAND_PRINT_CREDITS"))
        self.add_illustration_widget()
        self.add_footer_row()
        self.main_layout.addStretch()


class TreacheryEditor(FaceEditor):
    """Editor for treachery cards"""

    def setup_ui(self):
        self.start_band(tr("BAND_IDENTITY"))
        self.add_identity_row()
        self.add_class_field(default_classes=ENCOUNTER_CLASSES)

        self.start_band(tr("BAND_RULES_TEXT"))
        self.add_rules_text_row()

        self.start_band(tr("BAND_PRINT_CREDITS"))
        self.add_illustration_widget()
        self.add_footer_row()
        self.main_layout.addStretch()


class LocationEditor(FaceEditor):
    """Editor for location cards"""

    def setup_ui(self):
        self.start_band(tr("BAND_IDENTITY"))
        self.add_identity_row()

        # Connections: this location's own symbol, then the (up to 6) symbols it
        # connects to — see ConnectionSymbolField for the icon-grid popover this
        # replaced (one 1-column IconComboBox per slot, unusable at 32 symbols).
        connections_label = QLabel(tr("FIELD_CONNECTIONS"))
        connections_label.setProperty("role", "field-label")
        self._target_layout().addWidget(connections_label)

        self.connection_field = ConnectionSymbolField()
        self.connection_field.changed.connect(self._on_connection_field_changed)
        self._target_layout().addWidget(self.connection_field)

        self.start_band(tr("BAND_NUMBERS"))
        self.add_numbers_panel([
            (tr("FIELD_SHROUD") + " / " + tr("FIELD_CLUES"), ["shroud", "clues"]),
        ])

        self.start_band(tr("BAND_RULES_TEXT"))
        self.add_rules_text_row()

        self.start_band(tr("BAND_PRINT_CREDITS"))
        self.add_illustration_widget()
        self.add_footer_row()
        self.main_layout.addStretch()

    def _on_connection_field_changed(self):
        """connection/connections live on one composite widget spanning two face keys,
        so (like the mask-template combo in investigator_editors.py) it's wired by hand
        rather than through the generic self.fields dispatch."""
        if self.updating:
            return
        self.face.set('connection', self.connection_field.get_connection())
        self.face.set('connections', self.connection_field.get_connections())
        parent = self.parent()
        while parent:
            if hasattr(parent, 'data_changed'):
                parent.data_changed.emit()
                break
            parent = parent.parent()

    def load_data(self):
        """Load data from face into fields - override to handle connections specially"""
        self.updating = True

        for field_name, widget in self.fields.items():
            value = self.face.get(field_name, '')
            self.set_widget_value(widget, value)

        self.connection_field.set_connection(self.face.get('connection'))
        self.connection_field.set_connections(self.face.get('connections', []))

        self.updating = False


# Location back editor uses same fields as front
LocationBackEditor = LocationEditor
