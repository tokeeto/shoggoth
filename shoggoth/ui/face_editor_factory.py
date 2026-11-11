"""
Face editor factory and base/json editors for Shoggoth
"""
import json

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel
)

from shoggoth.ui.face_editor import FaceEditor
from shoggoth.ui.text_editor import PlainJsonTextEdit
from shoggoth.ui.player_editors import AssetEditor, EventEditor, SkillEditor, CustomizableEditor
from shoggoth.ui.encounter_editors import (
    EnemyEditor, TreacheryEditor, LocationEditor, LocationBackEditor, EnemyLocationEditor,
    ConcealedEditor, ConcealedBackEditor,
)
from shoggoth.ui.campaign_editors import (
    ActEditor, ActBackEditor, AgendaEditor, AgendaBackEditor, ChaosEditor, StoryEditor
)
from shoggoth.ui.investigator_editors import InvestigatorEditor, InvestigatorBackEditor, MiniInvestigatorEditor
from shoggoth.i18n import tr


class BaseEditor(FaceEditor):
    """Basic editor with just type field"""

    def setup_ui(self):
        """Type is already added by base class"""
        self.main_layout.addStretch()


class JsonEditor(FaceEditor):
    """Raw JSON editor for unknown types or manual editing"""

    def setup_ui(self):
        # Add a header explaining this is raw JSON mode
        header = QLabel(tr("JSON_EDITOR_HEADER"))
        header.setStyleSheet("font-size: 14pt; padding: 5px;")
        self.main_layout.addWidget(header)

        info = QLabel(tr("JSON_EDITOR_INFO"))
        info.setWordWrap(True)
        info.setStyleSheet("padding: 5px;")
        self.main_layout.addWidget(info)

        # Create the JSON editor
        self.json_editor = PlainJsonTextEdit(monospace=True)
        self.json_editor.setPlaceholderText("{\n  \"type\": \"asset\",\n  \"name\": \"Card Name\"\n}")
        self.json_editor.textChanged.connect(self.on_json_changed)
        self.main_layout.addWidget(self.json_editor)

        # Validation status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("padding: 5px;")
        self.main_layout.addWidget(self.status_label)

        # Format button
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
        self.main_layout.addWidget(button_widget)

    def format_json(self):
        """Format the JSON text"""
        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                data = json.loads(text)
                formatted = json.dumps(data, indent=2)
                self.json_editor.setPlainText(formatted)
                self.status_label.setText(tr("STATUS_FORMATTED"))
                self.status_label.setStyleSheet("color: green; padding: 5px;")
        except json.JSONDecodeError as e:
            self.status_label.setText(tr("STATUS_JSON_INVALID").format(error=e))
            self.status_label.setStyleSheet("color: red; padding: 5px;")

    def validate_json(self):
        """Validate the JSON"""
        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                json.loads(text)
                self.status_label.setText(tr("STATUS_VALID_JSON"))
                self.status_label.setStyleSheet("color: green; padding: 5px;")
            else:
                self.status_label.setText(tr("STATUS_EMPTY"))
                self.status_label.setStyleSheet("color: orange; padding: 5px;")
        except json.JSONDecodeError as e:
            self.status_label.setText(tr("STATUS_JSON_INVALID").format(error=e))
            self.status_label.setStyleSheet("color: red; padding: 5px;")

    def load_data(self):
        """Load face data as JSON"""
        super().load_data()  # load type field
        self.updating = True
        try:
            json_text = json.dumps(self.face.data, indent=2)
            self.json_editor.setPlainText(json_text)
            self.status_label.setText(tr("STATUS_JSON_LOADED"))
            self.status_label.setStyleSheet("color: green; padding: 5px;")
        except Exception as e:
            self.json_editor.setPlainText(tr("STATUS_ERROR_LOADING_JSON").format(error=e))
            self.status_label.setText(tr("STATUS_LOAD_ERROR").format(error=e))
            self.status_label.setStyleSheet("color: red; padding: 5px;")
        self.updating = False

    def on_json_changed(self):
        """Save JSON back to face"""
        if self.updating:
            return

        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                data = json.loads(text)
                if not isinstance(data, dict):
                    raise json.JSONDecodeError("a face must be a JSON object", text, 0)
                old_type = self.face.data.get('type')
                # Update the face dict in place: card.data['front'/'back'] is the same
                # object, and that is what gets saved and what the card's JSON tab shows.
                # Rebinding face.data would split the two apart.
                self.face.data.clear()
                self.face.data.update(data)
                if data.get('type') != old_type:
                    self.face._fallback = None
                    self.updating = True
                    self.set_widget_value(self.type_combo, data.get('type', ''))
                    self.updating = False
                self.face.card.dirty = True
                self._emit_data_changed()
                # Switch editor only once the type/"editor" names one that exists
                # (rebuilding on every keystroke of a type name would lose the cursor).
                if editor_class_for_face(self.face) is not JsonEditor:
                    self.type_changed.emit(self.face)
                    return
                self.status_label.setText(tr("STATUS_SAVED"))
                self.status_label.setStyleSheet("color: green; padding: 5px;")
        except json.JSONDecodeError as e:
            self.status_label.setText(tr("STATUS_JSON_INVALID").format(error=str(e)[:50]))
            self.status_label.setStyleSheet("color: red; padding: 5px;")

    def _emit_data_changed(self):
        parent = self.parent()
        while parent:
            if hasattr(parent, 'data_changed'):
                parent.data_changed.emit()
                break
            parent = parent.parent()


# Mapping of editor types to classes
EDITOR_MAPPING = {
    'player': BaseEditor,
    'customizable_back': BaseEditor,
    'encounter': BaseEditor,
    'asset': AssetEditor,
    'event': EventEditor,
    'skill': SkillEditor,
    'investigator': InvestigatorEditor,
    'investigator_back': InvestigatorBackEditor,
    'mini_investigator': MiniInvestigatorEditor,
    'mini_investigator_back': MiniInvestigatorEditor,
    'location': LocationEditor,
    'location_back': LocationBackEditor,
    'treachery': TreacheryEditor,
    'enemy': EnemyEditor,
    'enemy_location': EnemyLocationEditor,
    'act': ActEditor,
    'act_back': ActBackEditor,
    'agenda': AgendaEditor,
    'agenda_back': AgendaBackEditor,
    'chaos': ChaosEditor,
    'customizable': CustomizableEditor,
    'story': StoryEditor,
    'concealed': ConcealedEditor,
    'concealed_decoy': ConcealedEditor,
    'concealed_back': ConcealedBackEditor,
}


def editor_class_for_face(face):
    """The editor class get_editor_for_face would build for this face"""
    return next(
        (EDITOR_MAPPING[name] for name in face.editor_candidates() if name in EDITOR_MAPPING),
        JsonEditor,
    )


def get_editor_for_face(face, parent=None):
    """Get the appropriate editor for a face"""
    return editor_class_for_face(face)(face, parent)
