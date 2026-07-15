"""
Modal dialog for bulk image export with full control over scope and format.
"""
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QRadioButton, QCheckBox, QLabel, QComboBox, QSpinBox,
    QPushButton, QButtonGroup, QProgressDialog, QMessageBox,
    QDialogButtonBox, QLineEdit, QFileDialog,
)
from PySide6.QtCore import Qt

from shoggoth.card import natural_sort_key
from shoggoth.i18n import tr
from shoggoth.settings import EXPORT_SIZES
import multiprocessing

FILENAME_FORMATS = [
    ('id',        'UUID ({id})'),
    ('code_name', 'Code + name ({code}_{name})'),
    ('order',     'Order number ({order})'),
    ('name',      'Name only ({name})'),
]


class ImageExportDialog(QDialog):
    """Modal dialog that collects image export options and runs the export."""

    def __init__(self, project, renderer, parent=None, encounter_set=None):
        super().__init__(parent)
        self.project  = project
        self.renderer = renderer
        self._initial_encounter_set = encounter_set
        self.main_window = parent

        self.setWindowTitle(tr("IMG_EXPORT_DLG_TITLE"))
        self.setMinimumWidth(460)
        self.setWindowModality(Qt.ApplicationModal)

        self._build_ui()
        self._load_prefs()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── Scope ──────────────────────────────────────────────────────
        scope_group = QGroupBox(tr("TTS_SCOPE_LABEL"))
        scope_layout = QVBoxLayout(scope_group)

        self._scope_group = QButtonGroup(self)
        self._rb_campaign = QRadioButton(tr("TTS_SCOPE_CAMPAIGN"))
        self._rb_player   = QRadioButton(tr("TTS_SCOPE_PLAYER"))
        self._rb_all      = QRadioButton(tr("TTS_SCOPE_ALL"))
        self._rb_encounter = QRadioButton(tr("TTS_SCOPE_ENCOUNTER_SET"))

        encounter_sets = list(self.project.encounter_sets)
        self._encounter_combo = QComboBox()
        self._encounter_combo.setEnabled(False)
        for es in encounter_sets:
            self._encounter_combo.addItem(es.name, es)

        encounter_row = QHBoxLayout()
        encounter_row.setContentsMargins(0, 0, 0, 0)
        encounter_row.addWidget(self._rb_encounter)
        encounter_row.addWidget(self._encounter_combo, 1)

        if self._initial_encounter_set is not None:
            self._rb_encounter.setChecked(True)
            self._encounter_combo.setEnabled(True)
            for i, es in enumerate(encounter_sets):
                if es.id == self._initial_encounter_set.id:
                    self._encounter_combo.setCurrentIndex(i)
                    break
        else:
            self._rb_all.setChecked(True)

        for rb in (self._rb_campaign, self._rb_player, self._rb_all):
            self._scope_group.addButton(rb)
            scope_layout.addWidget(rb)
        self._scope_group.addButton(self._rb_encounter)
        scope_layout.addLayout(encounter_row)

        self._rb_encounter.toggled.connect(self._encounter_combo.setEnabled)

        root.addWidget(scope_group)

        # ── Destination ────────────────────────────────────────────────
        folder_group = QGroupBox(tr("IMG_EXPORT_FOLDER_LABEL"))
        folder_layout = QVBoxLayout(folder_group)

        self._folder_btn_group = QButtonGroup(self)
        self._rb_project_folder = QRadioButton(tr("TTS_FOLDER_PROJECT"))
        self._rb_custom_folder  = QRadioButton(tr("TTS_FOLDER_CUSTOM"))
        self._rb_project_folder.setChecked(True)
        self._folder_btn_group.addButton(self._rb_project_folder)
        self._folder_btn_group.addButton(self._rb_custom_folder)
        self._rb_project_folder.toggled.connect(self._on_folder_type_changed)
        folder_layout.addWidget(self._rb_project_folder)

        self._default_folder_label = QLabel(f"  {self._default_export_folder()}")
        self._default_folder_label.setStyleSheet("color: #888; font-size: 9pt;")
        folder_layout.addWidget(self._default_folder_label)

        folder_layout.addWidget(self._rb_custom_folder)

        custom_row = QHBoxLayout()
        self._custom_folder_input = QLineEdit()
        self._custom_folder_input.setEnabled(False)
        custom_row.addWidget(self._custom_folder_input)
        self._browse_folder_btn = QPushButton(tr("BTN_BROWSE"))
        self._browse_folder_btn.setEnabled(False)
        self._browse_folder_btn.clicked.connect(self._browse_folder)
        custom_row.addWidget(self._browse_folder_btn)
        folder_layout.addLayout(custom_row)

        root.addWidget(folder_group)

        # ── Format ─────────────────────────────────────────────────────
        format_group = QGroupBox(tr("GROUP_EXPORT_FORMAT"))
        format_form = QFormLayout(format_group)
        format_form.setRowWrapPolicy(QFormLayout.DontWrapRows)

        self._size_combo = QComboBox()
        self._size_combo.addItems([label for label, _ in EXPORT_SIZES])
        self._size_combo.setCurrentIndex(1)
        format_form.addRow(tr("LABEL_EXPORT_SIZE"), self._size_combo)

        self._format_combo = QComboBox()
        self._format_combo.addItems(['png', 'jpeg', 'webp'])
        self._format_combo.currentTextChanged.connect(self._on_format_changed)
        format_form.addRow(tr("LABEL_FORMAT"), self._format_combo)

        self._quality_spin = QSpinBox()
        self._quality_spin.setRange(1, 100)
        self._quality_spin.setValue(95)
        self._quality_spin.setSuffix("%")
        self._quality_spin.setEnabled(False)
        format_form.addRow(tr("LABEL_QUALITY"), self._quality_spin)

        root.addWidget(format_group)

        # ── File naming ────────────────────────────────────────────────
        naming_group = QGroupBox(tr("IMG_EXPORT_NAMING_LABEL"))
        naming_form = QFormLayout(naming_group)

        self._filename_combo = QComboBox()
        for _, label in FILENAME_FORMATS:
            self._filename_combo.addItem(label)
        naming_form.addRow(tr("IMG_EXPORT_FILENAME_LABEL"), self._filename_combo)
        root.addWidget(naming_group)

        # ── Options ────────────────────────────────────────────────────
        options_group = QGroupBox(tr("GROUP_EXPORT_OPTIONS"))
        options_form = QFormLayout(options_group)

        self._cb_rotate = QCheckBox(tr("IMG_EXPORT_ROTATE_OPT"))
        options_form.addRow(tr("IMG_EXPORT_ROTATE_LABEL"), self._cb_rotate)

        self._cb_bleed = QCheckBox(tr("OPT_INCLUDE_BLEED"))
        self._cb_bleed.setChecked(True)
        options_form.addRow(tr("LABEL_INCLUDE_BLEED"), self._cb_bleed)

        self._cb_separate = QCheckBox(tr("OPT_SEPARATE_VERSIONS"))
        options_form.addRow(tr("LABEL_SEPARATE_VERSIONS"), self._cb_separate)

        self._cb_backs = QCheckBox(tr("OPT_INCLUDE_BACKS"))
        options_form.addRow(tr("LABEL_INCLUDE_BACKS"), self._cb_backs)

        root.addWidget(options_group)

        # ── Buttons ────────────────────────────────────────────────────
        buttons = QDialogButtonBox(Qt.Horizontal)
        self._export_btn = buttons.addButton(tr("TTS_BTN_EXPORT"), QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._run_export)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_format_changed(self, fmt):
        self._quality_spin.setEnabled(fmt in ('jpeg', 'webp'))

    def _on_folder_type_changed(self, project_selected):
        self._custom_folder_input.setEnabled(not project_selected)
        self._browse_folder_btn.setEnabled(not project_selected)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, tr("TTS_DLG_SELECT_FOLDER"),
            self._custom_folder_input.text().strip() or str(Path(self.project.file_path).parent)
        )
        if folder:
            self._custom_folder_input.setText(folder)

    def _default_export_folder(self):
        return Path(self.project.file_path).parent / f'Export of {self.project.name}'

    def _selected_folder(self):
        if self._rb_custom_folder.isChecked():
            custom = self._custom_folder_input.text().strip()
            if custom:
                return Path(custom)
        return self._default_export_folder()

    def _selected_size(self):
        index = self._size_combo.currentIndex()
        return EXPORT_SIZES[index][1]

    def _selected_filename_format(self):
        return FILENAME_FORMATS[self._filename_combo.currentIndex()][0]

    # ------------------------------------------------------------------
    # Per-project preference persistence (stored in shoggoth.json)
    # ------------------------------------------------------------------

    def _load_prefs(self):
        prefs = self._stored_prefs()
        if not prefs:
            return

        folder = prefs.get('folder')
        if folder and Path(folder) != self._default_export_folder():
            self._rb_custom_folder.setChecked(True)
            self._custom_folder_input.setText(folder)

        size_label = prefs.get('size_label')
        if size_label is not None:
            for i, (label, _) in enumerate(EXPORT_SIZES):
                if label == size_label:
                    self._size_combo.setCurrentIndex(i)
                    break

        fmt = prefs.get('format')
        if fmt is not None:
            index = self._format_combo.findText(fmt)
            if index >= 0:
                self._format_combo.setCurrentIndex(index)

        if 'quality' in prefs:
            self._quality_spin.setValue(prefs['quality'])

        filename_format = prefs.get('filename_format')
        if filename_format is not None:
            for i, (key, _) in enumerate(FILENAME_FORMATS):
                if key == filename_format:
                    self._filename_combo.setCurrentIndex(i)
                    break

        if 'rotate' in prefs:
            self._cb_rotate.setChecked(prefs['rotate'])
        if 'bleed' in prefs:
            self._cb_bleed.setChecked(prefs['bleed'])
        if 'separate_versions' in prefs:
            self._cb_separate.setChecked(prefs['separate_versions'])
        if 'include_backs' in prefs:
            self._cb_backs.setChecked(prefs['include_backs'])

    def _save_prefs(self, folder):
        if self.main_window is None or not hasattr(self.main_window, 'settings'):
            return

        all_prefs = self.main_window.settings.setdefault('project_export_prefs', {})
        all_prefs[self.project.id] = {
            'folder': str(folder),
            'size_label': EXPORT_SIZES[self._size_combo.currentIndex()][0],
            'format': self._format_combo.currentText(),
            'quality': self._quality_spin.value(),
            'filename_format': self._selected_filename_format(),
            'rotate': self._cb_rotate.isChecked(),
            'bleed': self._cb_bleed.isChecked(),
            'separate_versions': self._cb_separate.isChecked(),
            'include_backs': self._cb_backs.isChecked(),
        }

        if hasattr(self.main_window, 'save_settings'):
            self.main_window.save_settings()

    def _stored_prefs(self):
        if self.main_window is None or not hasattr(self.main_window, 'settings'):
            return None
        return self.main_window.settings.get('project_export_prefs', {}).get(self.project.id)

    def _cards_for_scope(self):
        if self._rb_campaign.isChecked():
            cards = []
            for es in self.project.encounter_sets:
                cards.extend(es.cards)
            return cards
        if self._rb_player.isChecked():
            return list(self.project.player_cards)
        if self._rb_encounter.isChecked():
            es = self._encounter_combo.currentData()
            return list(es.cards) if es else []
        return list(self.project.get_all_cards())

    def _run_export(self):
        cards = self._cards_for_scope()
        cards.sort(key=lambda x: natural_sort_key(x.project_number))
        if not cards:
            QMessageBox.information(self, tr("IMG_EXPORT_DLG_TITLE"), tr("MSG_NO_CARDS_IN_SET"))
            return

        export_folder = self._selected_folder()
        export_folder.mkdir(parents=True, exist_ok=True)

        fmt = self._format_combo.currentText()
        quality = self._quality_spin.value()
        size = self._selected_size()
        bleed = self._cb_bleed.isChecked()
        separate = self._cb_separate.isChecked()
        include_backs = self._cb_backs.isChecked()
        rotate = self._cb_rotate.isChecked()
        filename_fmt = self._selected_filename_format()

        progress = QProgressDialog(
            tr("TTS_EXPORTING_IMAGES"), tr("BTN_CANCEL"), 0, len(cards), self
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        cores = max(4, multiprocessing.cpu_count() - 1)
        threads = []

        try:
            number = 1
            for i, card in enumerate(cards):
                if progress.wasCanceled():
                    break

                if i >= cores:
                    threads[i - cores].join()
                    progress.setValue(i - cores)

                progress.setLabelText(tr("MSG_EXPORTING_CARD").format(name=card.name))

                t = threading.Thread(
                    target=self.renderer.export_card_images,
                    args=(card, str(export_folder)),
                    kwargs={
                        'size': size,
                        'bleed': bleed,
                        'format': fmt,
                        'quality': quality,
                        'include_backs': include_backs,
                        'separate_versions': separate,
                        'rotate': rotate,
                        'filename_format': filename_fmt,
                        'number': number,
                    }
                )
                threads.append(t)
                t.start()
                number += card.amount

            for t in threads:
                t.join()

            progress.setValue(len(cards))

            self._save_prefs(export_folder)

            QMessageBox.information(
                self,
                tr("DLG_EXPORT_COMPLETE"),
                tr("MSG_EXPORTED_CARDS").format(count=len(cards), folder=export_folder)
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_EXPORT_ERROR"), tr("ERR_EXPORT_CARDS").format(error=e))
