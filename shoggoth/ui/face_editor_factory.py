"""
Face editor factory and base/json editors for Shoggoth
"""
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
)

from shoggoth.ui.face_editor import FaceEditor
from shoggoth.ui.text_editor import ArkhamTextEdit
from shoggoth.ui.player_editors import AssetEditor, EventEditor, SkillEditor, CustomizableEditor
from shoggoth.ui.encounter_editors import EnemyEditor, TreacheryEditor, LocationEditor, LocationBackEditor
from shoggoth.ui.campaign_editors import (
    ActEditor, ActBackEditor, AgendaEditor, AgendaBackEditor, ChaosEditor, StoryEditor
)
from shoggoth.ui.investigator_editors import InvestigatorEditor, InvestigatorBackEditor
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
        info.setStyleSheet("color: #666; padding: 5px;")
        self.main_layout.addWidget(info)

        # Create the JSON editor with syntax highlighting
        self.json_editor = ArkhamTextEdit()
        self.json_editor.setPlaceholderText("{\n  \"type\": \"asset\",\n  \"name\": \"Card Name\"\n}")

        # Enable JSON syntax highlighting
        try:
            from pygments.lexers import JsonLexer
            self.json_editor.set_lexer(JsonLexer())
        except:
            pass  # Syntax highlighting optional

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
                # Update face data
                self.face.data = data
                # Emit type_changed if type changed (to potentially switch editor)
                if 'type' in data and data['type'] != self.face.get('type'):
                    self.type_changed.emit()
                self.status_label.setText(tr("STATUS_SAVED"))
                self.status_label.setStyleSheet("color: green; padding: 5px;")
        except json.JSONDecodeError as e:
            self.status_label.setText(tr("STATUS_JSON_INVALID").format(error=str(e)[:50]))
            self.status_label.setStyleSheet("color: red; padding: 5px;")


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
    'location': LocationEditor,
    'location_back': LocationBackEditor,
    'treachery': TreacheryEditor,
    'enemy': EnemyEditor,
    'act': ActEditor,
    'act_back': ActBackEditor,
    'agenda': AgendaEditor,
    'agenda_back': AgendaBackEditor,
    'chaos': ChaosEditor,
    'customizable': CustomizableEditor,
    'story': StoryEditor,
}


def get_editor_for_face(face, parent=None):
    """Get the appropriate editor for a face"""
    editor_type = face.get_editor()
    editor_class = EDITOR_MAPPING.get(editor_type, JsonEditor)
    return editor_class(face, parent)
