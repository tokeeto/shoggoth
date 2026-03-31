"""
Modal dialog for PDF export (campaign cards or player cards).
"""
from pathlib import Path
import threading

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QCheckBox, QLabel, QLineEdit, QPushButton, QButtonGroup, QRadioButton,
    QProgressDialog, QMessageBox, QDialogButtonBox, QFileDialog,
    QFrame
)
from PySide6.QtCore import Qt

from shoggoth.i18n import tr

PDF_IMAGE_SIZE    = {'width': 1500, 'height': 2100, 'bleed': 72}
PDF_IMAGE_FORMAT  = 'png'
PDF_IMAGE_QUALITY = 100


class PDFExportDialog(QDialog):
    """Modal dialog that collects PDF export options and runs the export."""

    def __init__(self, project, renderer, cards, title, mbprint=False, default_filename=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.renderer = renderer
        self.cards = cards
        self.mbprint = mbprint
        self._default_filename = default_filename or f"{project.name}.pdf"

        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.setWindowModality(Qt.ApplicationModal)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── Images ─────────────────────────────────────────────────────
        images_group = QGroupBox(tr("PDF_IMAGES_LABEL"))
        images_layout = QVBoxLayout(images_group)

        self._cb_export_images = QCheckBox(tr("PDF_EXPORT_IMAGES_CHECK"))
        self._cb_export_images.setChecked(True)
        self._cb_export_images.toggled.connect(self._on_export_images_toggled)
        images_layout.addWidget(self._cb_export_images)

        self._warning_label = QLabel(tr("PDF_IMAGES_WARNING"))
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #c0392b; font-style: italic;")
        self._warning_label.setVisible(False)
        images_layout.addWidget(self._warning_label)

        # Folder sub-section
        self._folder_frame = QFrame()
        folder_layout = QVBoxLayout(self._folder_frame)
        folder_layout.setContentsMargins(0, 4, 0, 0)
        folder_layout.setSpacing(6)

        folder_layout.addWidget(QLabel(tr("PDF_IMAGE_FOLDER_LABEL")))

        self._folder_btn_group = QButtonGroup(self)
        self._rb_project_folder = QRadioButton(tr("PDF_FOLDER_PROJECT"))
        self._rb_custom_folder  = QRadioButton(tr("PDF_FOLDER_CUSTOM"))
        self._rb_project_folder.setChecked(True)
        self._folder_btn_group.addButton(self._rb_project_folder)
        self._folder_btn_group.addButton(self._rb_custom_folder)

        self._rb_project_folder.toggled.connect(self._on_folder_type_changed)
        folder_layout.addWidget(self._rb_project_folder)

        default_folder = self._default_image_folder()
        self._default_folder_label = QLabel(f"  {default_folder}")
        self._default_folder_label.setStyleSheet("color: #888; font-size: 9pt;")
        folder_layout.addWidget(self._default_folder_label)

        folder_layout.addWidget(self._rb_custom_folder)

        custom_row = QHBoxLayout()
        self._custom_folder_input = QLineEdit()
        self._custom_folder_input.setEnabled(False)
        custom_row.addWidget(self._custom_folder_input)
        self._browse_folder_btn = QPushButton(tr("BTN_BROWSE"))
        self._browse_folder_btn.setEnabled(False)
        self._browse_folder_btn.clicked.connect(self._browse_image_folder)
        custom_row.addWidget(self._browse_folder_btn)
        folder_layout.addLayout(custom_row)

        images_layout.addWidget(self._folder_frame)
        root.addWidget(images_group)

        # Format info bar
        info = QLabel(tr("PDF_FORMAT_INFO").format(
            fmt=PDF_IMAGE_FORMAT.upper(),
            w=PDF_IMAGE_SIZE['width'],
            h=PDF_IMAGE_SIZE['height'],
        ))
        info.setStyleSheet("color: #888; font-style: italic; font-size: 9pt;")
        root.addWidget(info)

        # ── PDF output path ────────────────────────────────────────────
        output_group = QGroupBox(tr("PDF_OUTPUT_LABEL"))
        output_layout = QVBoxLayout(output_group)

        output_row = QHBoxLayout()
        self._pdf_path_input = QLineEdit()
        self._pdf_path_input.setText(str(self._default_pdf_path()))
        output_row.addWidget(self._pdf_path_input)
        browse_output_btn = QPushButton(tr("BTN_BROWSE"))
        browse_output_btn.clicked.connect(self._browse_pdf_output)
        output_row.addWidget(browse_output_btn)
        output_layout.addLayout(output_row)

        root.addWidget(output_group)

        # ── Buttons ────────────────────────────────────────────────────
        buttons = QDialogButtonBox(Qt.Horizontal)
        buttons.addButton(tr("PDF_BTN_EXPORT"), QDialogButtonBox.AcceptRole)
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
        self._browse_folder_btn.setEnabled(not project_selected)

    def _browse_image_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, tr("PDF_DLG_SELECT_FOLDER"),
            str(Path(self.project.file_path).parent)
        )
        if folder:
            self._custom_folder_input.setText(folder)

    def _browse_pdf_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("PDF_DLG_SELECT_OUTPUT"),
            self._pdf_path_input.text(),
            "PDF Files (*.pdf)"
        )
        if path:
            self._pdf_path_input.setText(path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _default_image_folder(self):
        return self.project.folder / f"Export of {self.project.name}"

    def _default_pdf_path(self):
        return Path(self.project.file_path).parent / self._default_filename

    def _image_folder(self):
        if self._rb_project_folder.isChecked():
            return self._default_image_folder()
        custom = self._custom_folder_input.text().strip()
        return Path(custom) if custom else self._default_image_folder()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _run_export(self):
        pdf_path = self._pdf_path_input.text().strip()
        if not pdf_path:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("PDF_ERR_NO_OUTPUT_PATH"))
            return

        image_folder = self._image_folder()

        if self._cb_export_images.isChecked():
            if not self._export_images(image_folder):
                return  # cancelled or error already shown

        try:
            from shoggoth import pdf_exporter
            if self.mbprint:
                pdf_exporter.create_mbprint_pdf(self.cards, pdf_path, image_folder)
            else:
                pdf_exporter.export(self.cards, pdf_path, image_folder)
        except Exception as e:
            print(e)
            QMessageBox.critical(self, tr("DLG_ERROR"), tr("MSG_PDF_EXPORT_FAILED").format(error=str(e)))
            return

        QMessageBox.information(self, self.windowTitle(), tr("MSG_PDF_EXPORTED").format(path=pdf_path))
        self.accept()

    def _export_images(self, image_folder):
        """Export card images as PNG to image_folder. Returns False if cancelled."""
        if not self.cards:
            return True

        image_folder.mkdir(parents=True, exist_ok=True)

        progress = QProgressDialog(
            tr("PDF_EXPORTING_IMAGES"), tr("BTN_CANCEL"), 0, len(self.cards), self
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        threads = []
        cancelled = [False]

        for i, card in enumerate(self.cards):
            if progress.wasCanceled():
                cancelled[0] = True
                break

            progress.setValue(i)
            progress.setLabelText(tr("MSG_EXPORTING_CARD").format(name=card.name))

            t = threading.Thread(
                target=self.renderer.export_card_images,
                args=(card, str(image_folder)),
                kwargs={
                    'size': PDF_IMAGE_SIZE,
                    'bleed': True,
                    'format': PDF_IMAGE_FORMAT,
                    'quality': PDF_IMAGE_QUALITY,
                }
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        progress.setValue(len(self.cards))
        return not cancelled[0]
