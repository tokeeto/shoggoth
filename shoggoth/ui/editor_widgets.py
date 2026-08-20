"""
Editor widgets (comboboxes, slots) for Shoggoth face editors
"""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QGridLayout, QComboBox, QPushButton
)
from PySide6.QtCore import Qt, Signal, QSize
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
    'mini_investigator', 'mini_investigator_back',
    'concealed', 'concealed_back',
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
CHAPTER2_CARD_TYPES = [
    'chapter_2/enemy',
]


class NoScrollComboBox(QComboBox):
    """ComboBox that ignores wheel events when not focused."""

    def wheelEvent(self, event):
        event.ignore()


def _discover_slots():
    """Slot type names, derived from the "slot_<name>.png" overlay assets."""
    if not overlay_dir.exists():
        return []
    return [f.stem[5:] for f in sorted(overlay_dir.glob('slot_*.png'))]


def _slot_icon(name):
    path = overlay_dir / f"slot_{name}.png"
    return QIcon(str(path)) if path.exists() else QIcon()


class _SlotSuggestionPopup(QWidget):
    """Popup grid of slot-icon suggestions, opened by the "+ slot" ghost chip."""

    def __init__(self, field):
        super().__init__(field, Qt.Popup)
        self.field = field
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        for i, name in enumerate(field.slot_names):
            btn = QPushButton(name.replace('_', ' ').title())
            btn.setIcon(_slot_icon(name))
            btn.setIconSize(QSize(20, 20))
            btn.clicked.connect(lambda _, v=name: self._pick(v))
            layout.addWidget(btn, i // 3, i % 3)

    def _pick(self, value):
        self.field._add(value)
        self.close()


class SlotChipsField(QWidget):
    """Chip editor for an asset's slot(s): most cards use 0 or 1 slot and only rarely 2
    (the game's actual max), so this starts as a single "+ slot" ghost chip and only
    grows to a second chip when a second slot is actually added — instead of always
    reserving width for two side-by-side comboboxes regardless of how many are used.

    Stores/returns the raw ordered slot-name list the renderer expects directly (index 0
    -> slot_1_region, index 1 -> slot_2_region — see renderer.py:render_slots); chip order
    is simply pick order, no positional relabeling.
    """

    slotsChanged = Signal(object)  # Emits list or None

    SLOT_MAX = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._values = []
        self.slot_names = _discover_slots()

        self.flow = QHBoxLayout(self)
        self.flow.setContentsMargins(6, 4, 6, 4)
        self.flow.setSpacing(5)
        self.flow.addStretch(1)

        self.add_btn = QPushButton(f"+ {tr('FIELD_SLOT').lower()}")
        self.add_btn.setProperty("chip", "tag-add")
        self.add_btn.clicked.connect(self._show_suggestions)
        self.flow.insertWidget(0, self.add_btn)

    def _show_suggestions(self):
        popup = _SlotSuggestionPopup(self)
        pos = self.add_btn.mapToGlobal(self.add_btn.rect().bottomLeft())
        popup.move(pos)
        popup.show()

    def _add(self, value):
        if value not in self._values and len(self._values) < self.SLOT_MAX:
            self._values.append(value)
            self._rebuild()
            self.slotsChanged.emit(self.get_slots())

    def _remove(self, value):
        if value in self._values:
            self._values.remove(value)
            self._rebuild()
            self.slotsChanged.emit(self.get_slots())

    def _rebuild(self):
        for i in reversed(range(self.flow.count())):
            widget = self.flow.itemAt(i).widget()
            if widget is not None and widget is not self.add_btn:
                widget.setParent(None)
        insert_at = self.flow.indexOf(self.add_btn)
        for value in self._values:
            chip = QPushButton(f"{value.replace('_', ' ').title()} ×")
            chip.setIcon(_slot_icon(value))
            chip.setIconSize(QSize(16, 16))
            chip.setProperty("chip", "tag")
            chip.clicked.connect(lambda _, v=value: self._remove(v))
            self.flow.insertWidget(insert_at, chip)
            insert_at += 1
        self.add_btn.setVisible(len(self._values) < self.SLOT_MAX)

    def get_slots(self):
        """Get slots as an ordered list, or None if empty."""
        return list(self._values) if self._values else None

    def set_slots(self, slots):
        """Set slots from an ordered list (or None)."""
        self._values = [str(s) for s in slots][:self.SLOT_MAX] if slots else []
        self._rebuild()


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
