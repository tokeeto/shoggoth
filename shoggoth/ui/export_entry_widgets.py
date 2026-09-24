"""
Per-kind settings panels for one export entry (Images/PDF/TTS/arkham.build/
Guides), used by ProjectExportDialog's entry list: one widget instance is
built per entry (not shared across entries of the same kind, so several
Images entries can hold independent state at once).

Every widget exposes the same pair of methods:
  apply(entry)  -- entry: {'id', 'type', 'scope', 'settings'}; populate the UI
  read() -> {'scope': dict|None, 'settings': dict}
              -- 'scope' is None for kinds with no card scope of their own
                 (arkham.build, Guides -- see export_profile.USES_SCOPE)
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QComboBox, QSpinBox, QCheckBox, QLineEdit, QPushButton, QFileDialog, QFrame,
)

from shoggoth.files import default_export_folder, safe_filename
from shoggoth.i18n import tr
from shoggoth.settings import EXPORT_SIZES
from shoggoth.ui.export_widgets import FilePicker, FolderPicker, ProfileScopeSelector

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


class ImagesEntryWidget(QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        layout = QVBoxLayout(self)

        self._scope_selector = ProfileScopeSelector(project)
        layout.addWidget(self._scope_selector)

        self._folder = FolderPicker(tr("IMG_EXPORT_FOLDER_LABEL"), default_export_folder(project))
        layout.addWidget(self._folder)

        format_group = QGroupBox(tr("GROUP_EXPORT_FORMAT"))
        form = QFormLayout(format_group)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)

        self._size_combo = QComboBox()
        self._size_combo.addItems([label for label, _ in EXPORT_SIZES])
        form.addRow(tr("LABEL_EXPORT_SIZE"), self._size_combo)

        self._format_combo = QComboBox()
        self._format_combo.addItems(['png', 'jpeg', 'webp'])
        self._format_combo.currentTextChanged.connect(
            lambda fmt: self._quality_spin.setEnabled(fmt in ('jpeg', 'webp'))
        )
        form.addRow(tr("LABEL_FORMAT"), self._format_combo)

        self._quality_spin = QSpinBox()
        self._quality_spin.setRange(1, 100)
        self._quality_spin.setSuffix("%")
        form.addRow(tr("LABEL_QUALITY"), self._quality_spin)
        layout.addWidget(format_group)

        naming_group = QGroupBox(tr("IMG_EXPORT_NAMING_LABEL"))
        naming_form = QFormLayout(naming_group)
        self._filename_combo = QComboBox()
        for _, label in FILENAME_FORMATS:
            self._filename_combo.addItem(label)
        naming_form.addRow(tr("IMG_EXPORT_FILENAME_LABEL"), self._filename_combo)
        layout.addWidget(naming_group)

        options_group = QGroupBox(tr("GROUP_EXPORT_OPTIONS"))
        options_form = QFormLayout(options_group)
        self._rotate = QCheckBox(tr("IMG_EXPORT_ROTATE_OPT"))
        options_form.addRow(tr("IMG_EXPORT_ROTATE_LABEL"), self._rotate)
        self._bleed = QCheckBox(tr("OPT_INCLUDE_BLEED"))
        options_form.addRow(tr("LABEL_INCLUDE_BLEED"), self._bleed)
        self._rounded = QCheckBox(tr("OPT_ROUNDED_CORNERS"))
        self._rounded.setToolTip(tr("HELP_ROUNDED_CORNERS"))
        options_form.addRow(tr("LABEL_ROUNDED_CORNERS"), self._rounded)
        self._separate = QCheckBox(tr("OPT_SEPARATE_VERSIONS"))
        options_form.addRow(tr("LABEL_SEPARATE_VERSIONS"), self._separate)
        self._backs = QCheckBox(tr("OPT_INCLUDE_BACKS"))
        options_form.addRow(tr("LABEL_INCLUDE_BACKS"), self._backs)
        layout.addWidget(options_group)

        layout.addStretch()

    def apply(self, entry):
        self._scope_selector.set_scope(entry.get('scope') or {})
        d = entry.get('settings', {})
        self._folder.set_folder(d.get('folder'))
        self._size_combo.setCurrentIndex(_size_combo_index(self._size_combo, d.get('size_label')))
        self._format_combo.setCurrentText(d.get('format', 'png'))
        self._quality_spin.setValue(d.get('quality', 95))
        for i, (key, _) in enumerate(FILENAME_FORMATS):
            if key == d.get('filename_format', 'id'):
                self._filename_combo.setCurrentIndex(i)
                break
        self._rotate.setChecked(d.get('rotate', False))
        self._bleed.setChecked(d.get('bleed', True))
        self._rounded.setChecked(d.get('rounded', False))
        self._separate.setChecked(d.get('separate_versions', False))
        self._backs.setChecked(d.get('include_backs', False))

    def read(self):
        settings = {
            'folder': self._folder.folder_setting(),
            'size_label': self._size_combo.currentText(),
            'format': self._format_combo.currentText(),
            'quality': self._quality_spin.value(),
            'filename_format': FILENAME_FORMATS[self._filename_combo.currentIndex()][0],
            'rotate': self._rotate.isChecked(),
            'bleed': self._bleed.isChecked(),
            'rounded': self._rounded.isChecked(),
            'separate_versions': self._separate.isChecked(),
            'include_backs': self._backs.isChecked(),
        }
        return {'scope': self._scope_selector.read_scope(), 'settings': settings}


class PdfEntryWidget(QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        layout = QVBoxLayout(self)

        from shoggoth.pdf_exporter import check_prince_installed
        if not check_prince_installed():
            hint = QLabel(tr("PE_PRINCE_NOT_INSTALLED"))
            hint.setStyleSheet("color: #c0392b; font-style: italic;")
            hint.setWordWrap(True)
            layout.addWidget(hint)

        self._scope_selector = ProfileScopeSelector(project)
        layout.addWidget(self._scope_selector)

        self._flavor_combo = QComboBox()
        for _, label in PDF_FLAVORS:
            self._flavor_combo.addItem(label)
        self._flavor_combo.currentIndexChanged.connect(self._on_flavor_changed)
        flavor_form = QFormLayout()
        flavor_form.addRow(tr("PE_PDF_FLAVOR_LABEL"), self._flavor_combo)
        layout.addLayout(flavor_form)

        self._export_images_cb = QCheckBox(tr("PDF_EXPORT_IMAGES_CHECK"))
        self._export_images_cb.setChecked(True)
        layout.addWidget(self._export_images_cb)

        self._folder = FolderPicker(tr("PDF_IMAGE_FOLDER_LABEL"), default_export_folder(project))
        layout.addWidget(self._folder)
        self._export_images_cb.toggled.connect(self._folder.setVisible)

        size_form = QFormLayout()
        self._size_combo = QComboBox()
        self._size_combo.addItems([label for label, _ in EXPORT_SIZES])
        self._size_combo.currentIndexChanged.connect(self._update_format_info)
        size_form.addRow(tr("LABEL_EXPORT_SIZE"), self._size_combo)
        layout.addLayout(size_form)

        # Format/quality widgets are shared between the 'pdf' and 'azao'
        # flavors (mbprint is always fixed png/100, no controls shown); each
        # flavor keeps its own remembered format+quality in
        # `_format_by_flavor`, swapped into these widgets on flavor change.
        self._format_by_flavor = {'pdf': ('png', 100), 'azao': ('jpeg', 95)}

        self._format_frame = QFrame()
        pf_form = QFormLayout(self._format_frame)
        pf_form.setContentsMargins(0, 0, 0, 0)
        self._format_combo = QComboBox()
        self._format_combo.addItems(['png', 'jpeg', 'webp'])
        self._format_combo.currentTextChanged.connect(
            lambda fmt: self._quality_spin.setEnabled(fmt in ('jpeg', 'webp'))
        )
        pf_form.addRow(tr("LABEL_FORMAT"), self._format_combo)
        self._quality_spin = QSpinBox()
        self._quality_spin.setRange(1, 100)
        self._quality_spin.setSuffix("%")
        pf_form.addRow(tr("LABEL_QUALITY"), self._quality_spin)
        self._backs = QCheckBox(tr("OPT_INCLUDE_BACKS"))
        pf_form.addRow(tr("LABEL_INCLUDE_BACKS"), self._backs)
        layout.addWidget(self._format_frame)

        self._info_label = QLabel()
        self._info_label.setStyleSheet("color: #888; font-style: italic; font-size: 9pt;")
        layout.addWidget(self._info_label)

        self._vector_text = QCheckBox(tr("PDF_VECTOR_TEXT_CHECK"))
        self._vector_text.setToolTip(tr("PDF_VECTOR_TEXT_TOOLTIP"))
        layout.addWidget(self._vector_text)

        self._rounded = QCheckBox(tr("PDF_ROUNDED_CORNERS_CHECK"))
        self._rounded.setToolTip(tr("PDF_ROUNDED_CORNERS_TOOLTIP"))
        layout.addWidget(self._rounded)

        self._output_single = QFrame()
        row = QHBoxLayout(self._output_single)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(tr("PDF_OUTPUT_LABEL")))
        self._path_input = QLineEdit()
        row.addWidget(self._path_input)
        browse_btn = QPushButton(tr("BTN_BROWSE"))
        browse_btn.clicked.connect(lambda: self._browse_path(self._path_input))
        row.addWidget(browse_btn)
        layout.addWidget(self._output_single)

        self._output_azao = QFrame()
        azao_layout = QVBoxLayout(self._output_azao)
        azao_layout.setContentsMargins(0, 0, 0, 0)
        azao_layout.addWidget(QLabel(tr("PDF_OUTPUT_FRONT_LABEL")))
        front_row = QHBoxLayout()
        self._front_path_input = QLineEdit()
        front_row.addWidget(self._front_path_input)
        front_browse = QPushButton(tr("BTN_BROWSE"))
        front_browse.clicked.connect(lambda: self._browse_path(self._front_path_input))
        front_row.addWidget(front_browse)
        azao_layout.addLayout(front_row)
        azao_layout.addWidget(QLabel(tr("PDF_OUTPUT_BACK_LABEL")))
        back_row = QHBoxLayout()
        self._back_path_input = QLineEdit()
        back_row.addWidget(self._back_path_input)
        back_browse = QPushButton(tr("BTN_BROWSE"))
        back_browse.clicked.connect(lambda: self._browse_path(self._back_path_input))
        back_row.addWidget(back_browse)
        azao_layout.addLayout(back_row)
        layout.addWidget(self._output_azao)

        layout.addStretch()
        self._on_flavor_changed()

    def _browse_path(self, line_edit):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("PDF_DLG_SELECT_OUTPUT"), line_edit.text(), "PDF Files (*.pdf)"
        )
        if path:
            line_edit.setText(path)

    def _flavor_key(self):
        return PDF_FLAVORS[self._flavor_combo.currentIndex()][0]

    def _on_flavor_changed(self):
        flavor = self._flavor_key()
        is_azao = flavor == 'azao'
        is_plain = flavor == 'pdf'
        has_format_controls = is_plain or is_azao
        self._sync_format_quality_widgets(flavor)
        self._format_frame.setVisible(has_format_controls)
        self._format_frame.layout().setRowVisible(self._backs, is_plain)
        self._rounded.setVisible(is_plain)
        self._info_label.setVisible(not has_format_controls)
        self._output_single.setVisible(not is_azao)
        self._output_azao.setVisible(is_azao)
        self._update_format_info()

    def _sync_format_quality_widgets(self, new_flavor):
        prev_flavor = getattr(self, '_format_flavor', None)
        if prev_flavor in self._format_by_flavor:
            self._format_by_flavor[prev_flavor] = (
                self._format_combo.currentText(), self._quality_spin.value()
            )
        self._format_flavor = new_flavor
        if new_flavor in self._format_by_flavor:
            fmt, quality = self._format_by_flavor[new_flavor]
            self._format_combo.setCurrentText(fmt)
            self._quality_spin.setValue(quality)

    def _update_format_info(self):
        from shoggoth.renderer import trim_dimensions
        size = _resolve_size(self._size_combo.currentText())
        w, h = trim_dimensions(size)
        self._info_label.setText(tr("PDF_FORMAT_INFO").format(fmt='PNG', w=w, h=h))

    def _default_filename(self, flavor):
        if flavor == 'azao':
            return 'front.pdf'
        suffix = '_mbprint' if flavor == 'mbprint' else ''
        return f"{safe_filename(self.project.name)}{suffix}.pdf"

    def apply(self, entry):
        self._scope_selector.set_scope(entry.get('scope') or {})
        d = entry.get('settings', {})
        self._format_by_flavor = {
            'pdf': (d.get('format', 'png'), d.get('quality', 100)),
            'azao': (d.get('azao_format', 'jpeg'), d.get('azao_quality', 95)),
        }
        self._format_flavor = None
        for i, (key, _) in enumerate(PDF_FLAVORS):
            if key == d.get('flavor', 'pdf'):
                self._flavor_combo.setCurrentIndex(i)
                break
        self._export_images_cb.setChecked(d.get('export_images', True))
        self._folder.set_folder(d.get('folder'))
        self._size_combo.setCurrentIndex(_size_combo_index(self._size_combo, d.get('size_label')))
        self._backs.setChecked(d.get('include_backs', False))
        self._rounded.setChecked(d.get('rounded', False))
        self._vector_text.setChecked(d.get('vector_text', True))
        self._on_flavor_changed()

        flavor = d.get('flavor', 'pdf')
        default_path = str(self.project.folder / self._default_filename(flavor))
        self._path_input.setText(d.get('output_path') or default_path)
        self._front_path_input.setText(d.get('output_path') or default_path)
        self._back_path_input.setText(
            d.get('back_output_path') or str(self.project.folder / 'back.pdf')
        )

    def read(self):
        flavor = self._flavor_key()
        self._sync_format_quality_widgets(flavor)
        pdf_format, pdf_quality = self._format_by_flavor['pdf']
        azao_format, azao_quality = self._format_by_flavor['azao']
        settings = {
            'flavor': flavor,
            'folder': self._folder.folder_setting(),
            'export_images': self._export_images_cb.isChecked(),
            'size_label': self._size_combo.currentText(),
            'format': pdf_format,
            'quality': pdf_quality,
            'azao_format': azao_format,
            'azao_quality': azao_quality,
            'include_backs': self._backs.isChecked(),
            'rounded': self._rounded.isChecked(),
            'vector_text': self._vector_text.isChecked(),
            'output_path': self._front_path_input.text().strip() if flavor == 'azao'
                           else self._path_input.text().strip(),
            'back_output_path': self._back_path_input.text().strip() if flavor == 'azao' else None,
        }
        return {'scope': self._scope_selector.read_scope(), 'settings': settings}


class TtsEntryWidget(QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        layout = QVBoxLayout(self)

        self._scope_selector = ProfileScopeSelector(project)
        layout.addWidget(self._scope_selector)

        self._export_images_cb = QCheckBox(tr("TTS_EXPORT_IMAGES_CHECK"))
        self._export_images_cb.setChecked(True)
        layout.addWidget(self._export_images_cb)

        self._folder = FolderPicker(tr("TTS_IMAGE_FOLDER_LABEL"), default_export_folder(project))
        layout.addWidget(self._folder)
        self._export_images_cb.toggled.connect(self._folder.setVisible)

        from shoggoth.tts_lib import TTS_IMAGE_FORMAT, TTS_IMAGE_SIZE, TTS_IMAGE_QUALITY
        info = QLabel(tr("TTS_FORMAT_INFO").format(
            fmt=TTS_IMAGE_FORMAT.upper(), w=TTS_IMAGE_SIZE['width'], h=TTS_IMAGE_SIZE['height'],
        ))
        info.setStyleSheet("color: #888; font-style: italic; font-size: 9pt;")
        layout.addWidget(info)

        self._sync = QCheckBox(tr("TTS_SEND_TO_TTS"))
        layout.addWidget(self._sync)

        layout.addSpacing(10)

        file_label = QLabel(tr("TTS_UPDATE_FILE_LABEL"))
        layout.addWidget(file_label)

        self._file = FilePicker(tr("TTS_FILE_PLACEHOLDER"))
        layout.addWidget(self._file)

        layout.addStretch()

    def apply(self, entry):
        self._scope_selector.set_scope(entry.get('scope') or {})
        d = entry.get('settings', {})
        self._export_images_cb.setChecked(d.get('export_images', True))
        self._folder.set_folder(d.get('folder'))
        self._sync.setChecked(d.get('sync', False))

    def read(self):
        settings = {
            'folder': self._folder.folder_setting(),
            'export_images': self._export_images_cb.isChecked(),
            'sync': self._sync.isChecked(),
        }
        return {'scope': self._scope_selector.read_scope(), 'settings': settings}


class ArkhamBuildEntryWidget(QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        layout = QVBoxLayout(self)

        self._thumbnails_cb = QCheckBox(tr("PE_AB_EXPORT_THUMBNAILS"))
        layout.addWidget(self._thumbnails_cb)

        url_group = QGroupBox(tr("AB_URL_PATTERN_LABEL"))
        url_layout = QVBoxLayout(url_group)
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText(tr("AB_URL_PATTERN_PLACEHOLDER"))
        url_layout.addWidget(self._url_input)
        hint = QLabel(tr("AB_URL_PATTERN_HINT"))
        hint.setStyleSheet("color: #888; font-size: 9pt;")
        url_layout.addWidget(hint)
        layout.addWidget(url_group)

        layout.addStretch()

    def apply(self, entry):
        d = entry.get('settings', {})
        self._thumbnails_cb.setChecked(d.get('export_thumbnails', False))
        self._url_input.setText(d.get('url_pattern') or '')

    def read(self):
        settings = {
            'export_thumbnails': self._thumbnails_cb.isChecked(),
            'url_pattern': self._url_input.text().strip() or None,
        }
        return {'scope': None, 'settings': settings}


class GuidesEntryWidget(QWidget):
    def __init__(self, project=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("PE_GUIDES_HINT")))
        self._pdf = QCheckBox(tr("PE_GUIDES_EXPORT_PDF"))
        self._pdf.setChecked(True)
        layout.addWidget(self._pdf)
        self._html = QCheckBox(tr("PE_GUIDES_EXPORT_HTML"))
        self._html.setChecked(True)
        layout.addWidget(self._html)
        layout.addStretch()

    def apply(self, entry):
        d = entry.get('settings', {})
        self._pdf.setChecked(d.get('export_pdf', True))
        self._html.setChecked(d.get('export_html', True))

    def read(self):
        settings = {
            'export_pdf': self._pdf.isChecked(),
            'export_html': self._html.isChecked(),
        }
        return {'scope': None, 'settings': settings}


ENTRY_WIDGET_CLASSES = {
    'images': ImagesEntryWidget,
    'pdf': PdfEntryWidget,
    'tts': TtsEntryWidget,
    'arkham_build': ArkhamBuildEntryWidget,
    'guides': GuidesEntryWidget,
}


def build_entry_widget(kind, project, parent=None):
    if kind == 'publish':
        from shoggoth.ui.cloud.entry_widget import PublishEntryWidget
        return PublishEntryWidget(project, parent)
    return ENTRY_WIDGET_CLASSES[kind](project, parent)
