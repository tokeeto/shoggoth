"""Guide editor — markdown-based section editing with PDF preview."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QTextEdit, QSplitter, QFileDialog,
    QFrame, QMessageBox, QLineEdit, QStackedWidget,
    QListWidget, QListWidgetItem, QComboBox, QSizePolicy, QDialog,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QPixmap, QTextCursor,
)

import re
from shoggoth.i18n import tr
from shoggoth.guide import SECTION_TYPES, GuideSection


def get_section_label(stype: str) -> str:
    """Return the translated label for a section type."""
    return {
        'intro': tr('GUIDE_SECTION_INTRO'),
        'prelude': tr('GUIDE_SECTION_PRELUDE'),
        'interlude': tr('GUIDE_SECTION_INTERLUDE'),
        'scenario': tr('GUIDE_SECTION_SCENARIO'),
        'blank': tr('GUIDE_SECTION_BLANK'),
        'cover': tr('GUIDE_SECTION_COVER'),
    }.get(stype, stype)

SECTION_COLORS = {
    'intro': '#4a7c59',
    'prelude': '#2d5b58',
    'interlude': '#7c4a6e',
    'scenario': '#3d5a8a',
    'blank': '#666666',
    'cover': '#8a5a3d',
}


# ── Markdown syntax highlighter ───────────────────────────────────────────────

class MarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)

        heading_fmt = QTextCharFormat()
        heading_fmt.setFontWeight(QFont.Bold)
        heading_fmt.setForeground(QColor("#2d5b58"))

        bold_fmt = QTextCharFormat()
        bold_fmt.setFontWeight(QFont.Bold)

        italic_fmt = QTextCharFormat()
        italic_fmt.setFontItalic(True)

        trait_fmt = QTextCharFormat()
        trait_fmt.setFontWeight(QFont.Bold)
        trait_fmt.setFontItalic(True)
        trait_fmt.setForeground(QColor("#5a3d7c"))

        block_fmt = QTextCharFormat()
        block_fmt.setForeground(QColor("#7c4a6e"))
        block_fmt.setFontWeight(QFont.Bold)

        card_ref_fmt = QTextCharFormat()
        card_ref_fmt.setForeground(QColor("#1a7a8a"))
        card_ref_fmt.setFontWeight(QFont.Bold)

        project_ref_fmt = QTextCharFormat()
        project_ref_fmt.setForeground(QColor("#8a6a1a"))
        project_ref_fmt.setFontWeight(QFont.Bold)

        self._rules = [
            (re.compile(r'^#{1,6}\s.*$'), heading_fmt),
            # italic before bold so bold wins on overlap
            (re.compile(r'(?<!\*)\*(?!\*)[^*\n]+(?<!\*)\*(?!\*)'), italic_fmt),
            (re.compile(r'\*\*[^*\n]+\*\*'), bold_fmt),
            (re.compile(r'\[\[[^\]\n]+\]\]'), trait_fmt),
            (re.compile(r'\[card:[^\]]+\]'), card_ref_fmt),
            (re.compile(r'\[(?:enc|encounter):[^\]]+\]'), card_ref_fmt),
            (re.compile(r'\[project:[^\]]+\]'), project_ref_fmt),
            (re.compile(r'^:::.*$'), block_fmt),
        ]

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ── PDF rendering thread ──────────────────────────────────────────────────────

class PDFPageRenderer(QThread):
    page_ready = Signal(int, object)

    def __init__(self, guide, page_number):
        super().__init__()
        self.guide = guide
        self.page_number = page_number
        self._stop = False

    def run(self):
        if self._stop:
            return
        try:
            img = self.guide.get_page(self.page_number)
            if self._stop:
                return
            from PIL.ImageQt import ImageQt
            qimage = ImageQt(img)
            pixmap = QPixmap.fromImage(qimage)
            if not self._stop:
                self.page_ready.emit(self.page_number, pixmap)
        except Exception as e:
            print(f"Error rendering page {self.page_number}: {e}")

    def stop(self):
        self._stop = True


# ── Zoomable / pannable PDF viewer ────────────────────────────────────────────

class ZoomablePDFViewer(QFrame):
    def __init__(self):
        super().__init__()
        self.pixmap = None
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self._panning = False
        self._last_pos = None
        self.setFrameStyle(QFrame.Box | QFrame.Sunken)
        self.setMinimumSize(300, 400)
        self.setMouseTracking(True)

    def set_pixmap(self, pixmap):
        self.pixmap = pixmap
        if pixmap and pixmap.width() > 0 and pixmap.height() > 0:
            w_ratio = (self.width() - 4) / pixmap.width()
            h_ratio = (self.height() - 4) / pixmap.height()
            self.zoom_level = min(w_ratio, h_ratio)
        self.pan_x = 0
        self.pan_y = 0
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.pixmap:
            return
        from PySide6.QtGui import QPainter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        scaled = self.pixmap.scaled(
            int(self.pixmap.width() * self.zoom_level),
            int(self.pixmap.height() * self.zoom_level),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2 + self.pan_x
        y = (self.height() - scaled.height()) // 2 + self.pan_y
        painter.drawPixmap(x, y, scaled)

    def wheelEvent(self, event):
        d = event.angleDelta().y()
        self.zoom_level = min(self.zoom_level * 1.1, 5.0) if d > 0 else max(self.zoom_level / 1.1, 0.1)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._panning = True
            self._last_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._panning and self._last_pos:
            d = event.pos() - self._last_pos
            self.pan_x += d.x()
            self.pan_y += d.y()
            self._last_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._panning = False
            self._last_pos = None
            self.setCursor(Qt.ArrowCursor)

    def reset_view(self):
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.update()


# ── Overview panel ────────────────────────────────────────────────────────────

class GuideOverviewPanel(QWidget):
    """Section list with guide metadata. Double-click or Edit button opens a section."""

    section_edit_requested = Signal(str)  # section_id

    def __init__(self, guide, parent=None):
        super().__init__(parent)
        self.guide = guide
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Guide name
        layout.addWidget(QLabel(tr("LABEL_GUIDE_NAME")))
        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._on_name_changed)
        layout.addWidget(self._name_edit)

        # Front page
        layout.addWidget(QLabel(tr("LABEL_FRONT_PAGE")))
        fp_row = QHBoxLayout()
        self._fp_edit = QLineEdit()
        self._fp_edit.setPlaceholderText(tr("PLACEHOLDER_COVER_IMAGE_PATH"))
        self._fp_edit.textChanged.connect(self._on_fp_changed)
        fp_btn = QPushButton("…")
        fp_btn.setFixedWidth(28)
        fp_btn.clicked.connect(self._browse_front_page)
        fp_row.addWidget(self._fp_edit)
        fp_row.addWidget(fp_btn)
        layout.addLayout(fp_row)

        # Section list
        layout.addWidget(QLabel(tr("LABEL_SECTIONS")))
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list, stretch=1)

        # Edit button row
        edit_row = QHBoxLayout()
        edit_btn = QPushButton(tr("BTN_EDIT_SECTION"))
        edit_btn.clicked.connect(self._on_edit_clicked)
        edit_row.addWidget(edit_btn)
        up_btn = QPushButton("▲")
        up_btn.setFixedWidth(30)
        up_btn.clicked.connect(self._move_up)
        down_btn = QPushButton("▼")
        down_btn.setFixedWidth(30)
        down_btn.clicked.connect(self._move_down)
        del_btn = QPushButton(tr("BTN_DELETE"))
        del_btn.clicked.connect(self._delete_section)
        edit_row.addWidget(up_btn)
        edit_row.addWidget(down_btn)
        edit_row.addStretch()
        edit_row.addWidget(del_btn)
        layout.addLayout(edit_row)

        # Add section buttons
        add_lbl = QLabel(tr("LABEL_ADD_SECTION"))
        add_lbl.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout.addWidget(add_lbl)
        for stype in SECTION_TYPES:
            btn = QPushButton(get_section_label(stype))
            color = SECTION_COLORS.get(stype, '#666')
            btn.setStyleSheet(
                f"QPushButton {{ color: white; background: {color}; border-radius: 3px; padding: 2px; }}"
                f"QPushButton:hover {{ background: {color}cc; }}"
            )
            btn.clicked.connect(lambda checked=False, t=stype: self._add_section(t))
            layout.addWidget(btn)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        # Export buttons
        export_row = QHBoxLayout()
        export_pdf_btn = QPushButton(tr("BTN_EXPORT_PDF"))
        export_pdf_btn.clicked.connect(self._export_pdf)
        export_row.addWidget(export_pdf_btn)
        export_html_btn = QPushButton(tr("BTN_EXPORT_HTML"))
        export_html_btn.clicked.connect(self._export_html)
        export_row.addWidget(export_html_btn)
        layout.addLayout(export_row)

    def refresh(self):
        self._name_edit.blockSignals(True)
        self._name_edit.setText(self.guide.name)
        self._name_edit.blockSignals(False)
        self._fp_edit.blockSignals(True)
        self._fp_edit.setText(self.guide.front_page)
        self._fp_edit.blockSignals(False)

        selected_id = None
        item = self._list.currentItem()
        if item:
            selected_id = item.data(Qt.UserRole)

        self._list.clear()
        for s in self.guide.sections:
            color = SECTION_COLORS.get(s.type, '#666')
            label = get_section_label(s.type)
            item = QListWidgetItem(f"[{label}]  {s.name}")
            item.setData(Qt.UserRole, s.id)
            item.setForeground(QColor(color))
            self._list.addItem(item)

        # Restore selection
        if selected_id:
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.UserRole) == selected_id:
                    self._list.setCurrentRow(i)
                    return
        if self._list.count():
            self._list.setCurrentRow(0)

    def _current_id(self):
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _on_name_changed(self, text):
        self.guide.name = text
        self.guide.project.save_all()

    def _on_fp_changed(self, text):
        self.guide.front_page = text
        self.guide.project.save_all()

    def _browse_front_page(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("DLG_SELECT_FRONT_PAGE"), str(self.guide.project.folder),
            "Images (*.png *.jpg *.jpeg *.webp *.avif)",
        )
        if path:
            self._fp_edit.setText(path)

    def _add_section(self, section_type: str):
        name = get_section_label(section_type)
        sections = self.guide.sections
        es_id = None
        if section_type == 'scenario':
            dlg = ScenarioEncounterPickerDialog(self.guide, self)
            if dlg.exec() != QDialog.Accepted:
                return
            es_id = dlg.selected_id()
        new_section = GuideSection.new(section_type, name, encounter_set_id=es_id)
        sections.append(new_section)
        self.guide.save_sections(sections)
        self.refresh()
        # Select and open the newly added section
        self.section_edit_requested.emit(new_section.id)

    def _delete_section(self):
        sid = self._current_id()
        if sid is None:
            return
        sections = [s for s in self.guide.sections if s.id != sid]
        self.guide.save_sections(sections)
        self.refresh()

    def _move_up(self):
        sid = self._current_id()
        if not sid:
            return
        sections = self.guide.sections
        idx = next((i for i, s in enumerate(sections) if s.id == sid), None)
        if idx is not None and idx > 0:
            sections[idx - 1], sections[idx] = sections[idx], sections[idx - 1]
            self.guide.save_sections(sections)
            self.refresh()

    def _move_down(self):
        sid = self._current_id()
        if not sid:
            return
        sections = self.guide.sections
        idx = next((i for i, s in enumerate(sections) if s.id == sid), None)
        if idx is not None and idx < len(sections) - 1:
            sections[idx], sections[idx + 1] = sections[idx + 1], sections[idx]
            self.guide.save_sections(sections)
            self.refresh()

    def _on_double_click(self, item):
        self.section_edit_requested.emit(item.data(Qt.UserRole))

    def _on_edit_clicked(self):
        sid = self._current_id()
        if sid:
            self.section_edit_requested.emit(sid)

    def _export_pdf(self):
        self.guide.render_to_file()
        QMessageBox.information(
            self, tr("DLG_EXPORT_COMPLETE"),
            tr("MSG_PDF_EXPORTED").format(path=self.guide.target_path),
        )

    def _export_html(self):
        html = self.guide.to_html()
        html_path = self.guide.target_path.with_suffix('.html')
        html_path.write_text(html, encoding='utf-8')
        QMessageBox.information(
            self, tr("DLG_EXPORT_COMPLETE"),
            tr("MSG_HTML_EXPORTED").format(html_path=html_path),
        )


# ── Scenario encounter set picker dialog ──────────────────────────────────────

class ScenarioEncounterPickerDialog(QDialog):
    """Pick an encounter set when creating a new scenario section."""

    def __init__(self, guide, parent=None):
        super().__init__(parent)
        self.guide = guide
        self.setWindowTitle(tr("DLG_CHOOSE_ENCOUNTER_FOR_SCENARIO"))
        self.setMinimumSize(300, 350)
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("LABEL_SELECT_ENCOUNTER_FOR_SCENARIO")))
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self._list, stretch=1)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton(tr("DLG_OK"))
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(tr("DLG_CANCEL"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _populate(self):
        none_item = QListWidgetItem(tr("LABEL_NONE"))
        none_item.setData(Qt.UserRole, None)
        self._list.addItem(none_item)
        self._list.setCurrentRow(0)
        try:
            for es in self.guide.project.encounter_sets:
                item = QListWidgetItem(es.name)
                item.setData(Qt.UserRole, es.id)
                self._list.addItem(item)
        except Exception:
            pass

    def selected_id(self):
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item else None


# ── Card picker dialog ────────────────────────────────────────────────────────

class CardPickerDialog(QDialog):
    def __init__(self, guide, parent=None):
        super().__init__(parent)
        self.guide = guide
        self._all_cards = []
        self.setWindowTitle(tr("DLG_INSERT_CARD_REF"))
        self.setMinimumSize(320, 420)
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setPlaceholderText(tr("PLACEHOLDER_SEARCH_CARDS"))
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self._list, stretch=1)

        prop_row = QHBoxLayout()
        prop_row.addWidget(QLabel(tr("LABEL_PROPERTY")))
        self._prop_edit = QLineEdit("name")
        prop_row.addWidget(self._prop_edit)
        layout.addLayout(prop_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        insert_btn = QPushButton(tr("BTN_INSERT"))
        insert_btn.setDefault(True)
        insert_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(tr("DLG_CANCEL"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(insert_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _populate(self):
        try:
            self._all_cards = list(self.guide.project.cards)
        except Exception:
            self._all_cards = []
        self._filter('')

    def _filter(self, text):
        self._list.clear()
        q = text.lower()
        for card in self._all_cards:
            if not q or q in card.name.lower():
                item = QListWidgetItem(card.name)
                item.setData(Qt.UserRole, card.id)
                self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def result_snippet(self):
        item = self._list.currentItem()
        if not item:
            return None
        card_id = item.data(Qt.UserRole)
        prop = self._prop_edit.text().strip() or 'name'
        return f'[card:{card_id}:{prop}]'


# ── Encounter set picker dialog ───────────────────────────────────────────────

class EncounterPickerDialog(QDialog):
    def __init__(self, guide, parent=None):
        super().__init__(parent)
        self.guide = guide
        self._all_sets = []
        self.setWindowTitle(tr("DLG_INSERT_ENCOUNTER_REF"))
        self.setMinimumSize(320, 360)
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setPlaceholderText(tr("PLACEHOLDER_SEARCH_ENCOUNTER_SETS"))
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self._list, stretch=1)

        prop_row = QHBoxLayout()
        prop_row.addWidget(QLabel(tr("LABEL_PROPERTY")))
        self._prop_edit = QLineEdit("icon")
        prop_row.addWidget(self._prop_edit)
        layout.addLayout(prop_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        insert_btn = QPushButton(tr("BTN_INSERT"))
        insert_btn.setDefault(True)
        insert_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(tr("DLG_CANCEL"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(insert_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _populate(self):
        try:
            self._all_sets = list(self.guide.project.encounter_sets)
        except Exception:
            self._all_sets = []
        self._filter('')

    def _filter(self, text):
        self._list.clear()
        q = text.lower()
        for es in self._all_sets:
            if not q or q in es.name.lower():
                item = QListWidgetItem(es.name)
                item.setData(Qt.UserRole, es.id)
                self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def result_snippet(self):
        item = self._list.currentItem()
        if not item:
            return None
        es_id = item.data(Qt.UserRole)
        prop = self._prop_edit.text().strip() or 'icon'
        return f'[encounter:{es_id}:{prop}]'


# ── Markdown-aware text editor ────────────────────────────────────────────────

class MarkdownEditor(QTextEdit):
    """QTextEdit with Ctrl+B/I/T formatting shortcuts and Ctrl+1-5 headings."""

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if mods == Qt.ControlModifier:
            if key == Qt.Key_B:
                self._wrap('**', '**')
                return
            elif key == Qt.Key_I:
                self._wrap('*', '*')
                return
            elif key == Qt.Key_T:
                self._wrap('[[', ']]')
                return
            elif Qt.Key_1 <= key <= Qt.Key_5:
                self._set_heading(key - Qt.Key_0)
                return
        super().keyPressEvent(event)

    def _wrap(self, open_m: str, close_m: str):
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.insertText(open_m + cursor.selectedText() + close_m)
        else:
            cursor.insertText(open_m + close_m)
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, len(close_m))
            self.setTextCursor(cursor)

    def _set_heading(self, level: int):
        cursor = self.textCursor()
        cursor.select(QTextCursor.LineUnderCursor)
        line = cursor.selectedText()
        stripped = re.sub(r'^#{1,6}\s*', '', line)
        cursor.insertText('#' * level + ' ' + stripped)


# ── Section editor panel ──────────────────────────────────────────────────────

class SectionEditorPanel(QWidget):
    """Markdown editor for a single guide section."""

    back_requested = Signal()
    content_changed = Signal()

    def __init__(self, guide, section_id: str, parent=None):
        super().__init__(parent)
        self.guide = guide
        self.section_id = section_id
        self._loading = False
        self.save_timer = None
        self._setup_ui()
        self._load()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Back button + section name
        top_row = QHBoxLayout()
        back_btn = QPushButton(tr("BTN_BACK_SECTIONS"))
        back_btn.setFixedWidth(100)
        back_btn.clicked.connect(self.back_requested)
        top_row.addWidget(back_btn)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(tr("PLACEHOLDER_SECTION_NAME"))
        self._name_edit.textChanged.connect(self._on_name_changed)
        top_row.addWidget(self._name_edit)
        layout.addLayout(top_row)

        # Encounter set dropdown (scenario sections only)
        self._encounter_row = QWidget()
        enc_layout = QHBoxLayout(self._encounter_row)
        enc_layout.setContentsMargins(0, 0, 0, 0)
        enc_layout.addWidget(QLabel(tr("LABEL_LINKED_ENCOUNTER_SET")))
        self._encounter_combo = QComboBox()
        self._encounter_combo.currentIndexChanged.connect(self._on_encounter_changed)
        enc_layout.addWidget(self._encounter_combo)
        self._encounter_row.hide()
        layout.addWidget(self._encounter_row)

        # Template insert toolbar
        toolbar = QHBoxLayout()
        toolbar_lbl = QLabel(tr("LABEL_INSERT"))
        toolbar_lbl.setStyleSheet("font-size: 8pt; color: gray;")
        toolbar.addWidget(toolbar_lbl)
        self._insert_combo = QComboBox()
        self._insert_combo.setFixedHeight(24)
        for label, snippet in [
            (tr("COMBO_STORY"),       ":::story\n*Flavor text here.*\n:::\n\n"),
            (tr("COMBO_SETUP"),       None),  # generated dynamically from linked encounter set
            (tr("COMBO_RESOLUTION"),  ":::resolution\n## DO NOT READ<br>until end of scenario\n\n**If no resolution was reached (each investigator resigned or was defeated):** You all died. Tough luck.\n\n- The investigators lost the campaign.\n\n**Resolution 1**: *Huraa!*\n\n- Each investigator earns experience equal to the Victory X value of each card in the victory display.\n- The investigators win the campaign. Proceed to **Interlude 1 - Title Here**.\n:::\n\n"),
            (tr("COMBO_CODEX"),       ":::codex\n**Rule name:** Rule description.\n:::\n\n"),
            (tr("COMBO_TOC"),         ":::toc\n:::\n\n"),
            (tr("COMBO_INDENT"),      ":::indent\n\n:::\n\n"),
            (tr("COMBO_CENTER"),      ":::center\n\n:::\n\n"),
            (tr("COMBO_RIGHT"),       ":::right\n\n:::\n\n"),
            (tr("COMBO_IMAGE_UP"),    ":::image-top\n/path/to/image.png\n:::\n\n"),
            (tr("COMBO_IMAGE_DOWN"),  ":::image-bottom\n/path/to/image.png\n:::\n\n"),
        ]:
            self._insert_combo.addItem(label, snippet)
        toolbar.addWidget(self._insert_combo)
        insert_btn = QPushButton(tr("BTN_INSERT"))
        insert_btn.setFixedHeight(24)
        insert_btn.setStyleSheet("font-size: 8pt;")
        insert_btn.clicked.connect(self._insert_selected_snippet)
        toolbar.addWidget(insert_btn)
        card_btn = QPushButton(tr("BTN_CARD_REF"))
        card_btn.setFixedHeight(24)
        card_btn.setStyleSheet("font-size: 8pt; color: #1a7a8a;")
        card_btn.clicked.connect(self._insert_card_ref)
        toolbar.addWidget(card_btn)
        enc_btn = QPushButton(tr("BTN_ENC_REF"))
        enc_btn.setFixedHeight(24)
        enc_btn.setStyleSheet("font-size: 8pt; color: #1a7a8a;")
        enc_btn.clicked.connect(self._insert_encounter_ref)
        toolbar.addWidget(enc_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Markdown editor
        self._md_editor = MarkdownEditor()
        self._md_editor.setAcceptRichText(False)
        self._md_editor.setFont(QFont("Courier", 10))
        MarkdownHighlighter(self._md_editor.document())
        self._md_editor.textChanged.connect(self._on_markdown_changed)
        layout.addWidget(self._md_editor, stretch=1)

    def _load(self):
        section = next((s for s in self.guide.sections if s.id == self.section_id), None)
        if section is None:
            return
        self._loading = True
        self._name_edit.setText(section.name or '')

        if section.type == 'scenario':
            self._encounter_row.show()
            self._encounter_combo.blockSignals(True)
            self._encounter_combo.clear()
            self._encounter_combo.addItem(tr("LABEL_NONE"), None)
            try:
                for es in self.guide.project.encounter_sets:
                    self._encounter_combo.addItem(es.name, es.id)
            except Exception:
                pass
            if section.encounter_set_id:
                for i in range(self._encounter_combo.count()):
                    if self._encounter_combo.itemData(i) == section.encounter_set_id:
                        self._encounter_combo.setCurrentIndex(i)
                        break
            self._encounter_combo.blockSignals(False)
        else:
            self._encounter_row.hide()

        self._md_editor.blockSignals(True)
        self._md_editor.setPlainText(section.markdown or '')
        self._md_editor.blockSignals(False)
        self._loading = False

    def _insert_selected_snippet(self):
        snippet = self._insert_combo.currentData()
        if snippet is None:
            snippet = self._make_setup_snippet()
        if snippet:
            self._insert_snippet(snippet)

    def _make_setup_snippet(self) -> str:
        section = next((s for s in self.guide.sections if s.id == self.section_id), None)
        es_id = section.encounter_set_id if section else None
        if not es_id:
            return "## Setup\n\n- \n\n"
        try:
            es = self.guide.project.get_encounter_set(es_id)
            linked_ids = es.data.get('meta', {}).get('tts', {}).get('included_sets', [])
            linked = [self.guide.project.get_encounter_set(lid) for lid in linked_ids]
            linked = [ls for ls in linked if ls]
        except Exception:
            return "## Setup\n\n- \n\n"

        lines = [
            "## Setup",
            "",
            f"- Gather the [encounter:{es_id}:name] set.",
            "",
            ":::center",
            f"[encounter:{es_id}:icon]",
            ":::",
            "",
            f"- Put all [encounter:{es_id}:number_of_locations] locations into play, unrevealed side up.",
        ]

        if linked:
            name_list = " and ".join(f"[encounter:{ls.id}:name]" for ls in linked)
            plural = "sets" if len(linked) > 1 else "set"
            lines.append(f"- Also gather the {name_list} {plural}.")
            lines.append("")
            lines.append(":::center")
            for ls in linked:
                lines.append(f"[encounter:{ls.id}:icon]")
            lines.append(":::")

        lines.append("")
        return "\n".join(lines) + "\n"

    def _insert_card_ref(self):
        dlg = CardPickerDialog(self.guide, self)
        if dlg.exec() == QDialog.Accepted:
            snippet = dlg.result_snippet()
            if snippet:
                self._insert_snippet(snippet)

    def _insert_encounter_ref(self):
        dlg = EncounterPickerDialog(self.guide, self)
        if dlg.exec() == QDialog.Accepted:
            snippet = dlg.result_snippet()
            if snippet:
                self._insert_snippet(snippet)

    def _insert_snippet(self, text: str):
        self._md_editor.textCursor().insertText(text)
        self._md_editor.setFocus()

    def _on_name_changed(self, text):
        if self._loading:
            return
        self._save_to_guide(name_only=True)

    def _on_encounter_changed(self):
        if self._loading:
            return
        self._save_to_guide()

    def _on_markdown_changed(self):
        if self._loading:
            return
        if self.save_timer:
            self.save_timer.stop()
        self.save_timer = QTimer()
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self._save_to_guide)
        self.save_timer.start(500)
        self.content_changed.emit()

    def _save_to_guide(self, name_only=False):
        sections = self.guide.sections
        for s in sections:
            if s.id == self.section_id:
                s.name = self._name_edit.text()
                if not name_only:
                    s.markdown = self._md_editor.toPlainText()
                    if self._encounter_row.isVisible():
                        s.encounter_set_id = self._encounter_combo.currentData()
                break
        self.guide.save_sections(sections)

    def flush(self):
        """Force-save any pending changes immediately."""
        if self.save_timer and self.save_timer.isActive():
            self.save_timer.stop()
        self._save_to_guide()


# ── Main guide editor ─────────────────────────────────────────────────────────

class GuideEditor(QWidget):
    """Left: stacked overview/editor. Right: PDF preview."""

    def __init__(self, guide):
        super().__init__()
        self.guide = guide
        self.current_page = 1
        self.render_thread = None
        self.render_timer = None
        self._active_editor = None
        self._setup_ui()
        self.render_page(1)

    def _setup_ui(self):
        splitter = QSplitter(Qt.Horizontal)

        # ── Left: stacked overview / editor ──────────────────────────────────
        self.stack = QStackedWidget()

        self.overview = GuideOverviewPanel(self.guide)
        self.overview.section_edit_requested.connect(self._open_section)
        self.stack.addWidget(self.overview)  # index 0

        # index 1 is set dynamically when a section is opened
        self._editor_slot = QWidget()
        self._editor_slot_layout = QVBoxLayout(self._editor_slot)
        self._editor_slot_layout.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self._editor_slot)  # index 1

        splitter.addWidget(self.stack)

        # ── Right: PDF preview ────────────────────────────────────────────────
        preview_widget = QWidget()
        pv_layout = QVBoxLayout(preview_widget)
        pv_layout.setContentsMargins(4, 4, 4, 4)
        pv_layout.setSpacing(4)

        zoom_row = QHBoxLayout()
        for icon, delta in [("−", -1), (tr("BTN_ZOOM_100"), 0), ("+", 1)]:
            btn = QPushButton(icon)
            btn.setFixedWidth(50 if delta == 0 else 30)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda checked=False, d=delta: self._zoom(d))
            zoom_row.addWidget(btn)
        zoom_row.addStretch()
        pv_layout.addLayout(zoom_row)

        self.pdf_viewer = ZoomablePDFViewer()
        pv_layout.addWidget(self.pdf_viewer, stretch=1)

        page_row = QHBoxLayout()
        prev_btn = QPushButton(tr("BTN_PREVIOUS"))
        prev_btn.clicked.connect(self._prev_page)
        page_row.addWidget(prev_btn)
        page_row.addStretch()
        page_row.addWidget(QLabel(tr("LABEL_PAGE")))
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(999)
        self.page_spin.valueChanged.connect(self._on_page_changed)
        page_row.addWidget(self.page_spin)
        self.page_label = QLabel(tr("LABEL_OF_PAGES").format(total="?"))
        page_row.addWidget(self.page_label)
        page_row.addStretch()
        next_btn = QPushButton(tr("BTN_NEXT"))
        next_btn.clicked.connect(self._next_page)
        page_row.addWidget(next_btn)
        pv_layout.addLayout(page_row)

        splitter.addWidget(preview_widget)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(splitter)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _open_section(self, section_id: str):
        if self._active_editor:
            self._active_editor.flush()

        # Remove old editor widget
        while self._editor_slot_layout.count():
            item = self._editor_slot_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        editor = SectionEditorPanel(self.guide, section_id)
        editor.back_requested.connect(self._show_overview)
        editor.content_changed.connect(self._schedule_render)
        self._editor_slot_layout.addWidget(editor)
        self._active_editor = editor
        self.stack.setCurrentIndex(1)

    def _show_overview(self):
        if self._active_editor:
            self._active_editor.flush()
        self.overview.refresh()
        self.stack.setCurrentIndex(0)
        self._schedule_render()

    # ── PDF preview ───────────────────────────────────────────────────────────

    def render_page(self, page_number):
        if self.render_thread and self.render_thread.isRunning():
            self.render_thread.stop()
            self.render_thread.wait(500)
        self.render_thread = PDFPageRenderer(self.guide, page_number)
        self.render_thread.page_ready.connect(self._on_page_rendered)
        self.render_thread.start()

    def _schedule_render(self):
        if self.render_timer:
            self.render_timer.stop()
        self.render_timer = QTimer()
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(lambda: self.render_page(self.current_page))
        self.render_timer.start(500)

    def _on_page_rendered(self, page_number, pixmap):
        if page_number == self.current_page:
            self.pdf_viewer.set_pixmap(pixmap)

    def _on_page_changed(self, page_number):
        self.current_page = page_number
        self.render_page(page_number)

    def _prev_page(self):
        if self.current_page > 1:
            self.page_spin.setValue(self.current_page - 1)

    def _next_page(self):
        self.page_spin.setValue(self.current_page + 1)

    def _zoom(self, direction):
        if direction == 0:
            self.pdf_viewer.reset_view()
        elif direction > 0:
            self.pdf_viewer.zoom_level = min(self.pdf_viewer.zoom_level * 1.2, 5.0)
            self.pdf_viewer.update()
        else:
            self.pdf_viewer.zoom_level = max(self.pdf_viewer.zoom_level / 1.2, 0.1)
            self.pdf_viewer.update()

    def cleanup(self):
        if self._active_editor:
            self._active_editor.flush()
        if self.render_thread and self.render_thread.isRunning():
            self.render_thread.stop()
            self.render_thread.wait(1000)
            if self.render_thread.isRunning():
                self.render_thread.terminate()
                self.render_thread.wait()
        if self.render_timer:
            self.render_timer.stop()
