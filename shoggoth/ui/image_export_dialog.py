"""
Modal dialog for bulk image export with full control over scope and format.
"""
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QRadioButton, QCheckBox, QLabel, QComboBox, QSpinBox,
    QPushButton, QButtonGroup, QProgressDialog, QMessageBox,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt

from shoggoth.i18n import tr
from shoggoth.settings import EXPORT_SIZES

FILENAME_FORMATS = [
    ('id',        'UUID ({id})'),
    ('code_name', 'Code + name ({code}_{name})'),
    ('order',     'Order number ({order})'),
    ('name',      'Name only ({name})'),
]


class ImageExportDialog(QDialog):
    """Modal dialog that collects image export options and runs the export."""

    def __init__(self, project, renderer, parent=None):
        super().__init__(parent)
        self.project  = project
        self.renderer = renderer

        self.setWindowTitle(tr("IMG_EXPORT_DLG_TITLE"))
        self.setMinimumWidth(460)
        self.setWindowModality(Qt.ApplicationModal)

        self._build_ui()

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
        self._rb_all.setChecked(True)
        for rb in (self._rb_campaign, self._rb_player, self._rb_all):
            self._scope_group.addButton(rb)
            scope_layout.addWidget(rb)
        root.addWidget(scope_group)

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

    def _selected_size(self):
        index = self._size_combo.currentIndex()
        return EXPORT_SIZES[index][1]

    def _selected_filename_format(self):
        return FILENAME_FORMATS[self._filename_combo.currentIndex()][0]

    def _cards_for_scope(self):
        if self._rb_campaign.isChecked():
            cards = []
            for es in self.project.encounter_sets:
                cards.extend(es.cards)
            return cards
        if self._rb_player.isChecked():
            return list(self.project.player_cards)
        return list(self.project.get_all_cards())

    def _run_export(self):
        cards = self._cards_for_scope()
        if not cards:
            QMessageBox.information(self, tr("IMG_EXPORT_DLG_TITLE"), tr("MSG_NO_CARDS_IN_SET"))
            return

        export_folder = Path(self.project.file_path).parent / f'Export of {self.project.name}'
        export_folder.mkdir(parents=True, exist_ok=True)

        fmt            = self._format_combo.currentText()
        quality        = self._quality_spin.value()
        size           = self._selected_size()
        bleed          = self._cb_bleed.isChecked()
        separate       = self._cb_separate.isChecked()
        include_backs  = self._cb_backs.isChecked()
        rotate         = self._cb_rotate.isChecked()
        filename_fmt   = self._selected_filename_format()

        progress = QProgressDialog(
            tr("TTS_EXPORTING_IMAGES"), tr("BTN_CANCEL"), 0, len(cards), self
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        import multiprocessing
        cores = max(4, multiprocessing.cpu_count() - 1)
        threads = []

        try:
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
                        'size':            size,
                        'bleed':           bleed,
                        'format':          fmt,
                        'quality':         quality,
                        'include_backs':   include_backs,
                        'separate_versions': separate,
                        'rotate':          rotate,
                        'filename_format': filename_fmt,
                    }
                )
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            progress.setValue(len(cards))

            QMessageBox.information(
                self,
                tr("DLG_EXPORT_COMPLETE"),
                tr("MSG_EXPORTED_CARDS").format(count=len(cards), folder=export_folder)
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_EXPORT_ERROR"), tr("ERR_EXPORT_CARDS").format(error=e))
