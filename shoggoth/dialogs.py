"""
Dialogs for creating new cards and projects
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QComboBox, QLabel,
    QDialogButtonBox, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
from pathlib import Path
import json
from uuid import uuid4

import shoggoth
from shoggoth.card import Card, TEMPLATES
from shoggoth.project import Project
from shoggoth.i18n import tr


class NewCardDialog(QDialog):
    """Dialog for creating a new card"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("DLG_NEW_CARD"))
        self.setMinimumWidth(500)
        
        self.selected_template = 'asset'
        self.selected_encounter = None
        
        self.setup_ui()
        
        # Pre-fill from current context if available
        if shoggoth.app.current_card:
            card = shoggoth.app.current_card
            if card.encounter:
                self.selected_encounter = card.encounter
                self.encounter_combo.setCurrentText(card.encounter.name)
                self.template_combo.setCurrentText('treachery')
    
    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout()
        
        # Form layout for inputs
        form = QFormLayout()
        
        # Card name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(tr("PLACEHOLDER_ENTER_CARD_NAME"))
        form.addRow(tr("FIELD_NAME"), self.name_input)
        
        # Template selection
        self.template_combo = QComboBox()
        templates = [
            'asset', 'event', 'skill', 'investigator',
            'enemy', 'treachery', 'location',
            'act', 'agenda', 'scenario', 'story'
        ]
        self.template_combo.addItems(templates)
        self.template_combo.currentTextChanged.connect(self.on_template_changed)
        form.addRow(tr("FIELD_TEMPLATE"), self.template_combo)
        
        # Encounter set selection
        self.encounter_combo = QComboBox()
        self.encounter_combo.addItem(tr("TYPE_PLAYER_CARD"), None)
        
        if shoggoth.app.current_project:
            for encounter in shoggoth.app.current_project.encounter_sets:
                self.encounter_combo.addItem(encounter.name, encounter)
        
        self.encounter_combo.currentIndexChanged.connect(self.on_encounter_changed)
        form.addRow(tr("FIELD_ENCOUNTER_SET"), self.encounter_combo)
        
        layout.addLayout(form)
        
        # Error label
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        layout.addWidget(self.error_label)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.create_card)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def on_template_changed(self, template):
        """Handle template change"""
        self.selected_template = template
    
    def on_encounter_changed(self, index):
        """Handle encounter set change"""
        self.selected_encounter = self.encounter_combo.itemData(index)
    
    def create_card(self):
        """Create the card"""
        name = self.name_input.text().strip()
        
        if not name:
            self.error_label.setText(tr("MSG_ENTER_CARD_NAME"))
            return
        
        try:
            # Get template
            template = TEMPLATES.get(self.selected_template)
            template['name'] = name
            
            # Create card
            project = shoggoth.app.current_project
            new_card = Card(
                data=template,
                expansion=project,
                encounter=self.selected_encounter
            )
            
            # Add to project
            project.add_card(new_card)
            
            # Refresh tree and navigate to new card
            shoggoth.app.refresh_tree()
            shoggoth.app.show_card(new_card)
            shoggoth.app.select_item_in_tree(new_card.id)
            
            self.accept()
        except Exception as e:
            self.error_label.setText(tr("ERR_CREATING_CARD").format(error=e))


class NewProjectDialog(QDialog):
    """Dialog for creating a new project"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("DLG_NEW_PROJECT"))
        self.setMinimumWidth(500)
        
        self.file_path = None
        self.icon_path = None
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout()
        
        # Form layout
        form = QFormLayout()
        
        # Project code
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText(tr("PLACEHOLDER_ABC"))
        self.code_input.setMaxLength(5)
        form.addRow(tr("FIELD_ABBREVIATION"), self.code_input)
        
        # Project name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(tr("PLACEHOLDER_EXAMPLE_PROJECT"))
        form.addRow(tr("FIELD_NAME"), self.name_input)
        
        # Icon
        icon_layout = QHBoxLayout()
        self.icon_display = QLineEdit()
        self.icon_display.setReadOnly(True)
        self.icon_display.setPlaceholderText(tr("PLACEHOLDER_NO_ICON"))
        icon_layout.addWidget(self.icon_display)
        
        icon_btn = QPushButton(tr("BTN_BROWSE"))
        icon_btn.clicked.connect(self.browse_icon)
        icon_layout.addWidget(icon_btn)
        
        form.addRow(tr("FIELD_ICON"), icon_layout)
        
        # File location
        file_layout = QHBoxLayout()
        self.file_display = QLineEdit()
        self.file_display.setReadOnly(True)
        self.file_display.setPlaceholderText(tr("PLACEHOLDER_NO_LOCATION"))
        file_layout.addWidget(self.file_display)
        
        file_btn = QPushButton(tr("BTN_BROWSE"))
        file_btn.clicked.connect(self.browse_file)
        file_layout.addWidget(file_btn)
        
        form.addRow(tr("FIELD_SAVE_LOCATION"), file_layout)
        
        layout.addLayout(form)
        
        # Error label
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        layout.addWidget(self.error_label)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.create_project)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def browse_icon(self):
        """Browse for icon file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("DLG_SELECT_ICON"),
            str(Path.home()),
            tr("FILTER_IMAGES")
        )
        if file_path:
            self.icon_path = file_path
            self.icon_display.setText(file_path)
    
    def browse_file(self):
        """Browse for save location"""
        suggested_name = self.name_input.text() or "project"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            str(Path.home() / f"{suggested_name}.json"),
            "JSON Files (*.json)"
        )
        if file_path:
            self.file_path = file_path
            self.file_display.setText(file_path)
    
    def create_project(self):
        """Create the project"""
        name = self.name_input.text().strip()
        code = self.code_input.text().strip()
        
        if not name:
            self.error_label.setText(tr("MSG_ENTER_PROJECT_NAME"))
            return
        
        if not code:
            self.error_label.setText(tr("MSG_ENTER_ABBREVIATION"))
            return
        
        if not self.file_path:
            self.error_label.setText(tr("MSG_SELECT_SAVE_LOCATION"))
            return
        
        try:
            # Create project data
            data = Project.new(
                name=name,
                code=code,
                icon=self.icon_path or ''
            )
            
            # Save to file
            with open(self.file_path, 'w') as f:
                json.dump(data, f, indent=4)
            
            # Load project
            shoggoth.app.open_project(self.file_path)
            
            self.accept()
        except Exception as e:
            self.error_label.setText(tr("ERR_CREATING_PROJECT").format(error=e))