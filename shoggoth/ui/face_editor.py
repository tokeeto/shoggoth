"""
FaceEditor base class for Shoggoth face editors
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QComboBox,
    QLabel, QCompleter, QCheckBox, QToolButton, QSpinBox
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPixmap, QFont, QFontDatabase

from shoggoth.ui.editor_widgets import NoScrollComboBox, ALL_CARD_TYPES, FULLART_CARD_TYPES, CHAPTER2_CARD_TYPES
from shoggoth.ui.field_widgets import (
    LabeledLineEdit, LabeledTraitEdit, LabeledTextEdit, ClassSelectorWidget, CompactLabeledField,
    UniqueNameField
)
from shoggoth.ui.card_widgets import IllustrationWidget
from shoggoth.ui.compact_widgets import (
    Band, Stepper, PerStepper, IconStatField, IconCountField, NumbersPanel, TagChipsField, SegmentedToggle
)
from shoggoth.files import overlay_dir, font_dir
from shoggoth.i18n import tr
import shoggoth

_flavor_font_family = None


def _load_flavor_font():
    """Register the Arno Pro italic face the renderer actually uses for flavor text
    (see the asset pack's "flavor_text_format": "...<i>{value}</i>") so the editor field
    previews it in roughly the same cursive-leaning style as the printed card."""
    global _flavor_font_family
    if _flavor_font_family is not None:
        return _flavor_font_family

    path = font_dir / "Arno Pro" / "arnopro_italic.otf"
    families = []
    if path.exists():
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)

    _flavor_font_family = families[0] if families else QFont().defaultFamily()
    return _flavor_font_family


class FaceEditor(QWidget):
    """Base class for all face editors"""

    # Signal emitted when type changes and editor should be swapped
    type_changed = Signal(object)  # Emits the face object

    # Fields that carry translatable prose content
    TRANSLATABLE_FIELDS = frozenset({'name', 'subtitle', 'text', 'flavor_text', 'traits', 'label'})

    def __init__(self, face, parent=None):
        super().__init__(parent)
        self.face = face
        self.fields = {}
        self.updating = False  # Prevent recursive updates
        self.field_containers = {}  # field_name -> outer container widget
        self.current_band = None  # Band that add_* helpers currently append into (None = main_layout)

        # Main layout
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        # Always add type selector first
        self.add_type_selector()

        # Then setup custom fields
        self.setup_ui()

        # Load data
        self.load_data()

    def add_type_selector(self):
        """Add type combobox - shown in all editors"""
        type_layout = QVBoxLayout()
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.setSpacing(4)
        type_label = QLabel(tr("FIELD_TYPE").upper())
        type_label.setProperty("role", "field-label")

        self.type_combo = NoScrollComboBox()
        self.type_combo.setFixedWidth(200)
        self.type_combo.setEditable(True)
        self.type_combo.setInsertPolicy(QComboBox.NoInsert)
        self.type_combo.addItems(ALL_CARD_TYPES)
        self.type_combo.addItem("")
        self.type_combo.addItem('-- ' + tr("FULLART_VARIANTS") + ' --')
        self.type_combo.addItems(FULLART_CARD_TYPES)
        self.type_combo.addItem("")
        self.type_combo.addItem('-- ' + tr("CH2_PREVIEW_VARIANTS") + ' --')
        self.type_combo.addItems(CHAPTER2_CARD_TYPES)

        # Add autocomplete
        completer = QCompleter(ALL_CARD_TYPES + FULLART_CARD_TYPES + CHAPTER2_CARD_TYPES)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.type_combo.setCompleter(completer)

        # Connect to handle changes - use signals that fire on "commit" not every keystroke
        # activated: fires when user selects from dropdown
        # lineEdit().editingFinished: fires on Enter or focus loss
        self.type_combo.activated.connect(self._on_type_committed)
        self.type_combo.lineEdit().editingFinished.connect(self._on_type_committed)

        self.fields['type'] = self.type_combo

        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_combo)
        type_widget = QWidget()
        type_widget.setProperty("visible_in_translation_project", False)
        type_widget.setLayout(type_layout)
        self.main_layout.addWidget(type_widget)

    def _on_type_committed(self, _=None):
        """Handle type field commit (Enter, focus loss, or dropdown selection)"""
        if self.updating:
            return

        value = self.type_combo.currentText()
        old_type = self.face.get('type')
        if value and value != old_type:
            self.face.set('type', value)
            # Emit signal to trigger editor swap
            self.type_changed.emit(self.face)

    def setup_ui(self):
        """Override in subclasses to add custom fields"""
        pass

    def start_band(self, title, hint=None, collapsible=False):
        """Open a new Band section; subsequent add_* helper calls append into it until the
        next start_band() call (or fall back to main_layout if none was ever opened)."""
        band = Band(title, hint=hint, collapsible=collapsible)
        self.main_layout.addWidget(band)
        self.current_band = band
        return band

    def _target_layout(self):
        """The layout add_* helpers should append into: the open band's content, or main_layout."""
        return self.current_band.content_layout if self.current_band else self.main_layout

    # Cost's "-" at 0 drops to this sentinel: "cannot be played/paid for by normal means"
    # (as opposed to "0", which is free-but-payable). Enemy attack/health/evade use
    # IconStatField instead of a Stepper — their own "-" option stores the "<dash>"
    # icon-font glyph (rich_text.py) directly, the "no value printed" dash used on enemy
    # stat lines. See renderer/defaults for the same literal strings.
    STEPPER_FLOOR_VALUES = {'cost': '---'}

    # Fields printed as "X per investigator" on real cards — these get a PerStepper (a
    # Stepper plus a toggle button appending/removing the literal "<per>" tag) instead of
    # a plain Stepper. (Enemy attack/health/evade are printed "per investigator" too, but
    # use IconStatField, which bundles the same toggle itself.)
    PER_TOGGLE_FIELDS = {'clues', 'doom'}

    def _make_stepper(self, field_name):
        floor_value = self.STEPPER_FLOOR_VALUES.get(field_name)
        cls = PerStepper if field_name in self.PER_TOGGLE_FIELDS else Stepper
        stepper = cls(floor_value=floor_value)
        stepper.textChanged.connect(lambda _, f=field_name: self.on_field_changed(f))
        self.fields[field_name] = stepper
        return stepper

    def _make_icon_field(self, icon_name, field_name, width=40):
        """A small [icon][plain text field] cluster — no stepper +/-, just the value,
        with an overlay icon (e.g. damage/horror) identifying what it is."""
        cluster = QHBoxLayout()
        cluster.setContentsMargins(0, 0, 0, 0)
        cluster.setSpacing(4)

        icon_label = QLabel()
        icon_path = overlay_dir / f"{icon_name}.png"
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path)).scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(pixmap)
        icon_label.setFixedSize(16, 16)
        cluster.addWidget(icon_label)

        field = QLineEdit()
        field.setFixedWidth(width)
        field.textChanged.connect(lambda: self.on_field_changed(field_name))
        self.fields[field_name] = field
        cluster.addWidget(field)

        widget = QWidget()
        widget.setLayout(cluster)
        return widget

    def add_icon_field_pair(self, icon1, field1, icon2, field2, width=40):
        """Two icon+field clusters side by side — build with _make_icon_field() and pass
        the result as a pre-built widget item into add_numbers_panel()."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self._make_icon_field(icon1, field1, width))
        row.addWidget(self._make_icon_field(icon2, field2, width))
        widget = QWidget()
        widget.setLayout(row)
        return widget

    def _make_icon_stat_field(self, icon_path, field_name):
        """An [icon][-/X/0-9 dropdown][per-investigator toggle] cluster — see IconStatField."""
        widget = IconStatField(icon_path)
        widget.textChanged.connect(lambda _, f=field_name: self.on_field_changed(f))
        self.fields[field_name] = widget
        return widget

    def add_icon_stat_row(self, *icon_field_pairs):
        """Row of icon+dropdown+toggle stat clusters (e.g. enemy Attack/Health/Evade) —
        build with _make_icon_stat_field() and pass the result as a pre-built widget item
        into add_numbers_panel(). `icon_field_pairs` is (icon_path, field_name) tuples."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        for icon_path, field_name in icon_field_pairs:
            row.addWidget(self._make_icon_stat_field(icon_path, field_name))
        widget = QWidget()
        widget.setLayout(row)
        return widget

    def _make_icon_count_field(self, icon_path, field_name, max_count=5):
        """An [icon][0-max_count dropdown] cluster — see IconCountField."""
        widget = IconCountField(icon_path, max_count=max_count)
        widget.textChanged.connect(lambda _, f=field_name: self.on_field_changed(f))
        self.fields[field_name] = widget
        return widget

    def add_icon_count_row(self, *icon_field_pairs):
        """Row of icon+count-dropdown clusters (e.g. enemy Damage/Horror icon counts) —
        build with _make_icon_count_field() and pass the result as a pre-built widget item
        into add_numbers_panel(). `icon_field_pairs` is (icon_path, field_name) tuples."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        for icon_path, field_name in icon_field_pairs:
            row.addWidget(self._make_icon_count_field(icon_path, field_name))
        widget = QWidget()
        widget.setLayout(row)
        return widget

    def add_numbers_panel(self, items):
        """Bordered stat mini-panel. `items` = [(label, item), ...] where `item` is:
          - a field name (str) -> one Stepper
          - a list/tuple of field names -> a row of Steppers sharing one group label
            (e.g. Willpower/Intellect/Combat/Agility, or a Health/Sanity pair)
          - a QWidget -> used as-is (e.g. an already-built IconsWidget/SlotChipsField)
        """
        panel = NumbersPanel()
        for label, item in items:
            if isinstance(item, QWidget):
                panel.add_group(label, item)
            elif isinstance(item, (list, tuple)):
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(4)
                for field_name in item:
                    row.addWidget(self._make_stepper(field_name))
                row_widget = QWidget()
                row_widget.setLayout(row)
                panel.add_group(label, row_widget)
            else:
                panel.add_group(label, self._make_stepper(item))
        self._target_layout().addWidget(panel)
        return panel

    def load_data(self):
        """Load data from face into fields"""
        self.updating = True
        for field_name, widget in self.fields.items():
            if field_name in self.face.data:
                # Explicitly set — clear any placeholder, then show the value
                self._set_widget_placeholder(field_name, '')
                value = self.face.get(field_name, '')
                self.set_widget_value(widget, value)
            elif self._has_floating_label(field_name):
                # Inherited from fallback and widget supports placeholder text —
                # set placeholder first (prevents animation fight), then clear value
                fallback = self.face.get(field_name, '')
                self._set_widget_placeholder(field_name, self._format_placeholder(field_name, fallback))
                self.set_widget_value(widget, '')
            else:
                # Comboboxes and other non-floating-label widgets: display fallback normally
                value = self.face.get(field_name, '')
                self.set_widget_value(widget, value)
        self.updating = False

    def _has_floating_label(self, field_name):
        """Return True if the field's widget has a compact-label wrapper that supports
        showing an inherited/fallback value as placeholder text. Most fields register
        their raw input (parent is the wrapper); a few (UniqueNameField) register the
        wrapper itself, since the wrapper needs to see the full raw value."""
        widget = self.fields.get(field_name)
        if widget is None:
            return False
        return isinstance(widget, CompactLabeledField) or isinstance(widget.parent(), CompactLabeledField)

    def _format_placeholder(self, field_name, value):
        """Format a fallback value as placeholder text"""
        if value is None or value == '':
            return ''
        if field_name in self.LIST_FIELDS and isinstance(value, list):
            return ', '.join(str(v) for v in value)
        return str(value)

    def _set_widget_placeholder(self, field_name, text):
        """Set placeholder text on the floating-label widget for a field"""
        widget = self.fields.get(field_name)
        if widget is None:
            return
        if isinstance(widget, CompactLabeledField):
            widget.setPlaceholderText(text)
            return
        # Walk up to find the FloatingLabel wrapper (the direct parent of the inner input)
        parent = widget.parent() if widget else None
        if isinstance(parent, CompactLabeledField):
            parent.setPlaceholderText(text)
            return
        # Fallback for plain widgets without floating labels
        if isinstance(widget, (QLineEdit, QTextEdit)):
            widget.setPlaceholderText(text)

    def set_widget_value(self, widget, value):
        """Set widget value based on type"""
        if isinstance(widget, ClassSelectorWidget):
            widget.set_classes(value)
        elif isinstance(widget, (Stepper, PerStepper, IconStatField, IconCountField, TagChipsField, UniqueNameField)):
            widget.setText(str(value) if value else '')
        elif isinstance(widget, SegmentedToggle):
            widget.set_current_value(value)
        elif isinstance(widget, QLineEdit):
            if isinstance(value, list):
                widget.setText(', '.join(str(v) for v in value))
            else:
                widget.setText(str(value) if value else '')
        elif isinstance(widget, QTextEdit):
            widget.setPlainText(str(value) if value else '')
        elif isinstance(widget, QComboBox):
            widget.setCurrentText('' if value in (None, '') else str(value))
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))

    def get_widget_value(self, widget):
        """Get widget value based on type"""
        if isinstance(widget, ClassSelectorWidget):
            return widget.get_classes()
        elif isinstance(widget, (Stepper, PerStepper, IconStatField, IconCountField, TagChipsField, UniqueNameField)):
            return widget.text()
        elif isinstance(widget, SegmentedToggle):
            return widget.current_value()
        elif isinstance(widget, QLineEdit):
            return widget.text()
        elif isinstance(widget, QTextEdit):
            return widget.toPlainText()
        elif isinstance(widget, QComboBox):
            return widget.currentData() or widget.currentText()
        elif isinstance(widget, QCheckBox):
            return widget.isChecked()
        return ''

    # Fields that require type conversion
    INTEGER_FIELDS = {}
    FLOAT_FIELDS = {'illustration_scale', 'illustration_pan_x', 'illustration_pan_y'}
    LIST_FIELDS = set()  # Fields stored as lists but displayed as comma-separated
    # Fields stored as True when set, and removed (None) rather than False when unset
    BOOL_FIELDS = {'illustration_mirror'}

    def on_field_changed(self, field_name):
        """Handle field change"""
        if self.updating:
            return

        widget = self.fields.get(field_name)
        if not widget:
            return

        value = self.get_widget_value(widget)

        if field_name in self.BOOL_FIELDS:
            self.face.set(field_name, True if value else None)
            parent = self.parent()
            while parent:
                if hasattr(parent, 'data_changed'):
                    parent.data_changed.emit()
                    break
                parent = parent.parent()
            return

        # Convert value to appropriate type
        if value is not None and value != '' and value != []:
            if field_name in self.INTEGER_FIELDS:
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    return  # Invalid integer, don't update
            elif field_name in self.FLOAT_FIELDS:
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    return  # Invalid float, don't update
            elif field_name in self.LIST_FIELDS and isinstance(value, str):
                # Convert comma-separated string to list (already a list for ClassSelectorWidget)
                value = [v.strip() for v in value.split(',') if v.strip()]
            self.face.set(field_name, value)
            if self._has_floating_label(field_name):
                self._set_widget_placeholder(field_name, '')
        else:
            self.face.set(field_name, None)
            fallback = self.face.get(field_name, '')
            if self._has_floating_label(field_name):
                self._set_widget_placeholder(field_name, self._format_placeholder(field_name, fallback))
            else:
                # Widgets without placeholder support (Stepper, combo boxes) just show the
                # resolved fallback value directly, same as the initial load_data() does.
                # Guard against the widget's own change signal re-entering on_field_changed.
                self.updating = True
                self.set_widget_value(widget, fallback)
                self.updating = False

        # Emit data_changed signal on parent CardEditor if it exists
        parent = self.parent()
        while parent:
            if hasattr(parent, 'data_changed'):
                parent.data_changed.emit()
                break
            parent = parent.parent()

    def add_labeled_line(self, label, field_name):
        """Helper to add a labeled line edit"""
        widget = LabeledLineEdit(label)
        widget.input.textChanged.connect(lambda: self.on_field_changed(field_name))
        self.fields[field_name] = widget.input
        self.field_containers[field_name] = widget
        self._target_layout().addWidget(widget)
        return widget

    def _build_name_field(self, field_name):
        """Name field with the unique-toggle star — see UniqueNameField. Registered as
        the wrapper itself (not .input) since it owns the raw "<unique>..." value."""
        widget = UniqueNameField(tr("FIELD_NAME"))
        widget.textChanged.connect(lambda: self.on_field_changed(field_name))
        self.fields[field_name] = widget
        self.field_containers[field_name] = widget
        return widget

    def add_name_field(self, field_name="name"):
        """Standalone Name field (with the unique-toggle star) as its own row."""
        widget = self._build_name_field(field_name)
        self._target_layout().addWidget(widget)
        return widget

    def add_identity_row(self, name_field="name", subtitle_field="subtitle", trait_field="traits"):
        """Name + Subtitle + Traits sharing one row (1.7 : 1.2 : 1.4 width ratio, per the
        1a mockup) instead of each taking a full-width row of its own."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        name_widget = self._build_name_field(name_field)
        row.addWidget(name_widget, 17)

        subtitle_widget = LabeledLineEdit(tr("FIELD_SUBTITLE"))
        subtitle_widget.input.textChanged.connect(lambda: self.on_field_changed(subtitle_field))
        self.fields[subtitle_field] = subtitle_widget.input
        self.field_containers[subtitle_field] = subtitle_widget
        row.addWidget(subtitle_widget, 12)

        trait_widget = LabeledTraitEdit(tr("FIELD_TRAITS"))
        trait_widget.input.textChanged.connect(lambda: self.on_field_changed(trait_field))
        self.fields[trait_field] = trait_widget.input
        self.field_containers[trait_field] = trait_widget
        row.addWidget(trait_widget, 14)

        row_widget = QWidget()
        row_widget.setLayout(row)
        self._target_layout().addWidget(row_widget)
        return row_widget

    def _victory_format_template(self):
        """Return the "victory format" template for the current card language.

        Falls back to the English default if the card language has no
        translation for this key, or no card renderer is available yet.
        """
        renderer = getattr(shoggoth.app, 'card_renderer', None)
        fmt = renderer.translations.get('victory format') if renderer else None
        return fmt or "Victory {input}."

    def _handle_victory_autoformat(self, field_name):
        """Auto-expand a bare number typed into the Victory field.

        "2" becomes "Victory 2." (or the localized equivalent) with the
        cursor placed right after the number, before the trailing dot.
        Left untouched if the field contains any letters, so custom values
        like "Vengeance 3." remain editable as free text.
        """
        if not self.updating:
            widget = self.fields.get(field_name)
            text = widget.text() if widget else ''
            if text and text.isdigit():
                fmt = self._victory_format_template()
                prefix_len = fmt.find('{input}')
                if prefix_len == -1:
                    fmt = "Victory {input}."
                    prefix_len = fmt.find('{input}')
                widget.blockSignals(True)
                widget.setText(fmt.format(input=text))
                widget.blockSignals(False)
                widget.setCursorPosition(prefix_len + len(text))
        self.on_field_changed(field_name)

    def add_victory_field(self, label=None, field_name="victory"):
        """Helper to add the Victory field with bare-number auto-formatting"""
        if label is None:
            label = tr("FIELD_VICTORY")
        widget = LabeledLineEdit(label)
        widget.input.textChanged.connect(lambda: self._handle_victory_autoformat(field_name))
        self.fields[field_name] = widget.input
        self.field_containers[field_name] = widget
        self._target_layout().addWidget(widget)
        return widget

    def add_rules_text_row(self, include_flavor=True, include_victory=True,
                            text_field="text", flavor_field="flavor_text", victory_field="victory",
                            use_arkham=True):
        """Rules text (full width, the standard ~5-line arkham editor height) with Flavor
        (~2 lines, 75% width) and Victory (single line, 25% width) stacked below it side
        by side, instead of either being its own full-width row."""
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        text_widget = LabeledTextEdit(tr("FIELD_TEXT"), use_arkham_editor=use_arkham)
        text_widget.input.textChanged.connect(lambda: self.on_field_changed(text_field))
        self.fields[text_field] = text_widget.input
        self.field_containers[text_field] = text_widget
        outer.addWidget(text_widget)

        if include_flavor or include_victory:
            bottom_row = QHBoxLayout()
            bottom_row.setContentsMargins(0, 0, 0, 0)
            bottom_row.setSpacing(12)

            if include_flavor:
                flavor_widget = LabeledTextEdit(tr("FIELD_FLAVOR"))
                flavor_widget.input.setFixedHeight(58)  # ~2 lines
                flavor_font = QFont(_load_flavor_font())
                # Some systems already have "Arno Pro" installed (multiple styles under
                # one family name) — without this, QFont silently resolves to whatever
                # style is default (usually Regular) instead of the italic face we want.
                flavor_font.setItalic(True)
                flavor_font.setPointSize(12)
                flavor_widget.input.setFont(flavor_font)
                flavor_widget.input.textChanged.connect(lambda: self.on_field_changed(flavor_field))
                self.fields[flavor_field] = flavor_widget.input
                self.field_containers[flavor_field] = flavor_widget
                bottom_row.addWidget(flavor_widget, 3, Qt.AlignTop)  # 75%

            if include_victory:
                victory_widget = LabeledLineEdit(tr("FIELD_VICTORY"))
                victory_widget.input.textChanged.connect(lambda: self._handle_victory_autoformat(victory_field))
                self.fields[victory_field] = victory_widget.input
                self.field_containers[victory_field] = victory_widget
                bottom_row.addWidget(victory_widget, 1, Qt.AlignTop)  # 25%

            bottom_widget = QWidget()
            bottom_widget.setLayout(bottom_row)
            outer.addWidget(bottom_widget)

        row_widget = QWidget()
        row_widget.setLayout(outer)
        self._target_layout().addWidget(row_widget)
        return row_widget

    def add_trait_field(self, label=None, field_name="traits"):
        """Helper to add a trait field with autocomplete"""
        if label is None:
            label = tr("FIELD_TRAITS")
        widget = LabeledTraitEdit(label)
        widget.input.textChanged.connect(lambda: self.on_field_changed(field_name))
        self.fields[field_name] = widget.input
        self.field_containers[field_name] = widget
        self._target_layout().addWidget(widget)
        return widget

    def add_class_field(self, label=None, field_name="classes"):
        """Helper to add a class selector widget"""
        widget = ClassSelectorWidget()
        widget.classesChanged.connect(lambda: self.on_field_changed(field_name))
        self.fields[field_name] = widget
        self.field_containers[field_name] = widget
        self._target_layout().addWidget(widget)
        return widget

    def add_class_and_level_row(self, level_labels, level_values, level_field="level"):
        """Classes (flexible width) + a Level segmented button row sharing one line."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        classes_widget = ClassSelectorWidget()
        classes_widget.classesChanged.connect(lambda: self.on_field_changed('classes'))
        self.fields['classes'] = classes_widget
        self.field_containers['classes'] = classes_widget
        row.addWidget(classes_widget, 1)

        level_col = QWidget()
        level_layout = QVBoxLayout(level_col)
        level_layout.setContentsMargins(0, 0, 0, 0)
        level_layout.setSpacing(4)
        level_label = QLabel(tr("FIELD_LEVEL").upper())
        level_label.setProperty("role", "field-label")
        level_layout.addWidget(level_label)

        level_toggle = SegmentedToggle(level_labels, values=level_values)
        level_toggle.valueChanged.connect(lambda: self.on_field_changed(level_field))
        self.fields[level_field] = level_toggle
        level_layout.addWidget(level_toggle)
        row.addWidget(level_col)

        row_widget = QWidget()
        row_widget.setLayout(row)
        self._target_layout().addWidget(row_widget)
        return row_widget

    def add_labeled_text(self, label, field_name, use_arkham=False):
        """Helper to add a labeled text edit"""
        widget = LabeledTextEdit(label, use_arkham_editor=use_arkham)
        widget.input.textChanged.connect(lambda: self.on_field_changed(field_name))
        self.fields[field_name] = widget.input
        self.field_containers[field_name] = widget
        self._target_layout().addWidget(widget)
        return widget

    def add_footer_row(self):
        """Add the "additional text fields" fold (call inside a "Print & credits" band —
        this does not open one itself)."""
        self.add_extra_fields_section()

    def add_token_area_widget(self):
        """Enable/height/title controls for a bottom-of-card token/tracking box (Chaos,
        Story). Opens its own band. Wires straight to self.on_token_area_changed —
        subclasses implement that to write out their own region field names and to
        shrink whichever other region the box eats into; use load_token_area() in
        load_data() to populate these widgets back from face data."""
        self.start_band(tr("GROUP_TOKEN_AREA"))
        self.token_area_enabled = QCheckBox(tr("FIELD_TOKEN_AREA_ENABLED"))
        self.token_area_enabled.toggled.connect(self.on_token_area_changed)
        self._target_layout().addWidget(self.token_area_enabled)

        fields_widget = QWidget()
        fields_layout = QHBoxLayout()
        fields_layout.setContentsMargins(0, 0, 0, 0)

        fields_layout.addWidget(QLabel(tr("FIELD_TOKEN_AREA_HEIGHT")))
        self.token_area_height = QSpinBox()
        self.token_area_height.setRange(10, 1000)
        self.token_area_height.setValue(300)
        self.token_area_height.valueChanged.connect(self.on_token_area_changed)
        fields_layout.addWidget(self.token_area_height)

        fields_layout.addWidget(QLabel(tr("FIELD_TOKEN_AREA_TITLE")))
        self.token_area_title = QLineEdit()
        self.token_area_title.textChanged.connect(self.on_token_area_changed)
        fields_layout.addWidget(self.token_area_title)

        fields_widget.setLayout(fields_layout)
        self._target_layout().addWidget(fields_widget)

    def load_token_area(self, region_field, title_field):
        """Populate add_token_area_widget()'s widgets — read raw data to avoid
        fallback confusion, same as the rest of load_data()."""
        region = self.face.data.get(region_field)
        self.token_area_enabled.setChecked(bool(region))
        if region:
            self.token_area_height.setValue(region.get('height', 100))
        self.token_area_title.setText(self.face.data.get(title_field, '') or '')

    def extra_text_fields(self):
        """ Text fields that render on this face (a '<field>_region' resolves)
            but have no dedicated widget in this editor: user-defined fields
            plus any stock text field this editor doesn't expose.
        """
        from shoggoth.renderer import DEFAULT_TEXT_FIELDS, discovered_text_fields
        candidates = list(DEFAULT_TEXT_FIELDS) + sorted(discovered_text_fields(self.face))
        return [
            field for field in candidates
            if field not in self.fields and self.face.get(f'{field}_region')
        ]

    def add_extra_fields_section(self):
        """Add a collapsed fold holding Copyright plus extra_text_fields(), one line edit
        each. Copyright lives here (rather than as its own always-visible row) since it's
        set-once-and-forget for most cards."""
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)

        toggle = QToolButton()
        toggle.setText(tr("SECTION_EXTRA_TEXT_FIELDS"))
        toggle.setCheckable(True)
        toggle.setArrowType(Qt.RightArrow)
        toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toggle.setAutoRaise(True)
        section_layout.addWidget(toggle)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        copyright_widget = LabeledLineEdit(tr("FIELD_COPYRIGHT"))
        copyright_widget.input.textChanged.connect(lambda: self.on_field_changed('copyright'))
        self.fields['copyright'] = copyright_widget.input
        self.field_containers['copyright'] = copyright_widget
        content_layout.addWidget(copyright_widget)

        # Computed after registering 'copyright' above so extra_text_fields()'s
        # "field not in self.fields" check excludes it from this list too.
        extra_fields = self.extra_text_fields()
        for field in extra_fields:
            widget = LabeledLineEdit(field)
            widget.input.textChanged.connect(lambda _, f=field: self.on_field_changed(f))
            self.fields[field] = widget.input
            self.field_containers[field] = widget
            content_layout.addWidget(widget)
        content.setVisible(False)
        section_layout.addWidget(content)

        def on_toggled(checked):
            content.setVisible(checked)
            toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        toggle.toggled.connect(on_toggled)

        self._target_layout().addWidget(section)

    def add_illustration_widget(self):
        """Add illustration widget"""
        illustration = IllustrationWidget(project=self.face.card.project, face=self.face)
        self.illustration_widget = illustration

        # Add fields
        self.fields['illustration'] = illustration.path_input.input
        self.fields['illustration_pan_y'] = illustration.pan_y_input.input
        self.fields['illustration_pan_x'] = illustration.pan_x_input.input
        self.fields['illustration_scale'] = illustration.scale_input.input
        self.fields['illustrator'] = illustration.artist_input.input
        self.fields['illustration_mirror'] = illustration.mirror_checkbox

        # Connect signals
        illustration.path_input.input.textChanged.connect(lambda: self.on_field_changed('illustration'))
        illustration.pan_y_input.input.textChanged.connect(lambda: self.on_field_changed('illustration_pan_y'))
        illustration.pan_x_input.input.textChanged.connect(lambda: self.on_field_changed('illustration_pan_x'))
        illustration.scale_input.input.textChanged.connect(lambda: self.on_field_changed('illustration_scale'))
        illustration.artist_input.input.textChanged.connect(lambda: self.on_field_changed('illustrator'))
        illustration.mirror_checkbox.toggled.connect(lambda: self.on_field_changed('illustration_mirror'))

        self._target_layout().addWidget(illustration)
        return illustration

    def _iter_main_widgets(self):
        """Yield every widget in this editor, including nested field widgets."""
        seen = set()
        for i in range(self.main_layout.count()):
            item = self.main_layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if widget is None:
                continue
            stack = [widget]
            while stack:
                current = stack.pop()
                if current is None or id(current) in seen:
                    continue
                seen.add(id(current))
                yield current
                for child in current.findChildren(QWidget):
                    if id(child) not in seen:
                        stack.append(child)

    def _subtree_has_translatable_field(self, widget, translatable_widgets):
        """Return True if `widget` itself, or any descendant at any depth, is a
        registered translatable field container."""
        if widget in translatable_widgets:
            return True
        return any(child in translatable_widgets for child in widget.findChildren(QWidget))

    def _set_translation_visibility(self, widget, translatable_widgets, field_widgets):
        """Recursively apply translation-mode visibility, pruning at field-leaf or
        fully-non-translatable subtree boundaries.

        A container (band/row wrapper) shared by translatable and non-translatable
        fields must stay visible itself — otherwise hiding it would collaterally hide
        the translatable fields nested inside it — so we only ever explicitly hide a
        registered non-translatable field container, or a subtree that contains no
        translatable field at all. Chrome (labels, hairlines, band headers) inside a
        still-visible mixed container is left untouched rather than independently
        judged, since it isn't a field and has no translatable-ness of its own.
        """
        if widget.property("visible_in_translation_project"):
            widget.setVisible(True)
            return

        if widget in field_widgets:
            widget.setVisible(widget in translatable_widgets)
            return

        if not self._subtree_has_translatable_field(widget, translatable_widgets):
            widget.setVisible(False)
            return

        widget.setVisible(True)
        for child in widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            self._set_translation_visibility(child, translatable_widgets, field_widgets)

    def _apply_translation_widget_state(self, enable_translation_mode):
        """Lock or unlock editor widgets according to translation mode."""
        translatable_widgets = {
            w for name, w in self.field_containers.items()
            if name in self.TRANSLATABLE_FIELDS
        }
        for name, widget in self.fields.items():
            if name in self.TRANSLATABLE_FIELDS:
                translatable_widgets.add(widget)

        if not enable_translation_mode:
            for widget in self._iter_main_widgets():
                widget.setVisible(True)
            return

        field_widgets = set(self.field_containers.values())
        for i in range(self.main_layout.count()):
            item = self.main_layout.itemAt(i)
            widget = item.widget() if item else None
            if widget is not None:
                self._set_translation_visibility(widget, translatable_widgets, field_widgets)

    def enter_translation_mode(self):
        """Lock non-translatable fields while keeping the form visible."""
        self._apply_translation_widget_state(True)

    def exit_translation_mode(self):
        """Restore all fields."""
        self._apply_translation_widget_state(False)
