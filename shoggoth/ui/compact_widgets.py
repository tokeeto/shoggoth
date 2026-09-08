"""
Shared compact-editor components: Band, Stepper, NumbersPanel, chip helpers, SegmentedToggle.

These are pure-Qt building blocks styled via the dynamic-property selectors defined in
compact_theme.EDITOR_QSS (setProperty("role", ...) / setProperty("chip", ...)) rather than by
subclassing every widget — see compact_theme.py for the actual colors/values.
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QPushButton,
    QLineEdit, QToolButton, QButtonGroup, QCompleter, QSizePolicy, QApplication
)
from PySide6.QtCore import Qt, Signal, QEvent, QSize
from PySide6.QtGui import QFocusEvent, QPixmap, QIcon

from shoggoth.files import overlay_dir
from shoggoth.i18n import tr
from shoggoth.ui.editor_widgets import (
    NoScrollComboBox, CONNECTION_ORIGINALS, CONNECTION_ALTS, connection_symbol_label
)

# Class chip colors — semantic (map to the game's own class colors), the one deliberate
# exception to the "no custom color" rule elsewhere in the compact editor theme.
# value -> (background, text)
CLASS_CHIP_COLORS = {
    'guardian': ('#2a5f8f', '#eaf3fb'),
    'seeker': ('#c9a227', '#2b2205'),
    'rogue': ('#2e7d46', '#eafbf0'),
    'survivor': ('#a5322f', '#fbeaea'),
    'mystic': ('#5c3f8f', '#f1eafb'),
    'neutral': ('#6b6f76', '#f2f2f3'),
    'specialist': ('#2b2f36', '#e8e8ea'),
    'weakness': ('#ffffff', '#111111'),
    'basic weakness': ('#ffffff', '#111111'),
    'reward': ('#8a6d1f', '#fdf6e3'),
}
# Per-container default toggle rows (see ClassChipsField) — each face editor passes the
# preset that matches what its card type actually needs, rather than one shared list.
PLAYER_CLASSES = ['guardian', 'survivor', 'seeker', 'mystic', 'rogue', 'neutral']
ENCOUNTER_CLASSES = ['weakness', 'basic weakness', 'neutral']
# Universal pool offered by the "Special" popover, minus whatever's already in the
# field's own default row (e.g. an encounter field only sees "specialist" there).
# "reward" is never a default toggle on either row — unlike weakness, it's always
# secondary, never a card's main class — so it only ever surfaces here.
SPECIAL_CANDIDATES = ['specialist', 'weakness', 'basic weakness', 'reward']
_DEFAULT_CLASS_CHIP_COLOR = ('#5a5f66', '#f2f2f3')

_CLASS_LABEL_KEYS = {
    'guardian': 'CLASS_GUARDIAN', 'seeker': 'CLASS_SEEKER', 'rogue': 'CLASS_ROGUE',
    'survivor': 'CLASS_SURVIVOR', 'mystic': 'CLASS_MYSTIC', 'neutral': 'CLASS_NEUTRAL',
    'specialist': 'CLASS_SPECIALIST', 'weakness': 'CLASS_WEAKNESS', 'basic weakness': 'CLASS_BASIC_WEAKNESS',
    'reward': 'CLASS_REWARD',
}


def class_label(value):
    key = _CLASS_LABEL_KEYS.get(value)
    return tr(key) if key else value.title()


def _hairline(vertical=False):
    frame = QFrame()
    frame.setFrameShape(QFrame.VLine if vertical else QFrame.HLine)
    frame.setFrameShadow(QFrame.Sunken)
    frame.setProperty("role", "divider" if vertical else "hairline")
    return frame


class Band(QWidget):
    """A section: uppercase label + hairline rule + padded content area.

    No border around the band itself — bands are separated by the rule + spacing only, per
    the style guide ("never nest a bordered box inside a bordered box more than one level deep").
    """

    def __init__(self, title, hint=None, collapsible=False, parent=None):
        super().__init__(parent)
        self.collapsible = collapsible
        # Never let a band get stretched taller than its content — extra vertical space
        # (e.g. from the scroll area forcing the whole column to fill the viewport) must
        # go to the trailing addStretch() in FaceEditor.main_layout, not leak into a band.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 14, 0, 0)
        outer.setSpacing(7)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.toggle = None
        if collapsible:
            self.toggle = QToolButton()
            self.toggle.setCheckable(True)
            self.toggle.setChecked(False)
            self.toggle.setArrowType(Qt.RightArrow)
            self.toggle.setText(title.upper())
            self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.toggle.setAutoRaise(True)
            self.toggle.setProperty("role", "band-label")
            self.toggle.toggled.connect(self._on_toggled)
            header.addWidget(self.toggle)
        else:
            label = QLabel(title.upper())
            label.setProperty("role", "band-label")
            header.addWidget(label)

        header.addWidget(_hairline(), 1)

        self.hint_label = None
        if hint:
            self.hint_label = QLabel(hint)
            self.hint_label.setProperty("role", "band-hint")
            header.addWidget(self.hint_label)

        outer.addLayout(header)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        outer.addWidget(self.content)

        if collapsible:
            self.content.setVisible(False)

    def _on_toggled(self, checked):
        self.toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.content.setVisible(checked)

    def set_expanded(self, expanded):
        if self.toggle is not None:
            self.toggle.setChecked(expanded)


class Stepper(QWidget):
    """A `- value +` stepper: three fixed-width cells, no visible gap.

    The middle cell stays a real, freely-editable QLineEdit (not a spinbox) since several
    Arkham fields legitimately hold non-numeric tokens ("X", "-", "*"). The +/- buttons only
    do a best-effort integer parse/clamp/increment; anything else is left for the user to type.
    """

    textChanged = Signal(str)

    def __init__(self, width=34, minimum=0, maximum=99, floor_value=None, parent=None):
        super().__init__(parent)
        self.minimum = minimum
        self.maximum = maximum
        # An optional sentinel text one notch below `minimum` — e.g. Cost's "---" ("cannot
        # be played/paid for by normal means"), reached by pressing "-" at minimum, and left
        # by pressing "+" back to minimum.
        self.floor_value = floor_value

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.minus_btn = QPushButton("−")
        self.minus_btn.setProperty("role", "stepper-btn")
        self.minus_btn.setFixedSize(20, 24)
        self.minus_btn.clicked.connect(lambda: self._step(-1))

        self.value_input = QLineEdit()
        self.value_input.setProperty("role", "stepper-value")
        self.value_input.setFixedSize(width, 24)
        self.value_input.textChanged.connect(self.textChanged.emit)

        self.plus_btn = QPushButton("+")
        self.plus_btn.setProperty("role", "stepper-btn")
        self.plus_btn.setFixedSize(20, 24)
        self.plus_btn.clicked.connect(lambda: self._step(1))

        layout.addWidget(self.minus_btn)
        layout.addWidget(self.value_input)
        layout.addWidget(self.plus_btn)

    def _step(self, delta):
        text = self.value_input.text().strip()

        if self.floor_value is not None and text == self.floor_value:
            if delta > 0:
                self.value_input.setText(str(self.minimum))
            # delta < 0: already at the floor, nothing lower to go to
            return

        try:
            value = int(text)
        except (ValueError, TypeError):
            return

        new_value = value + delta
        if self.floor_value is not None and new_value < self.minimum:
            self.value_input.setText(self.floor_value)
            return

        value = max(self.minimum, min(self.maximum, new_value))
        self.value_input.setText(str(value))

    def text(self):
        return self.value_input.text()

    def setText(self, text):
        self.value_input.setText(text)


PER_TAG = "<per>"


class PerStepper(QWidget):
    """A Stepper with a trailing "per investigator" toggle button.

    Several stat fields (enemy attack/health/evade, location/act clue thresholds, agenda
    doom thresholds) can be printed as "X per investigator" — the toggle appends/removes a
    literal "<per>" suffix on the *stored* value, same idea as UniqueNameField's "<unique>"
    prefix toggle on the name field, just suffixed and shared across these stepper fields
    instead of being its own one-off widget.
    """

    textChanged = Signal(str)

    def __init__(self, width=34, minimum=0, maximum=99, floor_value=None, parent=None):
        super().__init__(parent)
        self._updating = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self.stepper = Stepper(width=width, minimum=minimum, maximum=maximum, floor_value=floor_value)
        self.stepper.textChanged.connect(self._on_changed)
        row.addWidget(self.stepper)

        self.per_btn = QPushButton("P")
        self.per_btn.setCheckable(True)
        self.per_btn.setProperty("role", "per-btn")
        self.per_btn.setFixedSize(22, 24)
        self.per_btn.setToolTip(tr("TOOLTIP_PER"))
        self.per_btn.toggled.connect(self._on_toggle_per)
        row.addWidget(self.per_btn)

    def _on_changed(self, *_):
        if not self._updating:
            self.textChanged.emit(self.text())

    def _on_toggle_per(self, _checked):
        self._on_changed()

    def text(self):
        """The raw stored value: the stepper's value plus the <per> tag (if toggled)."""
        suffix = PER_TAG if self.per_btn.isChecked() else ""
        return self.stepper.text() + suffix

    def setText(self, value):
        """Load a raw stored value: a literal trailing "<per>" (if present) becomes the
        toggle state; everything before it goes into the stepper untouched."""
        self._updating = True
        value = value or ""
        per = value.endswith(PER_TAG)
        self.stepper.setText(value[:-len(PER_TAG)] if per else value)
        self.per_btn.setChecked(per)
        self._updating = False


def _icon_label(icon_path, size=16):
    """A fixed-size QLabel showing icon_path scaled to size, or blank if missing."""
    label = QLabel()
    if icon_path and Path(icon_path).exists():
        pixmap = QPixmap(str(icon_path)).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(pixmap)
    label.setFixedSize(size, size)
    return label


class IconStatField(QWidget):
    """Icon + closed-set dropdown ("-"/X/0-9) + "per investigator" toggle button.

    Used for stats that are always one of a small fixed set of printed values (enemy
    attack/health/evade) — unlike Stepper's freely-typed value, a dropdown is the more
    honest control here since nothing outside that set is ever printed on a card.
    """

    LABELS = ['–', 'X'] + [str(n) for n in range(10)]
    VALUES = ['<dash>', 'X'] + [str(n) for n in range(10)]

    textChanged = Signal(str)

    def __init__(self, icon_path=None, parent=None):
        super().__init__(parent)
        self._updating = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        row.addWidget(_icon_label(icon_path))

        self.combo = NoScrollComboBox()
        for label, value in zip(self.LABELS, self.VALUES):
            self.combo.addItem(label, value)
        self.combo.setProperty("role", "flat-combo")
        self.combo.setFixedWidth(38)
        self.combo.currentIndexChanged.connect(self._on_changed)
        row.addWidget(self.combo)

        self.per_btn = QPushButton("P")
        self.per_btn.setCheckable(True)
        self.per_btn.setProperty("role", "per-btn")
        self.per_btn.setFixedSize(22, 24)
        self.per_btn.setToolTip(tr("TOOLTIP_PER"))
        self.per_btn.toggled.connect(self._on_changed)
        row.addWidget(self.per_btn)

    def _on_changed(self, *_):
        if not self._updating:
            self.textChanged.emit(self.text())

    def text(self):
        """The raw stored value: the dropdown's value plus the <per> tag (if toggled)."""
        suffix = PER_TAG if self.per_btn.isChecked() else ""
        return (self.combo.currentData() or "") + suffix

    def setText(self, value):
        """Load a raw stored value: a literal trailing "<per>" (if present) becomes the
        toggle state; an unrecognized remaining value (outside the fixed set) falls back
        to the first entry, same as SegmentedToggle does for an unrecognized value."""
        self._updating = True
        value = value or ""
        per = value.endswith(PER_TAG)
        if per:
            value = value[:-len(PER_TAG)]
        try:
            index = self.VALUES.index(value)
        except ValueError:
            index = 0
        self.combo.setCurrentIndex(index)
        self.per_btn.setChecked(per)
        self._updating = False


class IconCountField(QWidget):
    """Icon + plain 0-N count dropdown, no "per investigator" toggle.

    For stats that are just "how many of this icon to print" (enemy damage/horror) rather
    than a printed number — there's no "X" or "-" case, since it's not a value on the card
    at all, just an icon repeat count.
    """

    textChanged = Signal(str)

    def __init__(self, icon_path=None, max_count=5, parent=None):
        super().__init__(parent)
        self._updating = False
        self.values = [str(n) for n in range(max_count + 1)]

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        row.addWidget(_icon_label(icon_path))

        self.combo = NoScrollComboBox()
        self.combo.addItems(self.values)
        self.combo.setProperty("role", "flat-combo")
        self.combo.setFixedWidth(38)
        self.combo.currentIndexChanged.connect(self._on_changed)
        row.addWidget(self.combo)

    def _on_changed(self, *_):
        if not self._updating:
            self.textChanged.emit(self.text())

    def text(self):
        return self.combo.currentText()

    def setText(self, value):
        """An unrecognized value (outside 0-max_count) falls back to 0, same as
        IconStatField does for its own out-of-range values."""
        self._updating = True
        index = self.values.index(value) if value in self.values else 0
        self.combo.setCurrentIndex(index)
        self._updating = False


class NumbersPanel(QFrame):
    """Bordered mini-panel holding several stat sub-groups, divided by thin vertical rules."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Sunken)
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(13, 11, 13, 11)
        self.layout_.setSpacing(14)
        self._first = True

    def add_group(self, label, widget, stretch=0):
        """Add a labelled sub-group (e.g. "Cost", "Health / Sanity") to the panel."""
        if not self._first:
            self.layout_.addWidget(_hairline(vertical=True))
        self._first = False

        group = QWidget()
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(6)

        if label:
            label_widget = QLabel(label.upper())
            label_widget.setProperty("role", "field-label")
            group_layout.addWidget(label_widget)

        group_layout.addWidget(widget)
        self.layout_.addWidget(group, stretch)
        return group


class TagChipsField(QWidget):
    """Chip editor for open, user-typed lists (Traits): filled pills with `x`, plus a trailing
    dashed "+ <label>" ghost chip that turns into a text entry with autocomplete on click.

    Stores/round-trips the exact same "value1. value2." dot-joined string format the rest of
    the app expects — this widget only changes how the user edits that string.
    """

    textChanged = Signal(str)

    def __init__(self, add_label="+ trait", completions=None, parent=None):
        super().__init__(parent)
        self._values = []
        self._placeholder_values = []
        self._completions = completions or []

        self.flow = QHBoxLayout(self)
        self.flow.setContentsMargins(6, 4, 6, 4)
        self.flow.setSpacing(5)
        self.flow.addStretch(1)

        self.add_btn = QPushButton(add_label)
        self.add_btn.setProperty("chip", "tag-add")
        self.add_btn.clicked.connect(self._start_add)
        self.flow.insertWidget(0, self.add_btn)

        self.entry = QLineEdit()
        self.entry.setVisible(False)
        self.entry.setFixedWidth(120)
        if self._completions:
            completer = QCompleter(self._completions)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            self.entry.setCompleter(completer)
        # Enter commits the trait and keeps adding (most cards take 1-3 traits, so
        # re-clicking "+ trait" after every single one is annoying); losing focus commits
        # whatever's typed and closes back to the ghost chip. Enter on an empty entry also
        # closes — that's the "I'm done" signal.
        self.entry.returnPressed.connect(self._on_return_pressed)
        self.entry.installEventFilter(self)
        self.flow.insertWidget(0, self.entry)

    def _start_add(self):
        self.add_btn.setVisible(False)
        self.entry.setVisible(True)
        self.entry.setFocus()

    def _close_entry(self):
        self.entry.blockSignals(True)
        self.entry.clear()
        self.entry.blockSignals(False)
        self.entry.setVisible(False)
        self.add_btn.setVisible(True)

    def _commit_entry_text(self, text):
        self.entry.blockSignals(True)
        self.entry.clear()
        self.entry.blockSignals(False)
        formatted = text[0].upper() + text[1:]
        if not formatted.endswith('.'):
            formatted += '.'
        if formatted not in self._values:
            self._values.append(formatted)
        self._rebuild()
        self.textChanged.emit(self.text())

    def _on_return_pressed(self):
        text = self.entry.text().strip()
        if not text:
            self._close_entry()
            return
        self._commit_entry_text(text)
        self.entry.setFocus()

    def eventFilter(self, obj, event):
        if obj is self.entry and event.type() == QEvent.FocusOut:
            # The completer popup opening/taking focus also fires a FocusOut on the entry
            # (QLineEdit only suppresses this for its own editingFinished signal, not for a
            # plain event filter) — that's not the user clicking away, so ignore it. This is
            # the same PopupFocusReason check QLineEdit itself uses internally for this.
            reason = event.reason() if isinstance(event, QFocusEvent) else None
            if reason == Qt.PopupFocusReason:
                return super().eventFilter(obj, event)
            text = self.entry.text().strip()
            if text:
                self._commit_entry_text(text)
            self._close_entry()
        return super().eventFilter(obj, event)

    def _remove(self, value):
        if value in self._values:
            self._values.remove(value)
            self._rebuild()
            self.textChanged.emit(self.text())

    def _rebuild(self):
        for i in reversed(range(self.flow.count())):
            item = self.flow.itemAt(i)
            widget = item.widget()
            if widget is not None and widget not in (self.add_btn, self.entry):
                widget.setParent(None)
        insert_at = self.flow.indexOf(self.entry)
        if self._values:
            for value in self._values:
                chip = QPushButton(f"{value.rstrip('.')} ×")
                chip.setProperty("chip", "tag")
                chip.clicked.connect(lambda _, v=value: self._remove(v))
                self.flow.insertWidget(insert_at, chip)
                insert_at += 1
        else:
            # No explicit value set on this face — show the inherited/fallback traits as
            # non-interactive "ghost" chips, same spirit as a placeholder on a text field.
            for value in self._placeholder_values:
                chip = QPushButton(value.rstrip('.'))
                chip.setProperty("chip", "tag-ghost")
                chip.setEnabled(False)
                self.flow.insertWidget(insert_at, chip)
                insert_at += 1

    def text(self):
        return ' '.join(self._values)

    def setText(self, text):
        text = (text or '').strip()
        self._values = [v.strip() + '.' for v in text.split('.') if v.strip()] if text else []
        self._rebuild()

    def set_placeholder(self, text):
        """Show the inherited/fallback trait values as muted ghost chips when empty."""
        text = (text or '').strip()
        self._placeholder_values = [v.strip() + '.' for v in text.split('.') if v.strip()] if text else []
        if not self._values:
            self._rebuild()


class SegmentedToggle(QWidget):
    """A row of equal-height rounded buttons with a single exclusive active state.

    `values` (optional) parallels `options` with the underlying data value each button
    represents (defaults to the button's index) — e.g. the Level selector uses button
    labels ['–','0',...,'5','C'] backed by values ['None','0',...,'5','Custom'].
    """

    currentChanged = Signal(int)
    valueChanged = Signal(object)

    def __init__(self, options, values=None, parent=None):
        super().__init__(parent)
        self.values = list(values) if values is not None else list(range(len(options)))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = []
        for i, label in enumerate(options):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("role", "segment")
            pos = "left" if i == 0 else ("right" if i == len(options) - 1 else "mid")
            btn.setProperty("segmentPos", pos)
            btn.setFixedHeight(28)
            self.group.addButton(btn, i)
            layout.addWidget(btn)
            self.buttons.append(btn)
        if self.buttons:
            self.buttons[0].setChecked(True)
        self.group.idClicked.connect(self._on_clicked)

    def _on_clicked(self, index):
        self.currentChanged.emit(index)
        self.valueChanged.emit(self.values[index])

    def current_index(self):
        return self.group.checkedId()

    def set_current_index(self, index):
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)

    def current_value(self):
        index = self.group.checkedId()
        return self.values[index] if index >= 0 else None

    def set_current_value(self, value):
        try:
            index = self.values.index(value)
        except ValueError:
            index = 0
        self.set_current_index(index)


def _class_chip_style(value, checked=False):
    """Always-colored chip style (semantic per-class color) for compact list rows —
    used by the Special popover and by overflow (legacy/custom) chips, where every
    row shown is already a real value, not an unselected option."""
    bg, fg = CLASS_CHIP_COLORS.get(value, _DEFAULT_CLASS_CHIP_COLOR)
    border = "2px solid #333" if checked else "1px solid rgba(0,0,0,.2)"
    return (
        f"QPushButton {{ background: {bg}; color: {fg}; border-radius: 5px; "
        f"padding: 4px 9px; font-size: 11px; font-weight: 600; border: {border}; }}"
    )


def _class_toggle_style(value, checked):
    """Always-visible main-row toggle style: neutral/palette-based when unchecked (so
    inactive classes don't read as "active" just for being on screen), the class's
    semantic color when checked — mirrors _class_chip_style's property set exactly so
    toggling doesn't shift size/padding."""
    if not checked:
        return (
            "QPushButton { background: palette(button); color: palette(button-text); "
            "border: 1px solid palette(mid); border-radius: 5px; padding: 4px 9px; "
            "font-size: 11px; font-weight: 600; }"
        )
    bg, fg = CLASS_CHIP_COLORS.get(value, _DEFAULT_CLASS_CHIP_COLOR)
    return (
        f"QPushButton {{ background: {bg}; color: {fg}; border: 1px solid {bg}; "
        "border-radius: 5px; padding: 4px 9px; font-size: 11px; font-weight: 600; }"
    )


class _ClassSpecialPopover(QWidget):
    """Popover opened by the "Special ▾" button: preset values not already covered by
    the field's own default row (e.g. Weakness/Basic Weakness are hidden here for an
    encounter-card field, since they're already primary toggles there), plus a free-text
    entry for anything else — arbitrary legacy/custom class strings included."""

    def __init__(self, field):
        super().__init__(field, Qt.Popup)
        self.field = field
        candidates = [v for v in SPECIAL_CANDIDATES if v not in field.default_classes]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.buttons = {}
        for value in candidates:
            btn = QPushButton(class_label(value))
            btn.setCheckable(True)
            btn.setChecked(value in field.values())
            btn.setStyleSheet(_class_chip_style(value, checked=btn.isChecked()))
            btn.clicked.connect(lambda _, v=value: self._pick(v))
            self.buttons[value] = btn
            layout.addWidget(btn)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText(tr("PLACEHOLDER_CUSTOM_CLASS"))
        self.entry.returnPressed.connect(self._commit_entry)
        layout.addWidget(self.entry)

    def _pick(self, value):
        self.field._pick(value)
        btn = self.buttons[value]
        btn.setChecked(value in self.field.values())
        btn.setStyleSheet(_class_chip_style(value, checked=btn.isChecked()))

    def _commit_entry(self):
        text = self.entry.text().strip().lower()
        if not text:
            return
        self.entry.clear()
        self.field._pick(text)
        self.close()


class ClassChipsField(QWidget):
    """Chip editor for the card Class field: an always-visible row of toggle buttons
    for the container's own default classes (e.g. Guardian/Seeker/... for player cards,
    Weakness/Basic Weakness/Neutral for encounter cards — see PLAYER_CLASSES/
    ENCOUNTER_CLASSES), a "Special ▾" popover for everything else, and overflow chips
    for arbitrary legacy/custom values already present in the data (never silently
    dropped). Plain click selects a single value; Shift/Ctrl-click combines multiple.
    """

    changed = Signal()

    def __init__(self, default_classes=None, parent=None):
        super().__init__(parent)
        self._values = []
        self.default_classes = list(default_classes) if default_classes else list(PLAYER_CLASSES)

        self.flow = QHBoxLayout(self)
        self.flow.setContentsMargins(6, 4, 6, 4)
        self.flow.setSpacing(5)

        self.toggle_buttons = {}
        for value in self.default_classes:
            btn = QPushButton(class_label(value))
            btn.setCheckable(True)
            btn.setStyleSheet(_class_toggle_style(value, False))
            btn.clicked.connect(lambda _, v=value: self._pick(v))
            self.toggle_buttons[value] = btn
            self.flow.addWidget(btn)

        self.special_btn = QPushButton(f"{tr('LABEL_SPECIAL')} ▾")
        self.special_btn.setProperty("chip", "tag-ghost")
        self.special_btn.clicked.connect(self._show_special)
        self.flow.addWidget(self.special_btn)

        self.overflow_layout = QHBoxLayout()
        self.overflow_layout.setContentsMargins(0, 0, 0, 0)
        self.overflow_layout.setSpacing(5)
        self.flow.addLayout(self.overflow_layout)
        self.flow.addStretch(1)

    def values(self):
        return list(self._values)

    def _show_special(self):
        popup = _ClassSpecialPopover(self)
        pos = self.special_btn.mapToGlobal(self.special_btn.rect().bottomLeft())
        popup.move(pos)
        popup.show()

    def _pick(self, value):
        modifiers = QApplication.keyboardModifiers()
        combine = bool(modifiers & (Qt.ShiftModifier | Qt.ControlModifier))
        if combine:
            if value in self._values:
                self._values.remove(value)
            else:
                self._values.append(value)
        elif self._values == [value]:
            self._values = []
        else:
            self._values = [value]
        self._rebuild()
        self.changed.emit()

    def _remove(self, value):
        if value in self._values:
            self._values.remove(value)
            self._rebuild()
            self.changed.emit()

    def _rebuild(self):
        for value, btn in self.toggle_buttons.items():
            checked = value in self._values
            btn.blockSignals(True)
            btn.setChecked(checked)
            btn.blockSignals(False)
            btn.setStyleSheet(_class_toggle_style(value, checked))

        for i in reversed(range(self.overflow_layout.count())):
            widget = self.overflow_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)
        overflow = [v for v in self._values if v not in self.default_classes]
        for value in overflow:
            chip = QPushButton(f"{class_label(value)} ×")
            chip.setStyleSheet(_class_chip_style(value, checked=True))
            chip.setFlat(True)
            chip.clicked.connect(lambda _, v=value: self._remove(v))
            self.overflow_layout.addWidget(chip)

    def get_classes(self):
        return list(self._values) if self._values else None

    def set_classes(self, value):
        if not value:
            self._values = []
        elif isinstance(value, list):
            self._values = [str(v) for v in value]
        else:
            self._values = [v.strip() for v in str(value).split(',') if v.strip()]
        self._rebuild()


class _ConnectionSymbolPopover(QWidget):
    """Icon grid popover shared by ConnectionSymbolField's own-symbol button and its
    "+ add symbol" button, split into Originals/Alts tabs (the real 32-symbol set
    already divides cleanly along that naming convention — see CONNECTION_ORIGINALS/
    CONNECTION_ALTS in editor_widgets.py).

    `multi=False` (own symbol): a single pick, closes the popover; the current
    selection is highlighted.
    `multi=True` (connects to): picking adds a chip and the popover stays open so
    several can be added in a row; symbols already connected-to are disabled.
    """

    COLUMNS = 6

    def __init__(self, field, multi):
        super().__init__(field, Qt.Popup)
        self.field = field
        self.multi = multi
        self.buttons = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        tabs_row = QHBoxLayout()
        tabs_row.setContentsMargins(0, 0, 0, 0)
        tabs_row.setSpacing(2)
        outer.addLayout(tabs_row)

        groups = [(tr("LABEL_ORIGINALS"), CONNECTION_ORIGINALS), (tr("LABEL_ALTS"), CONNECTION_ALTS)]
        self.tab_buttons = {}
        self.pages = {}
        for name, symbols in groups:
            tab_btn = QPushButton(name)
            tab_btn.setCheckable(True)
            tab_btn.setProperty("role", "segment")
            tab_btn.clicked.connect(lambda _, n=name: self._show_page(n))
            self.tab_buttons[name] = tab_btn
            tabs_row.addWidget(tab_btn)

            page = QWidget()
            grid = QGridLayout(page)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(3)
            for i, symbol in enumerate(symbols):
                btn = QToolButton()
                icon_path = overlay_dir / 'svg' / f"connection_{symbol}.svg"
                if icon_path.exists():
                    btn.setIcon(QIcon(str(icon_path)))
                else:
                    btn.setText(symbol[:2])
                btn.setIconSize(QSize(24, 24))
                btn.setToolTip(connection_symbol_label(symbol))
                btn.clicked.connect(lambda _, s=symbol: self._pick(s))
                grid.addWidget(btn, i // self.COLUMNS, i % self.COLUMNS)
                self.buttons[symbol] = btn
            outer.addWidget(page)
            self.pages[name] = page

        if multi:
            hint = QLabel(tr("HINT_SYMBOL_PICKER"))
            hint.setProperty("role", "band-hint")
            outer.addWidget(hint)

        self._refresh_state()
        first_name = groups[0][0]
        self.tab_buttons[first_name].setChecked(True)
        self._show_page(first_name)

    def _show_page(self, name):
        for n, btn in self.tab_buttons.items():
            btn.setChecked(n == name)
        for n, page in self.pages.items():
            page.setVisible(n == name)

    def _refresh_state(self):
        if self.multi:
            used = set(self.field.get_connections() or [])
            for symbol, btn in self.buttons.items():
                btn.setEnabled(symbol not in used)
        else:
            current = self.field.get_connection()
            for symbol, btn in self.buttons.items():
                btn.setStyleSheet(
                    "QToolButton { background: palette(highlight); border-radius: 4px; }"
                    if symbol == current else ""
                )

    def _pick(self, symbol):
        if self.multi:
            if self.field._add_connection(symbol):
                self._refresh_state()
        else:
            self.field._set_own_symbol(symbol)
            self.close()


class ConnectionSymbolField(QWidget):
    """Location connections editor (mock 1a): this location's own symbol (single
    choice) plus the symbols it connects to, both picked from the shared
    _ConnectionSymbolPopover grid instead of a 1-column combo box listing all 32
    symbols. Connects-to is capped at MAX_CONNECTIONS — a real rendering constraint,
    not an arbitrary UI limit (renderer.render_connection_icons looks up fixed
    connection_1_region..connection_6_region slots from the card art defaults).
    """

    MAX_CONNECTIONS = 6
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._own = None
        self._connections = []

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        own_col = QVBoxLayout()
        own_col.setContentsMargins(0, 0, 0, 0)
        own_col.setSpacing(5)
        own_label = QLabel(tr("LABEL_THIS_LOCATION").upper())
        own_label.setProperty("role", "field-label")
        own_col.addWidget(own_label)

        own_row = QHBoxLayout()
        own_row.setContentsMargins(0, 0, 0, 0)
        own_row.setSpacing(3)
        self.own_btn = QPushButton()
        self.own_btn.setProperty("chip", "tag")
        self.own_btn.clicked.connect(lambda: self._open_popover(multi=False))
        own_row.addWidget(self.own_btn)
        self.own_clear_btn = QPushButton("×")
        self.own_clear_btn.setProperty("chip", "tag-ghost")
        self.own_clear_btn.setFixedWidth(20)
        self.own_clear_btn.clicked.connect(self._clear_own_symbol)
        own_row.addWidget(self.own_clear_btn)
        own_col.addLayout(own_row)

        own_widget = QWidget()
        own_widget.setLayout(own_col)
        outer.addWidget(own_widget)

        outer.addWidget(_hairline(vertical=True))

        connects_col = QVBoxLayout()
        connects_col.setContentsMargins(0, 0, 0, 0)
        connects_col.setSpacing(5)
        self.connects_label = QLabel()
        self.connects_label.setProperty("role", "field-label")
        connects_col.addWidget(self.connects_label)

        self.chip_layout = QHBoxLayout()
        self.chip_layout.setContentsMargins(0, 0, 0, 0)
        self.chip_layout.setSpacing(5)
        self.add_btn = QPushButton(tr("BUTTON_ADD_SYMBOL"))
        self.add_btn.setProperty("chip", "tag-add")
        self.add_btn.clicked.connect(lambda: self._open_popover(multi=True))
        self.chip_layout.addWidget(self.add_btn)
        self.chip_layout.addStretch(1)
        connects_col.addLayout(self.chip_layout)

        connects_widget = QWidget()
        connects_widget.setLayout(connects_col)
        outer.addWidget(connects_widget, 1)

        self._refresh()

    def _open_popover(self, multi):
        popup = _ConnectionSymbolPopover(self, multi)
        anchor = self.add_btn if multi else self.own_btn
        pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        popup.move(pos)
        popup.show()

    def _set_own_symbol(self, symbol):
        self._own = symbol
        self._refresh()
        self.changed.emit()

    def _clear_own_symbol(self):
        if self._own is not None:
            self._own = None
            self._refresh()
            self.changed.emit()

    def _add_connection(self, symbol):
        if symbol in self._connections or len(self._connections) >= self.MAX_CONNECTIONS:
            return False
        self._connections.append(symbol)
        self._refresh()
        self.changed.emit()
        return True

    def _remove_connection(self, symbol):
        if symbol in self._connections:
            self._connections.remove(symbol)
            self._refresh()
            self.changed.emit()

    def _refresh(self):
        if self._own:
            self.own_btn.setIcon(QIcon(str(overlay_dir / 'svg' / f"connection_{self._own}.svg")))
            self.own_btn.setText(connection_symbol_label(self._own))
        else:
            self.own_btn.setIcon(QIcon())
            self.own_btn.setText(tr("OPTION_NONE"))
        self.own_clear_btn.setVisible(bool(self._own))

        self.connects_label.setText(
            f"{tr('LABEL_CONNECTS_TO')} · {len(self._connections)}/{self.MAX_CONNECTIONS}"
        )

        for i in reversed(range(self.chip_layout.count())):
            item = self.chip_layout.itemAt(i)
            widget = item.widget()
            if widget is not None and widget is not self.add_btn:
                widget.setParent(None)
        insert_at = self.chip_layout.indexOf(self.add_btn)
        for symbol in self._connections:
            chip = QPushButton(f"{connection_symbol_label(symbol)} ×")
            chip.setIcon(QIcon(str(overlay_dir / 'svg' / f"connection_{symbol}.svg")))
            chip.setProperty("chip", "tag")
            chip.clicked.connect(lambda _, s=symbol: self._remove_connection(s))
            self.chip_layout.insertWidget(insert_at, chip)
            insert_at += 1
        self.add_btn.setVisible(len(self._connections) < self.MAX_CONNECTIONS)

    def get_connection(self):
        return self._own

    def set_connection(self, value):
        self._own = value if value and value != 'None' else None
        self._refresh()

    def get_connections(self):
        return list(self._connections) if self._connections else None

    def set_connections(self, value):
        if not value:
            connections = []
        elif isinstance(value, list):
            connections = [str(v) for v in value if v and str(v) != 'None']
        else:
            connections = [v.strip() for v in str(value).split(',') if v.strip()]
        self._connections = connections[:self.MAX_CONNECTIONS]
        self._refresh()
