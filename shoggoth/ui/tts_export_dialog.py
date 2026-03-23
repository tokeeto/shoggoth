"""
Modal dialog for Tabletop Simulator export
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton,
    QCheckBox, QLabel, QLineEdit, QPushButton, QButtonGroup,
    QProgressDialog, QMessageBox, QDialogButtonBox, QFileDialog,
    QFrame
)
from PySide6.QtCore import Qt

from shoggoth.i18n import tr

TTS_IMAGE_SIZE   = {'width': 750, 'height': 1050, 'bleed': 36}
TTS_IMAGE_FORMAT = 'webp'
TTS_IMAGE_QUALITY = 85


class TTSExportDialog(QDialog):
    """Modal dialog that collects TTS export options and runs the export."""

    def __init__(self, project, renderer, parent=None):
        super().__init__(parent)
        self.project  = project
        self.renderer = renderer

        self.setWindowTitle(tr("TTS_DLG_TITLE"))
        self.setMinimumWidth(520)
        self.setWindowModality(Qt.ApplicationModal)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

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
        self._rb_campaign.setChecked(True)

        for rb in (self._rb_campaign, self._rb_player, self._rb_all):
            self._scope_group.addButton(rb)
            scope_layout.addWidget(rb)

        root.addWidget(scope_group)

        # ── Images ─────────────────────────────────────────────────────
        images_group = QGroupBox(tr("TTS_IMAGES_LABEL"))
        images_layout = QVBoxLayout(images_group)

        self._cb_export_images = QCheckBox(tr("TTS_EXPORT_IMAGES_CHECK"))
        self._cb_export_images.setChecked(True)
        self._cb_export_images.toggled.connect(self._on_export_images_toggled)
        images_layout.addWidget(self._cb_export_images)

        self._warning_label = QLabel(tr("TTS_IMAGES_WARNING"))
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #c0392b; font-style: italic;")
        self._warning_label.setVisible(False)
        images_layout.addWidget(self._warning_label)

        # Folder sub-section
        self._folder_frame = QFrame()
        folder_layout = QVBoxLayout(self._folder_frame)
        folder_layout.setContentsMargins(0, 4, 0, 0)
        folder_layout.setSpacing(6)

        folder_layout.addWidget(QLabel(tr("TTS_IMAGE_FOLDER_LABEL")))

        self._folder_btn_group = QButtonGroup(self)
        self._rb_project_folder = QRadioButton(tr("TTS_FOLDER_PROJECT"))
        self._rb_custom_folder  = QRadioButton(tr("TTS_FOLDER_CUSTOM"))
        self._rb_project_folder.setChecked(True)
        self._folder_btn_group.addButton(self._rb_project_folder)
        self._folder_btn_group.addButton(self._rb_custom_folder)

        self._rb_project_folder.toggled.connect(self._on_folder_type_changed)
        folder_layout.addWidget(self._rb_project_folder)

        # Default path hint
        default_folder = self._default_export_folder()
        self._default_folder_label = QLabel(f"  {default_folder}")
        self._default_folder_label.setStyleSheet("color: #888; font-size: 9pt;")
        folder_layout.addWidget(self._default_folder_label)

        folder_layout.addWidget(self._rb_custom_folder)

        custom_row = QHBoxLayout()
        self._custom_folder_input = QLineEdit()
        self._custom_folder_input.setEnabled(False)
        custom_row.addWidget(self._custom_folder_input)
        self._browse_btn = QPushButton(tr("BTN_BROWSE"))
        self._browse_btn.setEnabled(False)
        self._browse_btn.clicked.connect(self._browse_folder)
        custom_row.addWidget(self._browse_btn)
        folder_layout.addLayout(custom_row)

        images_layout.addWidget(self._folder_frame)
        root.addWidget(images_group)

        # ── Info bar ───────────────────────────────────────────────────
        info = QLabel(tr("TTS_FORMAT_INFO").format(
            fmt=TTS_IMAGE_FORMAT.upper(),
            w=TTS_IMAGE_SIZE['width'],
            h=TTS_IMAGE_SIZE['height'],
        ))
        info.setStyleSheet("color: #888; font-style: italic; font-size: 9pt;")
        root.addWidget(info)

        # ── Buttons ────────────────────────────────────────────────────
        buttons = QDialogButtonBox(Qt.Horizontal)
        self._export_btn = buttons.addButton(tr("TTS_BTN_EXPORT"), QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._run_export)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    def _on_export_images_toggled(self, checked):
        self._folder_frame.setVisible(checked)
        self._warning_label.setVisible(not checked)

    def _on_folder_type_changed(self, project_selected):
        self._custom_folder_input.setEnabled(not project_selected)
        self._browse_btn.setEnabled(not project_selected)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, tr("TTS_DLG_SELECT_FOLDER"),
            str(Path(self.project.file_path).parent)
        )
        if folder:
            self._custom_folder_input.setText(folder)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _default_export_folder(self):
        return Path(self.project.file_path).parent / f"Export of {self.project.name}"

    def _image_folder(self):
        if self._rb_project_folder.isChecked():
            return self._default_export_folder()
        custom = self._custom_folder_input.text().strip()
        return Path(custom) if custom else self._default_export_folder()

    def _cards_for_scope(self):
        if self._rb_campaign.isChecked():
            cards = []
            for es in self.project.encounter_sets:
                cards.extend(es.cards)
            return cards
        if self._rb_player.isChecked():
            return list(self.project.player_cards)
        return list(self.project.get_all_cards())

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _run_export(self):
        image_folder = self._image_folder()

        if self._cb_export_images.isChecked():
            if not self._export_images(image_folder):
                return  # User cancelled or error already reported

        try:
            from shoggoth import tts_lib
            if self._rb_campaign.isChecked():
                status, path = tts_lib.export_campaign(self.project, image_folder)
            elif self._rb_player.isChecked():
                status, path = tts_lib.export_player_cards(self.project.player_cards, image_folder)
            else:
                status, path = tts_lib.export_all(self.project, image_folder)
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_ERROR"), tr("ERR_EXPORT_TTS").format(error=e))
            return

        if status == 1:
            msg = tr("TTS_RESULT_TTS_DIR").format(path=path)
        else:
            msg = tr("TTS_RESULT_PROJECT_DIR").format(path=path)

        QMessageBox.information(self, tr("TTS_DLG_TITLE"), msg)
        self.accept()

    def _export_images(self, image_folder):
        """Export card images as WebP to image_folder. Returns False if cancelled."""
        cards = self._cards_for_scope()
        if not cards:
            return True

        image_folder.mkdir(parents=True, exist_ok=True)

        progress = QProgressDialog(
            tr("TTS_EXPORTING_IMAGES"), tr("BTN_CANCEL"), 0, len(cards), self
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        import threading
        threads = []
        cancelled = [False]

        for i, card in enumerate(cards):
            if progress.wasCanceled():
                cancelled[0] = True
                break

            progress.setValue(i)
            progress.setLabelText(tr("MSG_EXPORTING_CARD").format(name=card.name))

            t = threading.Thread(
                target=self.renderer.export_card_images,
                args=(card, str(image_folder)),
                kwargs={
                    'size': TTS_IMAGE_SIZE,
                    'bleed': False,
                    'format': TTS_IMAGE_FORMAT,
                    'quality': TTS_IMAGE_QUALITY,
                    'include_backs': True,
                }
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        progress.setValue(len(cards))
        return not cancelled[0]
