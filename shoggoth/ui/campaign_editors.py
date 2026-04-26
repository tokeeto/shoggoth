"""
Campaign card editors for Shoggoth (act, agenda, chaos, story)
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLineEdit
)

from shoggoth.ui.face_editor import FaceEditor
from shoggoth.i18n import tr


class ActEditor(FaceEditor):
    """Editor for act cards (front side)"""

    def setup_ui(self):
        self.add_labeled_line(tr("FIELD_NAME"), "name")
        self.add_labeled_line(tr("FIELD_INDEX"), "index")
        self.add_labeled_line(tr("FIELD_CLUES"), "clues")

        self.add_labeled_text(tr("FIELD_TEXT"), "text", use_arkham=True)
        self.add_labeled_text(tr("FIELD_FLAVOR"), "flavor_text")
        self.add_illustration_widget()

        # Copyright and collection
        self.add_copyright_collection_row()

        self.main_layout.addStretch()


class ActBackEditor(FaceEditor):
    """Editor for act cards (back side)"""

    def setup_ui(self):
        self.add_labeled_line(tr("FIELD_NAME"), "name")
        self.add_labeled_line(tr("FIELD_INDEX"), "index")

        self.add_labeled_text(tr("FIELD_TEXT"), "text", use_arkham=True)
        self.add_labeled_text(tr("FIELD_FLAVOR"), "flavor_text")

        # Copyright and collection
        self.add_copyright_collection_row()

        self.main_layout.addStretch()


class AgendaEditor(FaceEditor):
    """Editor for agenda cards (front side)"""

    def setup_ui(self):
        self.add_labeled_line(tr("FIELD_NAME"), "name")
        self.add_labeled_line(tr("FIELD_INDEX"), "index")
        self.add_labeled_line(tr("FIELD_DOOM"), "doom")

        self.add_labeled_text(tr("FIELD_TEXT"), "text", use_arkham=True)
        self.add_labeled_text(tr("FIELD_FLAVOR"), "flavor_text")
        self.add_illustration_widget()

        # Copyright and collection
        self.add_copyright_collection_row()

        self.main_layout.addStretch()


class AgendaBackEditor(FaceEditor):
    """Editor for agenda cards (back side)"""

    def setup_ui(self):
        self.add_labeled_line(tr("FIELD_NAME"), "name")
        self.add_labeled_line(tr("FIELD_INDEX"), "index")

        self.add_labeled_text(tr("FIELD_TEXT"), "text", use_arkham=True)
        self.add_labeled_text(tr("FIELD_FLAVOR"), "flavor_text")

        # Copyright and collection
        self.add_copyright_collection_row()

        self.main_layout.addStretch()


class ChaosEditor(FaceEditor):
    """Editor for chaos bag reference cards"""

    NUM_ENTRIES = 10

    def setup_ui(self):
        self.add_labeled_line(tr("FIELD_DIFFICULTY"), "difficulty")

        # Entries section
        entries_group = QGroupBox(tr("GROUP_CHAOS_BAG_ENTRIES"))
        entries_layout = QVBoxLayout()
        entries_layout.setSpacing(8)
        entries_layout.setContentsMargins(6, 6, 6, 6)

        self.entry_widgets = []  # Store (token_input, text_input) pairs

        for i in range(self.NUM_ENTRIES):
            entry_widget = QWidget()
            entry_layout = QHBoxLayout()
            entry_layout.setContentsMargins(0, 0, 0, 0)

            # Token input (comma-separated list of tokens)
            token_input = QLineEdit()
            token_input.setPlaceholderText(tr("PLACEHOLDER_TOKENS"))
            token_input.setMaximumWidth(150)
            token_input.textChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(token_input)

            # Text input
            text_input = QLineEdit()
            text_input.setPlaceholderText(tr("PLACEHOLDER_EFFECT_TEXT"))
            text_input.textChanged.connect(self.on_entries_changed)
            entry_layout.addWidget(text_input)

            entry_widget.setLayout(entry_layout)
            entries_layout.addWidget(entry_widget)

            self.entry_widgets.append((token_input, text_input))

        entries_group.setLayout(entries_layout)
        self.main_layout.addWidget(entries_group)

        # Copyright and collection
        self.add_copyright_collection_row()

        self.main_layout.addStretch()

    def load_data(self):
        """Load data from face into fields"""
        self.updating = True

        # Load regular fields
        for field_name, widget in self.fields.items():
            value = self.face.get(field_name, '')
            self.set_widget_value(widget, value)

        # Load entries
        entries = self.face.get('entries', [])
        if not entries:
            entries = []

        for i, (token_input, text_input) in enumerate(self.entry_widgets):
            if i < len(entries) and isinstance(entries[i], dict):
                # Token is a list, join with comma
                tokens = entries[i].get('token', [])
                if isinstance(tokens, list):
                    token_input.setText(', '.join(str(t) for t in tokens))
                else:
                    token_input.setText(str(tokens) if tokens else '')
                text_input.setText(str(entries[i].get('text', '')))
            else:
                token_input.setText('')
                text_input.setText('')

        self.updating = False

    def on_entries_changed(self):
        """Handle changes to entry fields"""
        if self.updating:
            return

        entries = []
        for token_input, text_input in self.entry_widgets:
            token_str = token_input.text().strip()
            text = text_input.text().strip()

            if token_str or text:
                # Parse tokens as comma-separated list
                tokens = [t.strip() for t in token_str.split(',') if t.strip()]
                entries.append({'token': tokens, 'text': text})

        if entries:
            self.face.set('entries', entries)
        else:
            self.face.set('entries', None)

        # Emit data_changed signal
        parent = self.parent()
        while parent:
            if hasattr(parent, 'data_changed'):
                parent.data_changed.emit()
                break
            parent = parent.parent()


class StoryEditor(FaceEditor):
    """Editor for story cards"""

    def setup_ui(self):
        self.add_labeled_line(tr("FIELD_NAME"), "name")
        self.add_class_field()

        self.add_labeled_text(tr("FIELD_TEXT"), "text", use_arkham=True)

        # Copyright and collection
        self.add_copyright_collection_row()

        self.main_layout.addStretch()
