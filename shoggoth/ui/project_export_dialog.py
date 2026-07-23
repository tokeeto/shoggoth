"""
Unified Project Export dialog: Images / PDF / TTS / arkham.build / Guides as
five toggleable sections sharing one profile-level scope, saved as named
profiles inside the project file (project.data['export_profiles']). Opened
in two modes:

  persist=True   "Export Project"   - the edited profile is saved back to the
                                       project on export.
  persist=False  "One-Time Export"  - identical UI, starting from the same
                                       saved profiles, but nothing is written
                                       back to the project.

Profile data is deep-copied out of the project at construction time and only
ever written back (via project.save_all()) on a successful persisted export,
so cancelling -- or running in one-time mode -- never mutates the live
project, even in memory.

Section execution itself lives in export_runner.py, shared with the
Export -> Setups quick-run menu.
"""
import copy

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QComboBox, QSpinBox, QCheckBox, QLineEdit, QPushButton, QFileDialog,
    QMessageBox, QDialogButtonBox, QInputDialog, QFrame, QScrollArea, QWidget,
)
from PySide6.QtCore import Qt

from shoggoth.export_profile import default_sections, default_scope
from shoggoth.i18n import tr
from shoggoth.settings import EXPORT_SIZES
from shoggoth.ui.export_widgets import FolderPicker, ProfileScopeSelector, CollapsibleSection

FILENAME_FORMATS = [
    ('id',        'UUID ({id})'),
    ('code_name', 'Code + name ({code}_{name})'),
    ('order',     'Order number ({order})'),
    ('name',      'Name only ({name})'),
]

PDF_FLAVORS = [
    ('pdf', 'Plain PDF'),
    ('mbprint', 'MBPrint'),
    ('azao', 'Azao'),
]


def _resolve_size(label):
    for lbl, size in EXPORT_SIZES:
        if lbl == label:
            return size
    return EXPORT_SIZES[1][1]


def _size_combo_index(combo, label):
    if label:
        idx = combo.findText(label)
        if idx >= 0:
            return idx
    return 1 if combo.count() > 1 else 0


class ProjectExportDialog(QDialog):
    def __init__(self, project, renderer, parent=None, persist=True):
        super().__init__(parent)
        self.project = project
        self.renderer = renderer
        self.persist = persist

        self._profiles_data = [copy.deepcopy(p.data) for p in project.export_profiles]
        self._current_index = -1
        self._new_profile_ids = set()

        self.setWindowTitle(tr("PE_DLG_TITLE") if persist else tr("PE_ONE_TIME_TITLE"))
        self.resize(620, 780)
        self.setWindowModality(Qt.ApplicationModal)

        self._build_ui()

        if self._profiles_data:
            self._select_profile(0, expand=False)
        else:
            self._apply_profile_to_widgets(
                {'scope': default_scope(), 'sections': default_sections()}, expand=True
            )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        if self._profiles_data:
            picker_row = QHBoxLayout()
            picker_row.addWidget(QLabel(tr("PE_PROFILE_LABEL")))
            self._profile_combo = QComboBox()
            for data in self._profiles_data:
                self._profile_combo.addItem(data.get('name', 'Profile'))
            self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
            picker_row.addWidget(self._profile_combo, 1)
            add_btn = QPushButton(tr("PE_BTN_ADD_PROFILE"))
            add_btn.clicked.connect(self._add_profile)
            picker_row.addWidget(add_btn)
            root.addLayout(picker_row)

        self._scope_selector = ProfileScopeSelector(self.project)
        root.addWidget(self._scope_selector)

        self._images_section = CollapsibleSection(tr("PE_SECTION_IMAGES"))
        self._build_images_section(self._images_section.body_layout)
        root.addWidget(self._images_section)

        self._pdf_section = CollapsibleSection(tr("PE_SECTION_PDF"))
        self._build_pdf_section(self._pdf_section.body_layout)
        root.addWidget(self._pdf_section)

        self._tts_section = CollapsibleSection(tr("PE_SECTION_TTS"))
        self._build_tts_section(self._tts_section.body_layout)
        root.addWidget(self._tts_section)

        self._ab_section = CollapsibleSection(tr("PE_SECTION_ARKHAM_BUILD"))
        self._build_arkham_build_section(self._ab_section.body_layout)
        root.addWidget(self._ab_section)

        self._guides_section = CollapsibleSection(tr("PE_SECTION_GUIDES"))
        self._build_guides_section(self._guides_section.body_layout)
        root.addWidget(self._guides_section)

        self._all_sections = [
            self._images_section, self._pdf_section, self._tts_section,
            self._ab_section, self._guides_section,
        ]

        self._maybe_disable_pdf_section()
        root.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(12, 8, 12, 12)
        buttons = QDialogButtonBox(Qt.Horizontal)
        export_label = tr("PE_BTN_EXPORT") if self.persist else tr("PE_BTN_EXPORT_ONCE")
        buttons.addButton(export_label, QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._run_export)
        buttons.rejected.connect(self.reject)
        button_row.addWidget(buttons)
        outer.addLayout(button_row)

    def _maybe_disable_pdf_section(self):
        from shoggoth.pdf_exporter import check_prince_installed
        if check_prince_installed():
            return
        self._pdf_section.set_enabled_checked(False)
        self._pdf_section.body.setEnabled(False)
        hint = QLabel(tr("PE_PRINCE_NOT_INSTALLED"))
        hint.setStyleSheet("color: #c0392b; font-style: italic;")
        hint.setWordWrap(True)
        self._pdf_section.body_layout.insertWidget(0, hint)

    # -- Images ----------------------------------------------------------

    def _build_images_section(self, layout):
        self._img_folder = FolderPicker(tr("IMG_EXPORT_FOLDER_LABEL"), self._default_folder())
        layout.addWidget(self._img_folder)

        format_group = QGroupBox(tr("GROUP_EXPORT_FORMAT"))
        form = QFormLayout(format_group)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)

        self._img_size_combo = QComboBox()
        self._img_size_combo.addItems([label for label, _ in EXPORT_SIZES])
        form.addRow(tr("LABEL_EXPORT_SIZE"), self._img_size_combo)

        self._img_format_combo = QComboBox()
        self._img_format_combo.addItems(['png', 'jpeg', 'webp'])
        self._img_format_combo.currentTextChanged.connect(
            lambda fmt: self._img_quality_spin.setEnabled(fmt in ('jpeg', 'webp'))
        )
        form.addRow(tr("LABEL_FORMAT"), self._img_format_combo)

        self._img_quality_spin = QSpinBox()
        self._img_quality_spin.setRange(1, 100)
        self._img_quality_spin.setSuffix("%")
        form.addRow(tr("LABEL_QUALITY"), self._img_quality_spin)
        layout.addWidget(format_group)

        naming_group = QGroupBox(tr("IMG_EXPORT_NAMING_LABEL"))
        naming_form = QFormLayout(naming_group)
        self._img_filename_combo = QComboBox()
        for _, label in FILENAME_FORMATS:
            self._img_filename_combo.addItem(label)
        naming_form.addRow(tr("IMG_EXPORT_FILENAME_LABEL"), self._img_filename_combo)
        layout.addWidget(naming_group)

        options_group = QGroupBox(tr("GROUP_EXPORT_OPTIONS"))
        options_form = QFormLayout(options_group)
        self._img_rotate = QCheckBox(tr("IMG_EXPORT_ROTATE_OPT"))
        options_form.addRow(tr("IMG_EXPORT_ROTATE_LABEL"), self._img_rotate)
        self._img_bleed = QCheckBox(tr("OPT_INCLUDE_BLEED"))
        options_form.addRow(tr("LABEL_INCLUDE_BLEED"), self._img_bleed)
        self._img_separate = QCheckBox(tr("OPT_SEPARATE_VERSIONS"))
        options_form.addRow(tr("LABEL_SEPARATE_VERSIONS"), self._img_separate)
        self._img_backs = QCheckBox(tr("OPT_INCLUDE_BACKS"))
        options_form.addRow(tr("LABEL_INCLUDE_BACKS"), self._img_backs)
        layout.addWidget(options_group)

    def _apply_images(self, d):
        self._images_section.set_enabled_checked(d['enabled'])
        self._img_folder.set_folder(d.get('folder'))
        self._img_size_combo.setCurrentIndex(_size_combo_index(self._img_size_combo, d.get('size_label')))
        self._img_format_combo.setCurrentText(d.get('format', 'png'))
        self._img_quality_spin.setValue(d.get('quality', 95))
        for i, (key, _) in enumerate(FILENAME_FORMATS):
            if key == d.get('filename_format', 'id'):
                self._img_filename_combo.setCurrentIndex(i)
                break
        self._img_rotate.setChecked(d.get('rotate', False))
        self._img_bleed.setChecked(d.get('bleed', True))
        self._img_separate.setChecked(d.get('separate_versions', False))
        self._img_backs.setChecked(d.get('include_backs', False))

    def _read_images(self):
        return {
            'enabled': self._images_section.is_enabled(),
            'folder': self._img_folder.folder_setting(),
            'size_label': self._img_size_combo.currentText(),
            'format': self._img_format_combo.currentText(),
            'quality': self._img_quality_spin.value(),
            'filename_format': FILENAME_FORMATS[self._img_filename_combo.currentIndex()][0],
            'rotate': self._img_rotate.isChecked(),
            'bleed': self._img_bleed.isChecked(),
            'separate_versions': self._img_separate.isChecked(),
            'include_backs': self._img_backs.isChecked(),
        }

    # -- PDF ---------------------------------------------------------------

    def _build_pdf_section(self, layout):
        self._pdf_flavor_combo = QComboBox()
        for _, label in PDF_FLAVORS:
            self._pdf_flavor_combo.addItem(label)
        self._pdf_flavor_combo.currentIndexChanged.connect(self._on_pdf_flavor_changed)
        flavor_form = QFormLayout()
        flavor_form.addRow(tr("PE_PDF_FLAVOR_LABEL"), self._pdf_flavor_combo)
        layout.addLayout(flavor_form)

        self._pdf_export_images_cb = QCheckBox(tr("PDF_EXPORT_IMAGES_CHECK"))
        self._pdf_export_images_cb.setChecked(True)
        layout.addWidget(self._pdf_export_images_cb)

        self._pdf_folder = FolderPicker(tr("PDF_IMAGE_FOLDER_LABEL"), self._default_folder())
        layout.addWidget(self._pdf_folder)
        self._pdf_export_images_cb.toggled.connect(self._pdf_folder.setVisible)

        size_form = QFormLayout()
        self._pdf_size_combo = QComboBox()
        self._pdf_size_combo.addItems([label for label, _ in EXPORT_SIZES])
        self._pdf_size_combo.currentIndexChanged.connect(self._update_pdf_format_info)
        size_form.addRow(tr("LABEL_EXPORT_SIZE"), self._pdf_size_combo)
        layout.addLayout(size_form)

        self._pdf_format_frame = QFrame()
        pf_form = QFormLayout(self._pdf_format_frame)
        pf_form.setContentsMargins(0, 0, 0, 0)
        self._pdf_format_combo = QComboBox()
        self._pdf_format_combo.addItems(['png', 'jpeg', 'webp'])
        self._pdf_format_combo.currentTextChanged.connect(
            lambda fmt: self._pdf_quality_spin.setEnabled(fmt in ('jpeg', 'webp'))
        )
        pf_form.addRow(tr("LABEL_FORMAT"), self._pdf_format_combo)
        self._pdf_quality_spin = QSpinBox()
        self._pdf_quality_spin.setRange(1, 100)
        self._pdf_quality_spin.setSuffix("%")
        pf_form.addRow(tr("LABEL_QUALITY"), self._pdf_quality_spin)
        self._pdf_backs = QCheckBox(tr("OPT_INCLUDE_BACKS"))
        pf_form.addRow(tr("LABEL_INCLUDE_BACKS"), self._pdf_backs)
        layout.addWidget(self._pdf_format_frame)

        self._pdf_info_label = QLabel()
        self._pdf_info_label.setStyleSheet("color: #888; font-style: italic; font-size: 9pt;")
        layout.addWidget(self._pdf_info_label)

        self._pdf_vector_text = QCheckBox(tr("PDF_VECTOR_TEXT_CHECK"))
        self._pdf_vector_text.setToolTip(tr("PDF_VECTOR_TEXT_TOOLTIP"))
        layout.addWidget(self._pdf_vector_text)

        self._pdf_output_single = QFrame()
        row = QHBoxLayout(self._pdf_output_single)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(tr("PDF_OUTPUT_LABEL")))
        self._pdf_path_input = QLineEdit()
        row.addWidget(self._pdf_path_input)
        browse_btn = QPushButton(tr("BTN_BROWSE"))
        browse_btn.clicked.connect(lambda: self._browse_pdf_path(self._pdf_path_input))
        row.addWidget(browse_btn)
        layout.addWidget(self._pdf_output_single)

        self._pdf_output_azao = QFrame()
        azao_layout = QVBoxLayout(self._pdf_output_azao)
        azao_layout.setContentsMargins(0, 0, 0, 0)
        azao_layout.addWidget(QLabel(tr("PDF_OUTPUT_FRONT_LABEL")))
        front_row = QHBoxLayout()
        self._pdf_front_path_input = QLineEdit()
        front_row.addWidget(self._pdf_front_path_input)
        front_browse = QPushButton(tr("BTN_BROWSE"))
        front_browse.clicked.connect(lambda: self._browse_pdf_path(self._pdf_front_path_input))
        front_row.addWidget(front_browse)
        azao_layout.addLayout(front_row)
        azao_layout.addWidget(QLabel(tr("PDF_OUTPUT_BACK_LABEL")))
        back_row = QHBoxLayout()
        self._pdf_back_path_input = QLineEdit()
        back_row.addWidget(self._pdf_back_path_input)
        back_browse = QPushButton(tr("BTN_BROWSE"))
        back_browse.clicked.connect(lambda: self._browse_pdf_path(self._pdf_back_path_input))
        back_row.addWidget(back_browse)
        azao_layout.addLayout(back_row)
        layout.addWidget(self._pdf_output_azao)

        self._on_pdf_flavor_changed()

    def _browse_pdf_path(self, line_edit):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("PDF_DLG_SELECT_OUTPUT"), line_edit.text(), "PDF Files (*.pdf)"
        )
        if path:
            line_edit.setText(path)

    def _pdf_flavor_key(self):
        return PDF_FLAVORS[self._pdf_flavor_combo.currentIndex()][0]

    def _on_pdf_flavor_changed(self):
        flavor = self._pdf_flavor_key()
        is_azao = flavor == 'azao'
        is_plain = flavor == 'pdf'
        self._pdf_format_frame.setVisible(is_plain)
        self._pdf_info_label.setVisible(not is_plain)
        self._pdf_vector_text.setVisible(not is_plain)
        self._pdf_output_single.setVisible(not is_azao)
        self._pdf_output_azao.setVisible(is_azao)
        self._update_pdf_format_info()

    def _update_pdf_format_info(self):
        from shoggoth.renderer import trim_dimensions
        flavor = self._pdf_flavor_key()
        fmt = 'png'
        size = _resolve_size(self._pdf_size_combo.currentText())
        w, h = trim_dimensions(size)
        self._pdf_info_label.setText(tr("PDF_FORMAT_INFO").format(fmt=fmt.upper(), w=w, h=h))

    def _pdf_default_filename(self, flavor):
        if flavor == 'azao':
            return 'front.pdf'
        suffix = '_mbprint' if flavor == 'mbprint' else ''
        return f"{self.project.name}{suffix}.pdf"

    def _apply_pdf(self, d):
        self._pdf_section.set_enabled_checked(d['enabled'])
        for i, (key, _) in enumerate(PDF_FLAVORS):
            if key == d.get('flavor', 'pdf'):
                self._pdf_flavor_combo.setCurrentIndex(i)
                break
        self._pdf_export_images_cb.setChecked(d.get('export_images', True))
        self._pdf_folder.set_folder(d.get('folder'))
        self._pdf_size_combo.setCurrentIndex(_size_combo_index(self._pdf_size_combo, d.get('size_label')))
        self._pdf_format_combo.setCurrentText(d.get('format', 'png'))
        self._pdf_quality_spin.setValue(d.get('quality', 100))
        self._pdf_backs.setChecked(d.get('include_backs', False))
        self._pdf_vector_text.setChecked(d.get('vector_text', True))

        flavor = d.get('flavor', 'pdf')
        default_path = str(self.project.folder / self._pdf_default_filename(flavor))
        self._pdf_path_input.setText(d.get('output_path') or default_path)
        self._pdf_front_path_input.setText(d.get('output_path') or default_path)
        self._pdf_back_path_input.setText(
            d.get('back_output_path') or str(self.project.folder / 'back.pdf')
        )

    def _read_pdf(self):
        flavor = self._pdf_flavor_key()
        return {
            'enabled': self._pdf_section.is_enabled(),
            'flavor': flavor,
            'folder': self._pdf_folder.folder_setting(),
            'export_images': self._pdf_export_images_cb.isChecked(),
            'size_label': self._pdf_size_combo.currentText(),
            'format': self._pdf_format_combo.currentText(),
            'quality': self._pdf_quality_spin.value(),
            'include_backs': self._pdf_backs.isChecked(),
            'vector_text': self._pdf_vector_text.isChecked(),
            'output_path': self._pdf_front_path_input.text().strip() if flavor == 'azao'
                           else self._pdf_path_input.text().strip(),
            'back_output_path': self._pdf_back_path_input.text().strip() if flavor == 'azao' else None,
        }

    # -- TTS ---------------------------------------------------------------

    def _build_tts_section(self, layout):
        self._tts_export_images_cb = QCheckBox(tr("TTS_EXPORT_IMAGES_CHECK"))
        self._tts_export_images_cb.setChecked(True)
        layout.addWidget(self._tts_export_images_cb)

        self._tts_folder = FolderPicker(tr("TTS_IMAGE_FOLDER_LABEL"), self._default_folder())
        layout.addWidget(self._tts_folder)
        self._tts_export_images_cb.toggled.connect(self._tts_folder.setVisible)

        from shoggoth.tts_lib import TTS_IMAGE_FORMAT, TTS_IMAGE_SIZE, TTS_IMAGE_QUALITY
        info = QLabel(tr("TTS_FORMAT_INFO").format(
            fmt=TTS_IMAGE_FORMAT.upper(), w=TTS_IMAGE_SIZE['width'], h=TTS_IMAGE_SIZE['height'],
        ))
        info.setStyleSheet("color: #888; font-style: italic; font-size: 9pt;")
        layout.addWidget(info)

        self._tts_sync = QCheckBox(tr("TTS_SEND_TO_TTS"))
        layout.addWidget(self._tts_sync)

    def _apply_tts(self, d):
        self._tts_section.set_enabled_checked(d['enabled'])
        self._tts_export_images_cb.setChecked(d.get('export_images', True))
        self._tts_folder.set_folder(d.get('folder'))
        self._tts_sync.setChecked(d.get('sync', False))

    def _read_tts(self):
        return {
            'enabled': self._tts_section.is_enabled(),
            'folder': self._tts_folder.folder_setting(),
            'export_images': self._tts_export_images_cb.isChecked(),
            'sync': self._tts_sync.isChecked(),
        }

    # -- arkham.build ----------------------------------------------------

    def _build_arkham_build_section(self, layout):
        self._ab_thumbnails_cb = QCheckBox(tr("PE_AB_EXPORT_THUMBNAILS"))
        layout.addWidget(self._ab_thumbnails_cb)

        url_group = QGroupBox(tr("AB_URL_PATTERN_LABEL"))
        url_layout = QVBoxLayout(url_group)
        self._ab_url_input = QLineEdit()
        self._ab_url_input.setPlaceholderText(tr("AB_URL_PATTERN_PLACEHOLDER"))
        url_layout.addWidget(self._ab_url_input)
        hint = QLabel(tr("AB_URL_PATTERN_HINT"))
        hint.setStyleSheet("color: #888; font-size: 9pt;")
        url_layout.addWidget(hint)
        layout.addWidget(url_group)

    def _apply_arkham_build(self, d):
        self._ab_section.set_enabled_checked(d['enabled'])
        self._ab_thumbnails_cb.setChecked(d.get('export_thumbnails', False))
        self._ab_url_input.setText(d.get('url_pattern') or '')

    def _read_arkham_build(self):
        return {
            'enabled': self._ab_section.is_enabled(),
            'export_thumbnails': self._ab_thumbnails_cb.isChecked(),
            'url_pattern': self._ab_url_input.text().strip() or None,
        }

    # -- Guides ------------------------------------------------------------

    def _build_guides_section(self, layout):
        layout.addWidget(QLabel(tr("PE_GUIDES_HINT")))
        self._guides_pdf = QCheckBox(tr("PE_GUIDES_EXPORT_PDF"))
        self._guides_pdf.setChecked(True)
        layout.addWidget(self._guides_pdf)
        self._guides_html = QCheckBox(tr("PE_GUIDES_EXPORT_HTML"))
        self._guides_html.setChecked(True)
        layout.addWidget(self._guides_html)

    def _apply_guides(self, d):
        self._guides_section.set_enabled_checked(d['enabled'])
        self._guides_pdf.setChecked(d.get('export_pdf', True))
        self._guides_html.setChecked(d.get('export_html', True))

    def _read_guides(self):
        return {
            'enabled': self._guides_section.is_enabled(),
            'export_pdf': self._guides_pdf.isChecked(),
            'export_html': self._guides_html.isChecked(),
        }

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def _default_folder(self):
        return self.project.folder / f'Export of {self.project.name}'

    def _apply_profile_to_widgets(self, profile_data, expand):
        self._scope_selector.set_scope(profile_data.get('scope', default_scope()))
        s = profile_data['sections']
        self._apply_images(s['images'])
        self._apply_pdf(s['pdf'])
        self._apply_tts(s['tts'])
        self._apply_arkham_build(s['arkham_build'])
        self._apply_guides(s['guides'])
        for section in getattr(self, '_all_sections', []):
            section.set_expanded(expand)

    def _read_all_sections(self):
        return {
            'images': self._read_images(),
            'pdf': self._read_pdf(),
            'tts': self._read_tts(),
            'arkham_build': self._read_arkham_build(),
            'guides': self._read_guides(),
        }

    def _select_profile(self, index, expand):
        self._current_index = index
        self._apply_profile_to_widgets(self._profiles_data[index], expand=expand)

    def _snapshot_current_profile(self):
        if self._current_index >= 0:
            self._profiles_data[self._current_index]['scope'] = self._scope_selector.read_scope()
            self._profiles_data[self._current_index]['sections'] = self._read_all_sections()

    def _on_profile_changed(self, index):
        if index < 0 or index == self._current_index:
            return
        self._snapshot_current_profile()
        expand = self._profiles_data[index]['id'] in self._new_profile_ids
        self._select_profile(index, expand=expand)

    def _add_profile(self):
        name, ok = QInputDialog.getText(self, tr("PE_BTN_ADD_PROFILE"), tr("PE_NEW_PROFILE_NAME_PROMPT"))
        if not ok or not name.strip():
            return
        self._snapshot_current_profile()
        from uuid import uuid4
        entry = {
            'id': str(uuid4()), 'name': name.strip(),
            'scope': default_scope(), 'sections': default_sections(),
        }
        self._profiles_data.append(entry)
        self._new_profile_ids.add(entry['id'])
        self._profile_combo.addItem(entry['name'])
        self._profile_combo.setCurrentIndex(self._profile_combo.count() - 1)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _run_export(self):
        self._snapshot_current_profile()
        if self._current_index >= 0:
            profile_data = self._profiles_data[self._current_index]
        else:
            # No profile existed yet (brand-new project): read the freshly
            # configured settings and, if this run should be saved, turn them
            # into a first "Default" profile so future opens show the picker.
            profile_data = {'scope': self._scope_selector.read_scope(), 'sections': self._read_all_sections()}
            if self.persist:
                from uuid import uuid4
                profile_data = {'id': str(uuid4()), 'name': 'Default', **profile_data}
                self._profiles_data.append(profile_data)

        from shoggoth.ui.export_runner import run_profile, summarize
        results, errors = run_profile(self, self.project, self.renderer, profile_data)

        if self.persist:
            self.project.data['export_profiles'] = self._profiles_data
            self.project.save_all()

        QMessageBox.information(self, self.windowTitle(), summarize(results, errors))
        self.accept()
