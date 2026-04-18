"""
Editor widgets (comboboxes, slots) for Shoggoth face editors
"""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QComboBox, QLabel
)
from PySide6.QtCore import Signal, QSize
from PySide6.QtGui import QIcon

from shoggoth.files import overlay_dir
from shoggoth.i18n import tr


# All available card types
ALL_CARD_TYPES = [
    'asset', 'event', 'skill',
    'investigator', 'investigator_back',
    'enemy', 'treachery', 'location', 'location_back',
    'act', 'act_back', 'agenda', 'agenda_back',
    'scenario', 'chaos',
    'customizable', 'story',
    'player', 'encounter', 'enemy_deck',
    'act_agenda_full', 'act_agenda_full_back',
]
FULLART_CARD_TYPES = [
    'fullart_asset',
    'fullart_event',
    'fullart_skill',
    'fullart_investigator',
    'fullart_enemy',
    'fullart_treachery',
    'fullart_location',
    'fullart_location_back',
    'fullart_scanning',
    'fullart_scanning_back',
    'fullart_encounter_with_connections',
]


class NoScrollComboBox(QComboBox):
    """ComboBox that ignores wheel events when not focused."""

    def wheelEvent(self, event):
        event.ignore()


class SlotComboBox(NoScrollComboBox):
    """ComboBox that displays available slot types with icons."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setIconSize(QSize(24, 24))

        # Add empty option first
        self.addItem('-', userData=None)

        # Discover slot files dynamically
        if overlay_dir.exists():
            slot_files = sorted(overlay_dir.glob('slot_*.png'))
            for slot_file in slot_files:
                # Extract name from "slot_<name>.png"
                name = slot_file.stem[5:]  # Remove "slot_" prefix
                icon = QIcon(str(slot_file))
                self.addItem(icon, name, userData=name)

    def setCurrentSlot(self, slot_name):
        """Set current selection by slot name"""
        if not slot_name:
            self.setCurrentIndex(0)
        else:
            for i in range(self.count()):
                if self.itemData(i) == slot_name:
                    self.setCurrentIndex(i)
                    return
            # If not found, default to empty
            self.setCurrentIndex(0)

    def currentSlot(self):
        """Get current slot name (or None for empty)"""
        return self.itemData(self.currentIndex())


class SlotsWidget(QWidget):
    """Widget with two slot comboboxes for asset cards."""

    slotsChanged = Signal(object)  # Emits list or None

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.slot1_combo = SlotComboBox()
        self.slot2_combo = SlotComboBox()

        self.slot1_combo.currentIndexChanged.connect(self._on_changed)
        self.slot2_combo.currentIndexChanged.connect(self._on_changed)

        layout.addWidget(QLabel(tr("FIELD_SLOT") + " 1:"))
        layout.addWidget(self.slot1_combo)
        layout.addWidget(QLabel(tr("FIELD_SLOT") + " 2:"))
        layout.addWidget(self.slot2_combo)
        layout.addStretch()

        self.setLayout(layout)

    def _on_changed(self):
        """Emit the current slots value"""
        self.slotsChanged.emit(self.get_slots())

    def get_slots(self):
        """Get slots as list (reversed order for rendering) or None if both empty"""
        slot1 = self.slot1_combo.currentSlot()
        slot2 = self.slot2_combo.currentSlot()

        if not slot1 and not slot2:
            return None
        # Return as [right, left] due to rendering order, filtering out None
        result = [s for s in [slot2, slot1] if s]
        return result if result else None

    def set_slots(self, slots):
        """Set slots from list (reversed order) or None"""
        # Block signals to prevent triggering changes during load
        self.slot1_combo.blockSignals(True)
        self.slot2_combo.blockSignals(True)
        try:
            if not slots:
                self.slot1_combo.setCurrentSlot(None)
                self.slot2_combo.setCurrentSlot(None)
            elif len(slots) == 1:
                self.slot1_combo.setCurrentSlot(slots[0])
                self.slot2_combo.setCurrentSlot(None)
            else:
                # slots is [right, left], so reverse when setting
                self.slot1_combo.setCurrentSlot(slots[1] if len(slots) > 1 else None)
                self.slot2_combo.setCurrentSlot(slots[0])
        finally:
            self.slot1_combo.blockSignals(False)
            self.slot2_combo.blockSignals(False)


class IconComboBox(NoScrollComboBox):
    """ComboBox that displays icons for connection symbols"""

    CONNECTION_SYMBOLS = [
        'None',
        'circle', 'circle_alt',
        'clover', 'clover_alt',
        'cross', 'cross_alt',
        'diamond', 'diamond_alt',
        'double_slash', 'double_slash_alt',
        'heart', 'heart_alt',
        'hourglass', 'hourglass_alt',
        'crescent', 'crescent_alt',
        'moon',
        'quote', 'quote_alt',
        'slash', 'slash_alt',
        'spade',
        'square', 'square_alt',
        'star', 'star_alt',
        'sun',
        't', 't_alt',
        'triangle', 'triangle_alt',
        'ying',
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        # Set fixed narrow width
        self.setFixedWidth(55)
        self.setIconSize(QSize(28, 28))

        # Add all symbols with icons
        from PySide6.QtGui import QIcon, QPixmap

        for symbol in self.CONNECTION_SYMBOLS:
            if symbol == 'None':
                # Empty option - show dash
                self.addItem('-', userData=None)
            else:
                icon_path = overlay_dir / 'svg' / f"connection_{symbol}.svg"
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
