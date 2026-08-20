"""
Encounter card editors for Shoggoth (enemy, treachery, location)
"""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel
)

from shoggoth.ui.face_editor import FaceEditor
from shoggoth.ui.editor_widgets import IconComboBox
from shoggoth.i18n import tr


class EnemyEditor(FaceEditor):
    """Editor for enemy cards"""

    def setup_ui(self):
        self.start_band(tr("BAND_IDENTITY"))
        self.add_identity_row()
        self.add_class_field()

        self.start_band(tr("BAND_NUMBERS"))
        self.add_numbers_panel([
            (tr("FIELD_ATTACK") + " / " + tr("FIELD_HEALTH") + " / " + tr("FIELD_EVADE"),
             ["attack", "health", "evade"]),
            (tr("FIELD_DAMAGE") + " / " + tr("FIELD_HORROR"), ["damage", "horror"]),
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
        self.add_class_field()

        self.start_band(tr("BAND_RULES_TEXT"))
        self.add_rules_text_row()

        self.start_band(tr("BAND_PRINT_CREDITS"))
        self.add_illustration_widget()
        self.add_footer_row()
        self.main_layout.addStretch()


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
        self.start_band(tr("BAND_IDENTITY"))

        # Connection symbol (this location's own symbol)
        conn_layout = QHBoxLayout()
        conn_label = QLabel(tr("FIELD_CONNECTION_SYMBOL"))
        conn_label.setProperty("role", "field-label")
        conn_label.setMinimumWidth(110)

        self.connection_combo = IconComboBox()
        self.connection_combo.currentIndexChanged.connect(lambda: self.on_connection_changed())
        self.fields['connection'] = self.connection_combo

        conn_layout.addWidget(conn_label)
        conn_layout.addWidget(self.connection_combo)
        conn_layout.addStretch()  # Push to left
        conn_widget = QWidget()
        conn_widget.setLayout(conn_layout)
        self._target_layout().addWidget(conn_widget)

        # Basic fields
        self.add_identity_row()

        # Connections section - single row of icon dropdowns
        connections_row = QHBoxLayout()
        connections_label = QLabel(tr("FIELD_CONNECTIONS"))
        connections_label.setProperty("role", "field-label")
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
        self._target_layout().addWidget(connections_widget)

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


# Location back editor uses same fields as front
LocationBackEditor = LocationEditor
