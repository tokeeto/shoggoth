"""
Card editor widget for Shoggoth using PySide6
"""
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel,
    QScrollArea, QStackedWidget, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Signal

from shoggoth.ui.field_widgets import LabeledLineEdit, FieldWidget
from shoggoth.ui.editor_widgets import NoScrollComboBox
from shoggoth.ui.compact_widgets import Band, SegmentedToggle
from shoggoth.ui import compact_theme
from shoggoth.ui.text_editor import ArkhamTextEdit
from shoggoth.ui.face_editor_factory import get_editor_for_face
from shoggoth.i18n import tr
import shoggoth


class CardEditor(QWidget):
    """Main card editor widget"""

    # Signal emitted when card data changes
    data_changed = Signal()

    def __init__(self, card):
        super().__init__()
        self.card = card
        # Whether front/back editors should be put into translation mode as soon as
        # they're (re)created — set by enter/exit_translation_mode. Needed because the
        # Front/Back/JSON toggle and a face type change both rebuild the face editors
        # from scratch (see create_form_editors/on_type_changed), which would otherwise
        # lose translation-mode state and show every field again.
        self._translation_active = False

        # Main layout with scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout()

        self.translation_notice = QLabel(tr("TRANSLATION_MODE_NOTE"))
        self.translation_notice.setVisible(False)
        self.translation_notice.setStyleSheet(
            "QLabel { color: #7a5b14; background: #fff4cc; border: 1px solid #d9c27a; "
            "padding: 6px 10px; border-radius: 4px; font-weight: 600; }"
        )
        layout.addWidget(self.translation_notice)

        self.name_input = LabeledLineEdit(tr("FIELD_NAME"))
        layout.addWidget(self.name_input)

        # Basic info (collapsible band, collapsed by default — rarely touched)
        self.basic_info_band = Band(tr("BAND_BASIC_INFO"), collapsible=True)

        self.copyright_input = LabeledLineEdit(tr("FIELD_COPYRIGHT"))
        self.basic_info_band.content_layout.addWidget(self.copyright_input)

        numbers_row = QHBoxLayout()
        numbers_row.setContentsMargins(0, 0, 0, 0)
        self.amount_input = LabeledLineEdit(tr("FIELD_AMOUNT_IN_SET"))
        self.collection_input = LabeledLineEdit(tr("FIELD_COLLECTION_NUM"))
        self.encounter_input = LabeledLineEdit(tr("FIELD_ENCOUNTER_SET_NUM"))
        numbers_row.addWidget(self.amount_input)
        numbers_row.addWidget(self.collection_input)
        numbers_row.addWidget(self.encounter_input)
        self.basic_info_band.content_layout.addLayout(numbers_row)

        # Automatic enumeration override
        enumerated_row = QHBoxLayout()
        enumerated_row.setContentsMargins(0, 0, 0, 0)
        enumerated_row.addWidget(QLabel(tr("FIELD_ENUMERATED")))
        self.enumerated_combo = NoScrollComboBox()
        self.enumerated_combo.addItem(tr("ENUM_MODE_DEFAULT"), '')
        self.enumerated_combo.addItem(tr("ENUM_MODE_IGNORED"), 'ignored')
        self.enumerated_combo.addItem(tr("ENUM_MODE_MANUAL"), 'manual')
        enumerated_row.addWidget(self.enumerated_combo, 1)
        self.basic_info_band.content_layout.addLayout(enumerated_row)

        self.investigator_input = LabeledLineEdit(tr("FIELD_INVESTIGATOR_LINK"))
        self.basic_info_band.content_layout.addWidget(self.investigator_input)

        self.id_input = LabeledLineEdit(tr("ID"))
        self.id_input.input.setReadOnly(True)
        self.basic_info_band.content_layout.addWidget(self.id_input)

        layout.addWidget(self.basic_info_band)

        # Header row: Front / Back / {} Json — one mutually-exclusive sliding toggle
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        self.view_toggle = SegmentedToggle(
            [tr("TAB_FRONT"), tr("TAB_BACK"), tr("TAB_JSON")],
            values=['front', 'back', 'json'],
        )
        self.view_toggle.valueChanged.connect(self._on_view_toggle_changed)
        header_row.addWidget(self.view_toggle)
        header_row.addStretch()
        header_widget = QWidget()
        header_widget.setLayout(header_row)
        layout.addWidget(header_widget)

        # Container for face editors (stacked front/back) or JSON editor. Expanding +
        # stretch=1 so it alone absorbs any leftover scroll-area height — without this,
        # Qt spreads surplus space evenly across every top-level Preferred-policy widget
        # in `layout` (name/basic-info/header included), which is harmless when the form
        # is tall enough to already fill the viewport but visibly shuffles everything
        # around for the comparatively short JSON view.
        self.editor_container = QWidget()
        self.editor_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.editor_layout = QVBoxLayout()
        self.editor_container.setLayout(self.editor_layout)
        layout.addWidget(self.editor_container, 1)

        # Track whether showing JSON
        self.showing_json = False
        self.face_stack = None
        self.front_editor = None
        self.back_editor = None

        # Create initial editors (form view)
        self.create_form_editors()

        content.setLayout(layout)
        scroll.setWidget(content)

        # Main widget layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)
        self.setStyleSheet(compact_theme.EDITOR_QSS)

        # Setup card field bindings
        self.fields = []
        self.setup_card_fields()
        self.load_card()

    def create_form_editors(self):
        """Create the stacked front/back face editors"""
        # Clear container
        while self.editor_layout.count():
            item = self.editor_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.face_stack = QStackedWidget()
        self.front_editor = None
        self.back_editor = None
        self.create_front_editor()
        self.create_back_editor()
        self.editor_layout.addWidget(self.face_stack)
        self._show_face(self.view_toggle.current_value())

    def create_json_editor(self):
        """Create the JSON editor for entire card.

        The title/info text sit in a compact (never-stretches, see Band's docstring)
        header band, but the editor itself is added straight to editor_layout with a
        stretch factor — it's the main element here, so it should fill whatever space
        the (already-Expanding, see __init__) editor_container is given, not be clipped
        to its own small sizeHint the way Band's fixed-height content would clip it.
        """
        # Clear container
        while self.editor_layout.count():
            item = self.editor_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.face_stack = None

        # Header: title + info text (compact, fixed height)
        json_group = Band(tr("CARD_DATA_JSON"))
        info = QLabel(tr("HELP_EDIT_CARD_JSON"))
        info.setWordWrap(True)
        json_group.content_layout.addWidget(info)
        self.editor_layout.addWidget(json_group)

        # JSON editor — the main element, expands to fill the rest of the pane
        self.json_editor = ArkhamTextEdit(monospace=True)
        self.json_editor.textChanged.connect(self.on_json_changed)
        self.editor_layout.addWidget(self.json_editor, 1)

        # Status
        self.json_status = QLabel("")
        self.editor_layout.addWidget(self.json_status)

        # Buttons
        button_row = QHBoxLayout()
        format_btn = QPushButton(tr("BTN_FORMAT_JSON"))
        format_btn.clicked.connect(self.format_json)
        button_row.addWidget(format_btn)

        validate_btn = QPushButton(tr("BTN_VALIDATE"))
        validate_btn.clicked.connect(self.validate_json)
        button_row.addWidget(validate_btn)

        button_row.addStretch()
        button_widget = QWidget()
        button_widget.setLayout(button_row)
        self.editor_layout.addWidget(button_widget)

        # Load current card data
        self.load_json_data()

        # Load current card data
        self.load_json_data()

    def _on_view_toggle_changed(self, value):
        """Handle the Front / Back / {} Json toggle.

        Switching to Front or Back also flips the live preview to that side — one-way:
        the preview dock's own Front/Back tabs can still be clicked independently
        without moving this toggle back.
        """
        if value == 'json':
            if not self.showing_json:
                self.showing_json = True
                self.create_json_editor()
            return

        if self.showing_json:
            self.showing_json = False
            self.create_form_editors()  # ends by showing view_toggle's current face
        else:
            self._show_face(value)

        preview = getattr(shoggoth.app, 'card_preview', None)
        if preview is not None:
            preview.show_front() if value == 'front' else preview.show_back()

    def load_json_data(self):
        """Load card data into JSON editor"""
        try:
            json_text = json.dumps(self.card.data, indent=2)
            self.json_editor.setPlainText(json_text)
            self.json_status.setText(tr("STATUS_JSON_LOADED"))
            self.json_status.setStyleSheet("color: green;")
        except Exception as e:
            self.json_status.setText(tr("STATUS_LOAD_ERROR").format(error=e))
            self.json_status.setStyleSheet("color: red;")

    def on_json_changed(self):
        """Handle JSON editor changes"""
        if not hasattr(self, 'json_editor'):
            return

        try:
            text = self.json_editor.toPlainText()
            if not text.strip():
                return

            data = json.loads(text)

            # Update front/back face dicts in-place so that Face.data references
            # remain valid (the renderer and editors hold references to those dicts).
            for face_key, face in (('front', self.card.front), ('back', self.card.back)):
                if face_key in data and isinstance(data[face_key], dict):
                    face.data.clear()
                    face.data.update(data[face_key])

            # Sync all other top-level keys, including any custom properties the
            # user may have added.  Keys absent from the edited JSON are removed.
            incoming_top = {k: v for k, v in data.items() if k not in ('front', 'back')}
            for key in [k for k in list(self.card.data) if k not in ('front', 'back')]:
                if key not in incoming_top:
                    del self.card.data[key]
            self.card.data.update(incoming_top)

            self.card.dirty = True
            self.data_changed.emit()

            self.json_status.setText(tr("STATUS_JSON_SAVED"))
            self.json_status.setStyleSheet("color: green;")

        except json.JSONDecodeError as e:
            self.json_status.setText(tr("STATUS_JSON_INVALID").format(error=str(e)[:50]))
            self.json_status.setStyleSheet("color: red;")

    def format_json(self):
        """Format the JSON"""
        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                data = json.loads(text)
                formatted = json.dumps(data, indent=2)
                self.json_editor.setPlainText(formatted)
                self.json_status.setText(tr("STATUS_JSON_FORMATTED"))
                self.json_status.setStyleSheet("color: green;")
        except json.JSONDecodeError as e:
            self.json_status.setText(tr("STATUS_JSON_INVALID").format(error=e))
            self.json_status.setStyleSheet("color: red;")

    def validate_json(self):
        """Validate the JSON"""
        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                json.loads(text)
                self.json_status.setText(tr("STATUS_JSON_VALID"))
                self.json_status.setStyleSheet("color: green;")
            else:
                self.json_status.setText(tr("STATUS_JSON_EMPTY"))
                self.json_status.setStyleSheet("color: orange;")
        except json.JSONDecodeError as e:
            self.json_status.setText(tr("STATUS_JSON_INVALID").format(error=e))
            self.json_status.setStyleSheet("color: red;")

    def create_front_editor(self):
        """Create/recreate front face editor"""
        if self.front_editor:
            self.face_stack.removeWidget(self.front_editor)
            self.front_editor.setParent(None)
            self.front_editor.deleteLater()

        self.front_editor = get_editor_for_face(self.card.front)
        self.front_editor.type_changed.connect(lambda: self.on_type_changed('front'))
        if self._translation_active:
            self.front_editor.enter_translation_mode()
        self.face_stack.addWidget(self.front_editor)

    def create_back_editor(self):
        """Create/recreate back face editor"""
        if self.back_editor:
            self.face_stack.removeWidget(self.back_editor)
            self.back_editor.setParent(None)
            self.back_editor.deleteLater()

        self.back_editor = get_editor_for_face(self.card.back)
        self.back_editor.type_changed.connect(lambda: self.on_type_changed('back'))
        if self._translation_active:
            self.back_editor.enter_translation_mode()
        self.face_stack.addWidget(self.back_editor)

    def _show_face(self, value):
        """Switch the visible face in the stack ('front' or 'back')"""
        if not self.face_stack:
            return
        target = self.front_editor if value == 'front' else self.back_editor
        if target:
            self.face_stack.setCurrentWidget(target)

    def on_type_changed(self, which_face):
        """Handle face type change - recreate the appropriate editor"""
        if which_face == 'front':
            self.create_front_editor()
        else:
            self.create_back_editor()
        self._show_face(self.view_toggle.current_value())

    def setup_card_fields(self):
        """Setup bindings for card-level fields"""
        self._loading_enumerated = False
        self.fields = [
            FieldWidget(self.name_input.input, 'name'),
            FieldWidget(self.copyright_input.input, 'copyright'),
            FieldWidget(self.amount_input.input, 'amount', int),
            FieldWidget(self.collection_input.input, 'project_number'),
            FieldWidget(self.encounter_input.input, 'encounter_number'),
            FieldWidget(self.investigator_input.input, 'investigator'),
            FieldWidget(self.id_input.input, 'id'),
        ]

        # Connect signals
        for field in self.fields:
            widget = field.widget
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(lambda v, f=field: self.on_field_changed(f, v))

        self.enumerated_combo.currentIndexChanged.connect(self.on_enumerated_changed)

    def load_card(self):
        """Load card data into fields"""
        for field in self.fields:
            field.update_from_card(self.card)

        self._loading_enumerated = True
        mode = self.card.get('enumerated') or ''
        index = self.enumerated_combo.findData(mode)
        self.enumerated_combo.setCurrentIndex(index if index >= 0 else 0)
        self._loading_enumerated = False

    def on_field_changed(self, field, value):
        """Handle field value changes"""
        if field.update_card(self.card, value):
            if field.card_key in ('project_number', 'encounter_number'):
                self._set_enumerated_silently('manual')
            self.data_changed.emit()

    def _set_enumerated_silently(self, mode):
        """Update the numbering-mode dropdown/data without re-triggering its change handler."""
        self._loading_enumerated = True
        index = self.enumerated_combo.findData(mode)
        if index >= 0 and self.enumerated_combo.currentIndex() != index:
            self.enumerated_combo.setCurrentIndex(index)
        self._loading_enumerated = False
        if (self.card.get('enumerated') or '') != mode:
            self.card.set('enumerated', mode or None)

    def on_enumerated_changed(self, index):
        """Handle a change to the numbering-mode dropdown."""
        if self._loading_enumerated:
            return

        new_mode = self.enumerated_combo.currentData()
        old_mode = self.card.get('enumerated') or ''

        if old_mode == 'manual' and new_mode == '':
            reply = QMessageBox.warning(
                self, tr("DLG_WARNING"), tr("MSG_ENUM_MANUAL_TO_DEFAULT"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                self._set_enumerated_silently('manual')
                return

        self.card.set('enumerated', new_mode or None)
        self.data_changed.emit()

    def enter_translation_mode(self):
        """Switch both face editors into translation mode and show a translation notice."""
        self._translation_active = True
        self.translation_notice.setVisible(True)
        if self.front_editor:
            self.front_editor.enter_translation_mode()
        if self.back_editor:
            self.back_editor.enter_translation_mode()

    def exit_translation_mode(self):
        """Restore both face editors to normal editing mode and hide the translation notice."""
        self._translation_active = False
        self.translation_notice.setVisible(False)
        if self.front_editor:
            self.front_editor.exit_translation_mode()
        if self.back_editor:
            self.back_editor.exit_translation_mode()

    def cleanup(self):
        """Cleanup editor resources"""
        if self.front_editor and hasattr(self.front_editor, 'cleanup'):
            self.front_editor.cleanup()
        if self.back_editor and hasattr(self.back_editor, 'cleanup'):
            self.back_editor.cleanup()
