"""
Modal dialog for arkham.build export
"""
import json
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QCheckBox, QLabel, QLineEdit, QPushButton, QButtonGroup,
    QRadioButton, QProgressDialog, QMessageBox, QDialogButtonBox,
    QFileDialog, QFrame
)
from PySide6.QtCore import Qt

from shoggoth.arkham_build import AB_IMAGE_FORMAT, AB_IMAGE_SIZE, AB_IMAGE_QUALITY
from shoggoth.i18n import tr


class ArkhamBuildExportDialog(QDialog):
    """Modal dialog that collects arkham.build export options and runs the export."""

    def __init__(self, project, renderer, parent=None):
        super().__init__(parent)
        self.project = project
        self.renderer = renderer

        self.setWindowTitle(tr("AB_DLG_TITLE"))
        self.setMinimumWidth(500)
        self.setWindowModality(Qt.ApplicationModal)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── Images ─────────────────────────────────────────────────────
        images_group = QGroupBox(tr("AB_IMAGES_LABEL"))
        images_layout = QVBoxLayout(images_group)

        self._cb_export_images = QCheckBox(tr("AB_EXPORT_IMAGES_CHECK"))
        self._cb_export_images.setChecked(True)
        self._cb_export_images.toggled.connect(self._on_export_images_toggled)
        images_layout.addWidget(self._cb_export_images)

        self._warning_label = QLabel(tr("AB_IMAGES_WARNING"))
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #c0392b; font-style: italic;")
        self._warning_label.setVisible(False)
        images_layout.addWidget(self._warning_label)

        self._folder_frame = QFrame()
        folder_layout = QVBoxLayout(self._folder_frame)
        folder_layout.setContentsMargins(0, 4, 0, 0)
        folder_layout.setSpacing(6)

        folder_layout.addWidget(QLabel(tr("AB_IMAGE_FOLDER_LABEL")))

        self._folder_btn_group = QButtonGroup(self)
        self._rb_project_folder = QRadioButton(tr("AB_FOLDER_PROJECT"))
        self._rb_custom_folder = QRadioButton(tr("AB_FOLDER_CUSTOM"))
        self._rb_project_folder.setChecked(True)
        self._folder_btn_group.addButton(self._rb_project_folder)
        self._folder_btn_group.addButton(self._rb_custom_folder)
        self._rb_project_folder.toggled.connect(self._on_folder_type_changed)

        folder_layout.addWidget(self._rb_project_folder)

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

        # ── Image URL pattern ──────────────────────────────────────────
        url_group = QGroupBox(tr("AB_URL_PATTERN_LABEL"))
        url_layout = QVBoxLayout(url_group)

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText(tr("AB_URL_PATTERN_PLACEHOLDER"))
        url_layout.addWidget(self._url_input)

        hint = QLabel(tr("AB_URL_PATTERN_HINT"))
        hint.setStyleSheet("color: #888; font-size: 9pt;")
        url_layout.addWidget(hint)

        root.addWidget(url_group)

        # ── Buttons ────────────────────────────────────────────────────
        buttons = QDialogButtonBox(Qt.Horizontal)
        buttons.addButton(tr("AB_BTN_EXPORT"), QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._run_export)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_export_images_toggled(self, checked):
        self._folder_frame.setVisible(checked)
        self._warning_label.setVisible(not checked)

    def _on_folder_type_changed(self, project_selected):
        self._custom_folder_input.setEnabled(not project_selected)
        self._browse_btn.setEnabled(not project_selected)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, tr("AB_DLG_SELECT_FOLDER"),
            str(Path(self.project.file_path).parent)
        )
        if folder:
            self._custom_folder_input.setText(folder)

    def _default_export_folder(self):
        return Path(self.project.file_path).parent / f"Export of {self.project.name}"

    def _image_folder(self):
        if self._rb_project_folder.isChecked():
            return self._default_export_folder()
        custom = self._custom_folder_input.text().strip()
        return Path(custom) if custom else self._default_export_folder()

    def _run_export(self):
        image_folder = self._image_folder()

        if self._cb_export_images.isChecked():
            if not self._export_images(image_folder):
                return

        url_pattern = self._url_input.text().strip() or None

        try:
            from shoggoth import arkham_build
            data = arkham_build.export_project(self.project, image_pattern=url_pattern)
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_ERROR"), tr("ERR_EXPORT_ARKHAM_BUILD").format(error=e))
            return

        output_path = Path(self.project.file_path).parent / f"{self.project.name}_arkham_build.json"
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_ERROR"), tr("ERR_EXPORT_ARKHAM_BUILD").format(error=e))
            return

        QMessageBox.information(self, tr("AB_DLG_TITLE"), tr("AB_RESULT").format(path=output_path))
        self.accept()

    def _export_images(self, image_folder):
        """Export card images to image_folder. Returns False if cancelled."""
        cards = list(self.project.get_all_cards())
        if not cards:
            return True

        image_folder.mkdir(parents=True, exist_ok=True)

        progress = QProgressDialog(
            tr("AB_EXPORTING_IMAGES"), tr("BTN_CANCEL"), 0, len(cards), self
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

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
                    'size': AB_IMAGE_SIZE,
                    'bleed': False,
                    'format': AB_IMAGE_FORMAT,
                    'quality': AB_IMAGE_QUALITY,
                    'include_backs': True,
                }
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        progress.setValue(len(cards))
        return not cancelled[0]
