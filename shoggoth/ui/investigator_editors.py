"""
Investigator card editors for Shoggoth
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QLabel, QPushButton, QFileDialog, QCheckBox
)
from PySide6.QtCore import Qt

from shoggoth.ui.face_editor import FaceEditor
from shoggoth.ui.field_widgets import ClassSelectorWidget, LabeledLineEdit
from shoggoth.ui.text_editor import ArkhamTextEdit
from shoggoth.ui.editor_widgets import NoScrollComboBox
from shoggoth.ui.compact_widgets import PLAYER_CLASSES, SegmentedToggle
from shoggoth.util.shape_alpha import FADE_DISTANCE
from shoggoth.i18n import tr


class InvestigatorEditor(FaceEditor):
    """Editor for investigator cards (front side)"""

    def setup_ui(self):
        self.start_band(tr("BAND_IDENTITY"))
        self.add_identity_row()

        # Classes
        classes_widget = ClassSelectorWidget(default_classes=PLAYER_CLASSES)
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

        # Shape image: drives the render-time distance fade in
        # render_illustration() (renderer/card_renderer.py) - black over the
        # subject, white/transparent elsewhere, same pixel dimensions as the
        # illustration so it stays aligned through the same pan/scale/mirror.
        shape_row = QWidget()
        shape_layout = QHBoxLayout()
        shape_layout.setContentsMargins(0, 0, 0, 0)
        self._shape_input = LabeledLineEdit(tr("FIELD_ILLUSTRATION_SHAPE"))
        self._shape_input.input.textChanged.connect(lambda: self.on_field_changed('illustration_shape'))
        shape_browse_btn = QPushButton(tr("BTN_BROWSE"))
        shape_browse_btn.clicked.connect(self._browse_shape_image)
        self._shape_overflow_checkbox = QCheckBox(tr("FIELD_SHAPE_OVERFLOW"))
        self._shape_overflow_checkbox.toggled.connect(lambda: self.on_field_changed('illustration_shape_overflow'))
        shape_layout.addWidget(self._shape_input, 1)
        shape_layout.addWidget(shape_browse_btn)
        shape_layout.addWidget(self._shape_overflow_checkbox)
        shape_row.setLayout(shape_layout)
        self._target_layout().addWidget(shape_row)
        self.fields['illustration_shape'] = self._shape_input.input
        self.fields['illustration_shape_overflow'] = self._shape_overflow_checkbox

        # Shape fade style: FADE_FLAT mirrors official card art (uniform,
        # subtle); FADE_DISTANCE tends to look better on user-supplied art
        # that doesn't fit the shape cleanly. `None` (unset) means FADE_FLAT.
        fade_row = QWidget()
        fade_layout = QHBoxLayout()
        fade_layout.setContentsMargins(0, 0, 0, 0)
        fade_label = QLabel(tr("FIELD_SHAPE_FADE"))
        fade_label.setProperty("role", "field-label")
        fade_label.setMinimumWidth(80)
        self._fade_toggle = SegmentedToggle(
            [tr("OPTION_FADE_FLAT"), tr("OPTION_FADE_DISTANCE")],
            values=[None, FADE_DISTANCE],
        )
        self._fade_toggle.valueChanged.connect(lambda: self.on_field_changed('illustration_fade_mode'))
        fade_layout.addWidget(fade_label)
        fade_layout.addWidget(self._fade_toggle)
        fade_layout.addStretch()
        fade_row.setLayout(fade_layout)
        self._target_layout().addWidget(fade_row)
        self.fields['illustration_fade_mode'] = self._fade_toggle

        # Mask template dropdown
        mask_row = QWidget()
        mask_layout = QHBoxLayout()
        mask_layout.setContentsMargins(0, 0, 0, 0)
        mask_label = QLabel(tr("FIELD_APPLY_MASK"))
        mask_label.setProperty("role", "field-label")
        mask_label.setMinimumWidth(80)
        self._mask_combo = NoScrollComboBox()
        self._mask_combo.addItem(tr("OPTION_MASK_SHAPED"), userData=None)
        self._mask_combo.addItem(tr("OPTION_MASK_SIMPLE"), userData='simple')
        self._mask_combo.addItem(tr("OPTION_MASK_NONE"), userData='none')
        self._mask_combo.currentIndexChanged.connect(self._on_mask_changed)
        self._class_icon_checkbox = QCheckBox(tr("FIELD_CLASS_ICON"))
        self._class_icon_checkbox.toggled.connect(lambda: self.on_field_changed('illustration_class_icon'))
        mask_layout.addWidget(mask_label)
        mask_layout.addWidget(self._mask_combo)
        mask_layout.addWidget(self._class_icon_checkbox)
        mask_layout.addStretch()
        mask_row.setLayout(mask_layout)
        self._target_layout().addWidget(mask_row)
        self.fields['illustration_class_icon'] = self._class_icon_checkbox

        self.add_footer_row()
        self.main_layout.addStretch()

    def _browse_shape_image(self):
        project = self.face.card.project
        current = self._shape_input.text().strip()
        if current:
            p = Path(current)
            if not p.is_absolute() and project:
                p = project.folder / p
            start_dir = str(p.parent) if p.parent.exists() else str(project.folder) if project else str(Path.home())
        else:
            start_dir = str(project.folder) if project else str(Path.home())

        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("DLG_SELECT_IMAGE"), start_dir, tr("FILTER_IMAGES")
        )
        if file_path:
            self._shape_input.setText(file_path)

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
        # `True` is the old boolean value for "Simple" (pre-dating the
        # Shaped/Simple/None dropdown); `False` and unset both mean "Shaped"
        # (renderer already treated them the same way).
        if value is True or value == 'simple':
            self._mask_combo.setCurrentIndex(1)
        elif value == 'none':
            self._mask_combo.setCurrentIndex(2)
        else:
            self._mask_combo.setCurrentIndex(0)
        self.updating = False


class InvestigatorBackEditor(FaceEditor):
    """Editor for investigator cards (back side) with deck building entries"""

    # Line-height mode of each entry the shipped INVESTIGATOR() template pre-fills
    # (see card.py): Deck Size and Secondary Class Choice are almost always a single
    # short line, Deckbuilding Options/Requirements usually run to a couple of lines,
    # and Restrictions is one line but often left empty entirely.
    DEFAULT_ENTRY_MODES = ['single', 'single', 'multi', 'multi', 'single']

    # Matches a compact_theme-styled QLineEdit's actual rendered height (measured, not
    # derived — QTextEdit has no line-count-based sizeHint of its own to match against).
    SINGLE_LINE_HEIGHT = 34
    MULTI_LINE_HEIGHT = 54  # ~3 lines

    def setup_ui(self):
        self.start_band(tr("BAND_IDENTITY"))
        self.add_identity_row()

        # Classes
        classes_widget = ClassSelectorWidget(default_classes=PLAYER_CLASSES)
        classes_widget.classesChanged.connect(lambda: self.on_field_changed('classes'))
        self.fields['classes'] = classes_widget
        self.field_containers['classes'] = classes_widget
        self._target_layout().addWidget(classes_widget)

        # Deck building entries section
        self._entries_group = self.start_band(tr("GROUP_DECK_BUILDING_OPTIONS"))

        self._entries_layout = QVBoxLayout()
        self._entries_layout.setSpacing(8)
        self._entries_layout.setContentsMargins(0, 0, 0, 0)
        self.entry_widgets = []  # Store (header_input, value_input) pairs
        for mode in self.DEFAULT_ENTRY_MODES:
            self._add_entry_row(mode)
        self._target_layout().addLayout(self._entries_layout)

        self._add_entry_btn = QPushButton(tr("BUTTON_ADD_ENTRY"))
        self._add_entry_btn.setProperty("chip", "tag-add")
        self._add_entry_btn.clicked.connect(lambda: self._add_entry_row('multi'))
        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.addWidget(self._add_entry_btn)
        add_row.addStretch(1)
        add_row_widget = QWidget()
        add_row_widget.setLayout(add_row)
        self._target_layout().addWidget(add_row_widget)

        self.start_band(tr("BAND_RULES_TEXT"))
        self.add_labeled_text(tr("FIELD_FLAVOR"), "flavor_text")

        self.start_band(tr("BAND_PRINT_CREDITS"))
        self.add_illustration_widget()
        self.add_footer_row()
        self.main_layout.addStretch()

    def _add_entry_row(self, mode='multi'):
        """Append one header+value entry row. `mode` is 'single' (one short line,
        header and value side by side at the same compact height) or 'multi' (a
        couple of lines of value text, header top-aligned beside it)."""
        index = len(self.entry_widgets)

        header_input = QLineEdit()
        header_input.setPlaceholderText(tr("PLACEHOLDER_HEADER").format(n=index + 1))
        header_input.textChanged.connect(self.on_entries_changed)

        value_input = ArkhamTextEdit()
        value_input.setPlaceholderText(tr("PLACEHOLDER_VALUE").format(n=index + 1))
        if mode == 'single':
            value_input.setFixedHeight(self.SINGLE_LINE_HEIGHT)
            value_input.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            value_input.setLineWrapMode(ArkhamTextEdit.NoWrap)
        else:
            value_input.setFixedHeight(self.MULTI_LINE_HEIGHT)
        value_input.textChanged.connect(self.on_entries_changed)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(header_input, 1, Qt.AlignTop)  # header: ~1/3 of the row
        row.addWidget(value_input, 2)  # value: ~2/3 of the row
        row_widget = QWidget()
        row_widget.setLayout(row)
        self._entries_layout.addWidget(row_widget)

        self.entry_widgets.append((header_input, value_input))
        return header_input, value_input

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

        # Load entries — grow the row list (as 'multi' rows, matching what the "+"
        # button spawns) if this card carries more entries than we have rows for.
        entries = self.face.get('entries', []) or []
        while len(entries) > len(self.entry_widgets):
            self._add_entry_row('multi')

        for i, (header_input, value_input) in enumerate(self.entry_widgets):
            if i < len(entries) and isinstance(entries[i], list) and len(entries[i]) >= 2:
                header_input.setText(str(entries[i][0]) if entries[i][0] else '')
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
