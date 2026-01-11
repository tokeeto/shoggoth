"""
Project editor widget for Shoggoth using PySide6
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QFileDialog,
    QScrollArea, QGridLayout, QGroupBox, QInputDialog,
    QMessageBox
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QPixmap, QImage
from pathlib import Path
import threading

import shoggoth


class ProjectEditor(QWidget):
    """Editor widget for project settings"""

    # Signal emitted when project data changes
    data_changed = Signal()

    # Signal for adding thumbnails from background thread
    thumbnail_ready = Signal(QPixmap, str, int)

    def __init__(self, project, card_renderer=None):
        super().__init__()
        self.project = project
        self.card_renderer = card_renderer
        self._updating = False

        # Connect thumbnail signal
        self.thumbnail_ready.connect(self._add_thumbnail)

        self.setup_ui()
        self.load_data()

        # Load thumbnails in background
        if self.card_renderer:
            threading.Thread(target=self.load_thumbnails, daemon=True).start()

    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout()

        # Project info section
        info_group = QGroupBox("Project Information")
        info_layout = QFormLayout()

        # Name
        self.name_input = QLineEdit()
        self.name_input.textChanged.connect(lambda: self.on_field_changed('name'))
        info_layout.addRow("Name:", self.name_input)

        # Code
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Short code for file naming")
        self.code_input.textChanged.connect(lambda: self.on_field_changed('code'))
        info_layout.addRow("Code:", self.code_input)

        # Default copyright
        self.copyright_input = QLineEdit()
        self.copyright_input.setPlaceholderText("Default copyright text for cards")
        self.copyright_input.textChanged.connect(lambda: self.on_field_changed('default_copyright'))
        info_layout.addRow("Default Copyright:", self.copyright_input)

        # Icon
        icon_layout = QHBoxLayout()
        self.icon_input = QLineEdit()
        self.icon_input.textChanged.connect(lambda: self.on_field_changed('icon'))
        icon_layout.addWidget(self.icon_input)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_icon)
        icon_layout.addWidget(browse_btn)
        info_layout.addRow("Icon:", icon_layout)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Actions section
        actions_group = QGroupBox("Actions")
        actions_layout = QHBoxLayout()

        add_encounter_btn = QPushButton("Add Encounter Set")
        add_encounter_btn.clicked.connect(self.add_encounter_set)
        actions_layout.addWidget(add_encounter_btn)

        actions_layout.addStretch()

        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        # Statistics section
        stats_group = QGroupBox("Statistics")
        stats_layout = QFormLayout()

        self.encounter_count_label = QLabel("0")
        stats_layout.addRow("Encounter Sets:", self.encounter_count_label)

        self.card_count_label = QLabel("0")
        stats_layout.addRow("Total Cards:", self.card_count_label)

        self.player_card_count_label = QLabel("0")
        stats_layout.addRow("Player Cards:", self.player_card_count_label)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # Card thumbnails section
        thumbnails_group = QGroupBox("Card Overview")
        thumbnails_layout = QVBoxLayout()

        # Scroll area for thumbnails
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(300)

        self.thumbnail_container = QWidget()
        self.thumbnail_grid = QGridLayout()
        self.thumbnail_grid.setSpacing(10)
        self.thumbnail_container.setLayout(self.thumbnail_grid)

        scroll.setWidget(self.thumbnail_container)
        thumbnails_layout.addWidget(scroll)

        thumbnails_group.setLayout(thumbnails_layout)
        layout.addWidget(thumbnails_group)

        self.setLayout(layout)

    def load_data(self):
        """Load project data into fields"""
        self._updating = True

        self.name_input.setText(self.project.get('name', ''))
        self.code_input.setText(self.project.get('code', ''))
        self.copyright_input.setText(self.project.get('default_copyright', ''))
        self.icon_input.setText(self.project.get('icon', ''))

        # Update statistics
        encounter_sets = list(self.project.encounter_sets)
        self.encounter_count_label.setText(str(len(encounter_sets)))
        self.card_count_label.setText(str(len(self.project.get_all_cards())))
        self.player_card_count_label.setText(str(len(self.project.player_cards)))

        self._updating = False

    def on_field_changed(self, field_name):
        """Handle field change"""
        if self._updating:
            return

        if field_name == 'name':
            self.project.data['name'] = self.name_input.text()
        elif field_name == 'code':
            self.project.data['code'] = self.code_input.text()
        elif field_name == 'default_copyright':
            self.project.data['default_copyright'] = self.copyright_input.text()
        elif field_name == 'icon':
            self.project.data['icon'] = self.icon_input.text()

        self.project.dirty = True
        self.data_changed.emit()

    def browse_icon(self):
        """Browse for icon file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Icon",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if file_path:
            self.icon_input.setText(file_path)

    def add_encounter_set(self):
        """Add a new encounter set to the project"""
        name, ok = QInputDialog.getText(
            self,
            "New Encounter Set",
            "Enter encounter set name:"
        )
        if ok and name:
            try:
                self.project.add_encounter_set(name)
                self.load_data()  # Refresh stats
                QMessageBox.information(
                    self,
                    "Success",
                    f"Encounter set '{name}' created."
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to create encounter set: {e}"
                )

    def load_thumbnails(self):
        """Load card thumbnails in background"""
        if not self.card_renderer:
            return

        cards = self.project.get_all_cards()

        for index, card in enumerate(cards):
            try:
                # Render thumbnail
                front_image, _ = self.card_renderer.get_card_textures(card, bleed=False)

                # Convert to QPixmap
                front_image.seek(0)
                image_data = front_image.read()
                qimage = QImage.fromData(image_data)
                pixmap = QPixmap.fromImage(qimage)

                # Scale to thumbnail size
                thumbnail = pixmap.scaled(
                    150, 210,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

                # Emit signal to add thumbnail in main thread
                self.thumbnail_ready.emit(thumbnail, card.name, index)

            except Exception as e:
                print(f"Error rendering thumbnail for {card.name}: {e}")

    @Slot(QPixmap, str, int)
    def _add_thumbnail(self, pixmap, card_name, index):
        """Add thumbnail to grid (called from main thread via signal)"""
        cols = 4
        row = index // cols
        col = index % cols

        label = QLabel()
        label.setPixmap(pixmap)
        label.setToolTip(card_name)
        label.setAlignment(Qt.AlignCenter)

        self.thumbnail_grid.addWidget(label, row, col)
