"""
Project editor widget for Shoggoth using PySide6
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QFileDialog,
    QScrollArea, QGridLayout, QGroupBox, QInputDialog,
    QMessageBox, QCheckBox, QComboBox
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QPixmap, QImage
from PIL.ImageQt import ImageQt
from pathlib import Path
import threading

import shoggoth
from shoggoth.files import translation_dir
from shoggoth.i18n import tr, get_available_languages_from_dir


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
        self._stop_thumbnails = False

        # Connect thumbnail signal
        self.thumbnail_ready.connect(self._add_thumbnail)

        self.setup_ui()
        self.load_data()

        # Load thumbnails in background
        if self.card_renderer:
            threading.Thread(target=self.load_thumbnails, daemon=True).start()

    def _build_language_combo(self):
        """A combo box of card-render languages, plus a leading 'Automatic'
        entry (empty string) that means "follow the global UI setting"."""
        combo = QComboBox()
        combo.addItem(tr("OPT_LANGUAGE_AUTOMATIC"), "")
        for lang_code, lang_name in get_available_languages_from_dir(translation_dir).items():
            combo.addItem(lang_name, lang_code)
        return combo

    def setup_ui(self):
        """Setup the user interface"""
        if self.project.is_translation:
            self._setup_translation_ui()
        else:
            self._setup_project_ui()

    def _setup_project_ui(self):
        """Full editor for normal projects"""
        layout = QVBoxLayout()

        # Project info section
        info_group = QGroupBox(tr("TITLE_PROJECT_INFORMATION"))
        info_layout = QFormLayout()

        # Name
        self.name_input = QLineEdit()
        self.name_input.textChanged.connect(lambda: self.on_field_changed('name'))
        info_layout.addRow(tr("FIELD_NAME"), self.name_input)

        # Code
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText(tr("PLACEHOLDER_SHORT_CODE"))
        self.code_input.textChanged.connect(lambda: self.on_field_changed('code'))
        info_layout.addRow(tr("FIELD_CODE"), self.code_input)

        # Default copyright
        self.copyright_input = QLineEdit()
        self.copyright_input.setPlaceholderText(tr("PLACEHOLDER_COPYRIGHT"))
        self.copyright_input.textChanged.connect(lambda: self.on_field_changed('default_copyright'))
        info_layout.addRow(tr("FIELD_DEFAULT_COPYRIGHT"), self.copyright_input)

        # Icon
        icon_layout = QHBoxLayout()
        self.icon_input = QLineEdit()
        self.icon_input.textChanged.connect(lambda: self.on_field_changed('icon'))
        self.icon_input.textChanged.connect(self._update_icon_preview)
        icon_layout.addWidget(self.icon_input)
        browse_btn = QPushButton(tr("BTN_BROWSE"))
        browse_btn.clicked.connect(self.browse_icon)
        icon_layout.addWidget(browse_btn)
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(64, 64)
        self.icon_preview.setAlignment(Qt.AlignCenter)
        self.icon_preview.setStyleSheet("border: 1px solid #aaa; background: #d4c3a0;")
        icon_layout.addWidget(self.icon_preview)
        info_layout.addRow(tr("FIELD_ICON"), icon_layout)

        # Card language override
        self.language_combo = self._build_language_combo()
        self.language_combo.currentIndexChanged.connect(lambda: self.on_field_changed('language'))
        info_layout.addRow(tr("FIELD_PROJECT_LANGUAGE"), self.language_combo)
        info_layout.addRow("", QLabel(tr("HELP_PROJECT_LANGUAGE")))

        # Auto-hyphenate
        self.auto_hyphenate_checkbox = QCheckBox(tr("OPT_ENABLE_HYPHENATION"))
        self.auto_hyphenate_checkbox.setToolTip(tr("HELP_HYPHENATION"))
        self.auto_hyphenate_checkbox.toggled.connect(lambda: self.on_field_changed('auto_hyphenate'))
        info_layout.addRow(tr("FIELD_AUTO_HYPHENATE"), self.auto_hyphenate_checkbox)

        # French punctuation spacing
        self.french_punctuation_checkbox = QCheckBox(tr("OPT_ENABLE_FRENCH_PUNCTUATION"))
        self.french_punctuation_checkbox.setToolTip(tr("HELP_FRENCH_PUNCTUATION"))
        self.french_punctuation_checkbox.toggled.connect(lambda: self.on_field_changed('french_punctuation'))
        info_layout.addRow(tr("FIELD_FRENCH_PUNCTUATION"), self.french_punctuation_checkbox)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Actions section
        actions_group = QGroupBox(tr("TITLE_ACTIONS"))
        actions_layout = QHBoxLayout()

        add_encounter_btn = QPushButton(tr("BTN_ADD_ENCOUNTER_SET"))
        add_encounter_btn.clicked.connect(self.add_encounter_set)
        actions_layout.addWidget(add_encounter_btn)

        actions_layout.addStretch()

        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        # Statistics section
        stats_group = QGroupBox(tr("TITLE_STATISTICS"))
        stats_layout = QFormLayout()

        self.encounter_count_label = QLabel("0")
        stats_layout.addRow(tr("FIELD_ENCOUNTER_SETS"), self.encounter_count_label)

        self.card_count_label = QLabel("0")
        stats_layout.addRow(tr("FIELD_TOTAL_CARDS"), self.card_count_label)

        self.player_card_count_label = QLabel("0")
        stats_layout.addRow(tr("FIELD_PLAYER_CARDS"), self.player_card_count_label)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # Translations section
        self.translations_group = QGroupBox("Translations")
        self.translations_layout = QVBoxLayout()
        self.translations_layout.setContentsMargins(8, 8, 8, 8)
        self.translations_group.setLayout(self.translations_layout)
        layout.addWidget(self.translations_group)

        # Card thumbnails section
        thumbnails_group = QGroupBox(tr("TITLE_CARD_OVERVIEW"))
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

    def _setup_translation_ui(self):
        """Simplified view for translation projects"""
        layout = QVBoxLayout()

        # Info section: parent project and language
        info_group = QGroupBox("Translation")
        info_layout = QFormLayout()

        parent_label = QLabel(self.project.data.get('project', ''))
        parent_label.setStyleSheet('color: grey;')
        info_layout.addRow("Parent project:", parent_label)

        lang_label = QLabel(self.project.data.get('language', '').upper())
        info_layout.addRow("Language:", lang_label)

        # Card language override — defaults to the translation's own
        # language (see Translation.apply()), but can still be changed.
        self.language_combo = self._build_language_combo()
        self.language_combo.currentIndexChanged.connect(lambda: self.on_field_changed('language'))
        info_layout.addRow(tr("FIELD_PROJECT_LANGUAGE"), self.language_combo)
        info_layout.addRow("", QLabel(tr("HELP_PROJECT_LANGUAGE")))

        self.card_count_label = QLabel("0")
        info_layout.addRow(tr("FIELD_TOTAL_CARDS"), self.card_count_label)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Card thumbnails section
        thumbnails_group = QGroupBox(tr("TITLE_CARD_OVERVIEW"))
        thumbnails_layout = QVBoxLayout()

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

        if self.project.is_translation:
            # Translation project: only show card count
            self.card_count_label.setText(str(len(self.project.get_all_cards())))
            idx = self.language_combo.findData(self.project.language)
            self.language_combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self.name_input.setText(self.project.get('name', ''))
            self.code_input.setText(self.project.get('code', ''))
            self.copyright_input.setText(self.project.get('default_copyright', ''))
            self.icon_input.setText(self.project.get('icon', ''))
            idx = self.language_combo.findData(self.project.language)
            self.language_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.auto_hyphenate_checkbox.setChecked(self.project.auto_hyphenate)
            self.french_punctuation_checkbox.setChecked(self.project.french_punctuation)

            # Update statistics
            encounter_sets = list(self.project.encounter_sets)
            self.encounter_count_label.setText(str(len(encounter_sets)))
            self.card_count_label.setText(str(len(self.project.get_all_cards())))
            self.player_card_count_label.setText(str(len(self.project.player_cards)))

            # Refresh translations list
            while self.translations_layout.count():
                item = self.translations_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            translations = self.project.data.get('translations', {})
            if translations:
                from PySide6.QtWidgets import QFormLayout
                form = QFormLayout()
                for lang, path in translations.items():
                    form.addRow(QLabel(lang.upper()), QLabel(path))
                self.translations_layout.addLayout(form)
            else:
                self.translations_layout.addWidget(QLabel("No translations registered."))

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
        elif field_name == 'language':
            self.project.language = self.language_combo.currentData() or ''
            if shoggoth.app and shoggoth.app.active_project is self.project:
                effective = self.project.language or shoggoth.app.config.get('Shoggoth', 'card_language', 'en')
                shoggoth.app.card_renderer.set_locale(effective)
                shoggoth.app.schedule_preview_update()
                from shoggoth.ui.main_window import menus
                menus.update_card_language_menu_state(shoggoth.app)
        elif field_name == 'auto_hyphenate':
            self.project.auto_hyphenate = self.auto_hyphenate_checkbox.isChecked()
            if shoggoth.app and shoggoth.app.active_project is self.project:
                shoggoth.app.card_renderer.set_hyphenation_enabled(self.project.auto_hyphenate)
                shoggoth.app.schedule_preview_update()
        elif field_name == 'french_punctuation':
            self.project.french_punctuation = self.french_punctuation_checkbox.isChecked()
            if shoggoth.app and shoggoth.app.active_project is self.project:
                shoggoth.app.card_renderer.set_french_punctuation(self.project.french_punctuation)
                shoggoth.app.schedule_preview_update()

        self.project.dirty = True
        self.data_changed.emit()

    def _update_icon_preview(self, path_text):
        path = Path(path_text.strip()) if path_text.strip() else None
        if path and not path.is_absolute():
            path = Path(self.project.file_path).parent / path
        if path and path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.icon_preview.setPixmap(
                    pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                return
        self.icon_preview.setPixmap(QPixmap())
        self.icon_preview.setText("")

    def browse_icon(self):
        """Browse for icon file"""
        current = self.icon_input.text().strip()
        if current:
            p = Path(current)
            if not p.is_absolute():
                p = self.project.folder / p
            start_dir = str(p.parent) if p.parent.exists() else str(self.project.folder)
        else:
            start_dir = str(self.project.folder)

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("DLG_SELECT_ICON"),
            start_dir,
            tr("FILTER_IMAGES")
        )
        if file_path:
            self.icon_input.setText(file_path)

    def add_encounter_set(self):
        """Add a new encounter set to the project"""
        name, ok = QInputDialog.getText(
            self,
            tr("DLG_NEW_ENCOUNTER_SET"),
            tr("PROMPT_ENCOUNTER_SET_NAME")
        )
        if ok and name:
            try:
                self.project.add_encounter_set(name)
                self.load_data()  # Refresh stats
                QMessageBox.information(
                    self,
                    tr("DLG_SUCCESS"),
                    tr("MSG_ENCOUNTER_SET_CREATED", name=name)
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    tr("DLG_ERROR"),
                    tr("ERR_CREATE_ENCOUNTER_SET", error=str(e))
                )

    def load_thumbnails(self):
        """Load card thumbnails in background"""
        if not self.card_renderer:
            return

        cards = self.project.get_all_cards()

        for index, card in enumerate(cards):
            if self._stop_thumbnails:
                break
            try:
                front_image, _ = self.card_renderer.get_card_textures(card, {'width': 375, 'height': 519, 'bleed': 18}, bleed=False)

                pixmap = QPixmap.fromImage(ImageQt(front_image))

                thumbnail = pixmap.scaled(
                    150, 210,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

                if not self._stop_thumbnails:
                    self.thumbnail_ready.emit(thumbnail, card.name, index)

            except Exception as e:
                print(f"Error rendering thumbnail for {card.name}: {e}")

    def cleanup(self):
        """Stop background thumbnail generation"""
        self._stop_thumbnails = True

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
