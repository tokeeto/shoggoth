"""
Guide Editor – structured form-based section editing with HTML fallback and PDF preview.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QTextEdit, QSplitter, QFileDialog, QScrollArea,
    QFrame, QMessageBox, QLineEdit, QStackedWidget, QSizePolicy,
    QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
    QPixmap, QImage,
)

import re
from pathlib import Path
from shoggoth.i18n import tr
from shoggoth.guide import SECTION_TYPES, GuideSection

# ── Display labels ────────────────────────────────────────────────────────────

SECTION_LABELS = {
    'intro': 'Intro',
    'prelude': 'Prelude',
    'interlude': 'Interlude',
    'scenario': 'Scenario',
    'blank': 'Blank',
}

SECTION_COLORS = {
    'intro': '#4a7c59',
    'prelude': '#2d5b58',
    'interlude': '#7c4a6e',
    'scenario': '#3d5a8a',
    'blank': '#666666',
}


# ── HTML syntax highlighter ───────────────────────────────────────────────────

class HTMLHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules = []

        tag_fmt = QTextCharFormat()
        tag_fmt.setForeground(QColor("#0000ff"))
        tag_fmt.setFontWeight(QFont.Bold)
        self._rules.append((re.compile(r'<[^>]+>'), tag_fmt))

        attr_fmt = QTextCharFormat()
        attr_fmt.setForeground(QColor("#ff0000"))
        self._rules.append((re.compile(r'\b\w+(?=\s*=)'), attr_fmt))

        val_fmt = QTextCharFormat()
        val_fmt.setForeground(QColor("#008000"))
        self._rules += [
            (re.compile(r'"[^"]*"'), val_fmt),
            (re.compile(r"'[^']*'"), val_fmt),
        ]

        cmt_fmt = QTextCharFormat()
        cmt_fmt.setForeground(QColor("#808080"))
        cmt_fmt.setFontItalic(True)
        self._rules.append((re.compile(r'<!--.*?-->'), cmt_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ── PDF rendering thread ──────────────────────────────────────────────────────

class PDFPageRenderer(QThread):
    page_ready = Signal(int, object)

    def __init__(self, guide, page_number, html=None):
        super().__init__()
        self.guide = guide
        self.page_number = page_number
        self.html = html
        self._stop = False

    def run(self):
        if self._stop:
            return
        try:
            buf = self.guide.get_page(self.page_number, html=self.html or '')
            if self._stop:
                return
            buf.seek(0)
            qimage = QImage.fromData(buf.read())
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
        self.setMinimumSize(400, 600)
        self.setMouseTracking(True)

    def set_pixmap(self, pixmap):
        self.pixmap = pixmap
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


# ── Reusable editable list widget ─────────────────────────────────────────────

class EditableListWidget(QWidget):
    """An ordered list with add / remove / reorder buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(80)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_item)
        remove_btn = QPushButton("− Remove")
        remove_btn.clicked.connect(self._remove_item)
        up_btn = QPushButton("▲")
        up_btn.setFixedWidth(32)
        up_btn.clicked.connect(self._move_up)
        down_btn = QPushButton("▼")
        down_btn.setFixedWidth(32)
        down_btn.clicked.connect(self._move_down)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        btn_row.addWidget(up_btn)
        btn_row.addWidget(down_btn)
        layout.addLayout(btn_row)

    def _add_item(self):
        item = QListWidgetItem("New item")
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.list_widget.addItem(item)
        self.list_widget.setCurrentItem(item)
        self.list_widget.editItem(item)

    def _remove_item(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def _move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            self.list_widget.setCurrentRow(row - 1)

    def _move_down(self):
        row = self.list_widget.currentRow()
        if row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            self.list_widget.setCurrentRow(row + 1)

    def get_items(self):
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]

    def set_items(self, items):
        self.list_widget.clear()
        for text in items:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.list_widget.addItem(item)


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _strip_tags(html: str) -> str:
    return re.sub(r'<[^>]+>', '', html)


# ── Type-specific section forms ───────────────────────────────────────────────

class BaseSectionForm(QWidget):
    def to_html(self) -> str:
        raise NotImplementedError

    def from_html(self, html: str):
        raise NotImplementedError


class ScenarioForm(BaseSectionForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit()
        layout.addWidget(self.title_edit)

        layout.addWidget(QLabel("Story / Flavor text:"))
        hint = QLabel("Italic flavor text. Separate paragraphs with a blank line.")
        hint.setStyleSheet("color: gray; font-size: 8pt;")
        layout.addWidget(hint)
        self.story_edit = QTextEdit()
        self.story_edit.setMinimumHeight(100)
        layout.addWidget(self.story_edit)

        layout.addWidget(QLabel("Setup steps:"))
        self.setup_list = EditableListWidget()
        layout.addWidget(self.setup_list)

        layout.addWidget(QLabel("Resolution:"))
        res_hint = QLabel("Resolution text / outcomes. Raw HTML accepted.")
        res_hint.setStyleSheet("color: gray; font-size: 8pt;")
        layout.addWidget(res_hint)
        self.resolution_edit = QTextEdit()
        self.resolution_edit.setMinimumHeight(80)
        layout.addWidget(self.resolution_edit)

        layout.addStretch()

    def to_html(self) -> str:
        parts = []
        title = self.title_edit.text().strip()
        if title:
            parts.append(f'<h1>{title}</h1>')
        story = self.story_edit.toPlainText().strip()
        if story:
            for para in re.split(r'\n{2,}', story):
                para = para.strip()
                if para:
                    parts.append(f'<p class="italic">{para}</p>')
        items = self.setup_list.get_items()
        if items:
            li = '\n'.join(f'\t<li>{item}</li>' for item in items)
            parts.append(f'<h4>Setup</h4>\n<ul>\n{li}\n</ul>\n<p><b>You are now ready to begin.</b></p>')
        res = self.resolution_edit.toPlainText().strip()
        if res:
            parts.append(f'<div class="resolution_box">\n{res}\n</div>')
        return '\n'.join(parts)

    def from_html(self, html: str):
        m = re.search(r'<h[12][^>]*>(.*?)</h[12]>', html, re.DOTALL | re.IGNORECASE)
        if m:
            self.title_edit.setText(_strip_tags(m.group(1)))
        story_paras = re.findall(
            r'<p[^>]*class=["\']italic["\'][^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE
        )
        if story_paras:
            self.story_edit.setPlainText('\n\n'.join(p for p in story_paras))
        setup_m = re.search(
            r'<h4[^>]*>\s*Setup\s*</h4>\s*<ul>(.*?)</ul>', html, re.DOTALL | re.IGNORECASE
        )
        if setup_m:
            items = re.findall(r'<li>(.*?)</li>', setup_m.group(1), re.DOTALL)
            self.setup_list.set_items([_strip_tags(i).strip() for i in items])
        res_m = re.search(
            r'<div[^>]*class=["\']resolution_box["\'][^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE
        )
        if res_m:
            self.resolution_edit.setPlainText(res_m.group(1).strip())


class InterludeForm(BaseSectionForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit()
        layout.addWidget(self.title_edit)

        layout.addWidget(QLabel("Story / Flavor text:"))
        hint = QLabel("Italic story text. Separate paragraphs with a blank line.")
        hint.setStyleSheet("color: gray; font-size: 8pt;")
        layout.addWidget(hint)
        self.story_edit = QTextEdit()
        self.story_edit.setMinimumHeight(120)
        layout.addWidget(self.story_edit)

        layout.addWidget(QLabel("Additional rules / notes:"))
        self.notes_edit = QTextEdit()
        self.notes_edit.setMinimumHeight(80)
        layout.addWidget(self.notes_edit)

        layout.addStretch()

    def to_html(self) -> str:
        parts = []
        title = self.title_edit.text().strip()
        if title:
            parts.append(f'<h1>{title}</h1>')
        story = self.story_edit.toPlainText().strip()
        if story:
            for para in re.split(r'\n{2,}', story):
                para = para.strip()
                if para:
                    parts.append(f'<p class="italic">{para}</p>')
        notes = self.notes_edit.toPlainText().strip()
        if notes:
            for para in re.split(r'\n{2,}', notes):
                para = para.strip()
                if para:
                    parts.append(f'<p>{para}</p>')
        return '\n'.join(parts)

    def from_html(self, html: str):
        m = re.search(r'<h[12][^>]*>(.*?)</h[12]>', html, re.DOTALL | re.IGNORECASE)
        if m:
            self.title_edit.setText(_strip_tags(m.group(1)))
        story_paras = re.findall(
            r'<p[^>]*class=["\']italic["\'][^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE
        )
        if story_paras:
            self.story_edit.setPlainText('\n\n'.join(story_paras))
        notes_paras = re.findall(
            r'<p(?![^>]*class=["\']italic["\'])[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE
        )
        if notes_paras:
            self.notes_edit.setPlainText('\n\n'.join(_strip_tags(p) for p in notes_paras))


class IntroForm(BaseSectionForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit()
        layout.addWidget(self.title_edit)

        layout.addWidget(QLabel("Opening quote / flavor:"))
        self.quote_edit = QTextEdit()
        self.quote_edit.setMaximumHeight(80)
        layout.addWidget(self.quote_edit)

        layout.addWidget(QLabel("Description:"))
        hint = QLabel("Campaign overview text. Separate paragraphs with a blank line.")
        hint.setStyleSheet("color: gray; font-size: 8pt;")
        layout.addWidget(hint)
        self.desc_edit = QTextEdit()
        self.desc_edit.setMinimumHeight(100)
        layout.addWidget(self.desc_edit)

        layout.addWidget(QLabel("Campaign setup steps:"))
        self.setup_list = EditableListWidget()
        layout.addWidget(self.setup_list)

        layout.addStretch()

    def to_html(self) -> str:
        parts = []
        title = self.title_edit.text().strip()
        if title:
            parts.append(f'<h2>{title}</h2>')
        quote = self.quote_edit.toPlainText().strip()
        if quote:
            parts.append(f'<div class="center italic">\n{quote}\n</div>')
        desc = self.desc_edit.toPlainText().strip()
        if desc:
            for para in re.split(r'\n{2,}', desc):
                para = para.strip()
                if para:
                    parts.append(f'<p>{para}</p>')
        items = self.setup_list.get_items()
        if items:
            li = '\n'.join(f'\t<li>{item}</li>' for item in items)
            parts.append(f'<h2>Campaign Setup</h2>\n<ol>\n{li}\n</ol>')
        return '\n'.join(parts)

    def from_html(self, html: str):
        m = re.search(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL | re.IGNORECASE)
        if m:
            self.title_edit.setText(_strip_tags(m.group(1)))
        quote_m = re.search(
            r'<div[^>]*class=["\']center italic["\'][^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE
        )
        if quote_m:
            self.quote_edit.setPlainText(quote_m.group(1).strip())
        desc_paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
        if desc_paras:
            self.desc_edit.setPlainText('\n\n'.join(_strip_tags(p) for p in desc_paras))
        setup_m = re.search(r'<ol>(.*?)</ol>', html, re.DOTALL | re.IGNORECASE)
        if setup_m:
            items = re.findall(r'<li>(.*?)</li>', setup_m.group(1), re.DOTALL)
            self.setup_list.set_items([_strip_tags(i).strip() for i in items])


class PreludeForm(BaseSectionForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit()
        layout.addWidget(self.title_edit)

        layout.addWidget(QLabel("Story / Flavor text:"))
        hint = QLabel("Italic story text. Separate paragraphs with a blank line.")
        hint.setStyleSheet("color: gray; font-size: 8pt;")
        layout.addWidget(hint)
        self.story_edit = QTextEdit()
        self.story_edit.setMinimumHeight(120)
        layout.addWidget(self.story_edit)

        layout.addStretch()

    def to_html(self) -> str:
        parts = []
        title = self.title_edit.text().strip()
        if title:
            parts.append(f'<h1>{title}</h1>')
        story = self.story_edit.toPlainText().strip()
        if story:
            for para in re.split(r'\n{2,}', story):
                para = para.strip()
                if para:
                    parts.append(f'<p class="italic">{para}</p>')
        return '\n'.join(parts)

    def from_html(self, html: str):
        m = re.search(r'<h[12][^>]*>(.*?)</h[12]>', html, re.DOTALL | re.IGNORECASE)
        if m:
            self.title_edit.setText(_strip_tags(m.group(1)))
        story_paras = re.findall(
            r'<p[^>]*class=["\']italic["\'][^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE
        )
        if story_paras:
            self.story_edit.setPlainText('\n\n'.join(story_paras))


class BlankForm(BaseSectionForm):
    """Blank sections get a raw HTML editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setFont(QFont("Courier", 10))
        HTMLHighlighter(self.editor.document())
        layout.addWidget(self.editor)

    def to_html(self) -> str:
        return self.editor.toPlainText()

    def from_html(self, html: str):
        self.editor.setPlainText(html)


FORM_CLASSES = {
    'scenario': ScenarioForm,
    'interlude': InterludeForm,
    'intro': IntroForm,
    'prelude': PreludeForm,
    'blank': BlankForm,
}


# ── Section editor panel ──────────────────────────────────────────────────────

class SectionEditorPanel(QWidget):
    saved = Signal()
    back_requested = Signal()

    def __init__(self, guide, section_id, parent=None):
        super().__init__(parent)
        self.guide = guide
        self.section_id = section_id
        self._form = None
        self._setup_ui()
        self._load()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Top bar
        top = QHBoxLayout()
        back_btn = QPushButton("← Overview")
        back_btn.clicked.connect(self.back_requested)
        top.addWidget(back_btn)
        top.addStretch()
        self._html_toggle_btn = QPushButton("< > HTML")
        self._html_toggle_btn.setCheckable(True)
        self._html_toggle_btn.toggled.connect(self._toggle_html)
        top.addWidget(self._html_toggle_btn)
        layout.addLayout(top)

        # Section name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Section name:"))
        self.name_edit = QLineEdit()
        name_row.addWidget(self.name_edit)
        layout.addLayout(name_row)

        # Content: stacked (0=form in scroll, 1=HTML editor)
        self.content_stack = QStackedWidget()

        self._form_scroll = QScrollArea()
        self._form_scroll.setWidgetResizable(True)
        self._form_scroll.setFrameStyle(QFrame.NoFrame)
        # Placeholder until _load() sets the real form
        self._form_scroll.setWidget(QWidget())
        self.content_stack.addWidget(self._form_scroll)  # index 0

        self._html_editor = QTextEdit()
        self._html_editor.setAcceptRichText(False)
        self._html_editor.setFont(QFont("Courier", 10))
        HTMLHighlighter(self._html_editor.document())
        self.content_stack.addWidget(self._html_editor)  # index 1

        layout.addWidget(self.content_stack, stretch=1)

        # Save button
        save_btn = QPushButton("Save Section")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

    def _load(self):
        result = self.guide.parse_sections()
        if result is None:
            return
        _, sections, _ = result
        section = next((s for s in sections if s.id == self.section_id), None)
        if section is None:
            return
        self.name_edit.setText(section.name)
        form_class = FORM_CLASSES.get(section.type, BlankForm)
        self._form = form_class()
        self._form.from_html(section.html_content)
        self._form_scroll.setWidget(self._form)

    def _toggle_html(self, checked):
        if checked:
            if self._form:
                self._html_editor.setPlainText(self._form.to_html())
            self.content_stack.setCurrentIndex(1)
            self._html_toggle_btn.setText("Form view")
        else:
            if self._form:
                self._form.from_html(self._html_editor.toPlainText())
            self.content_stack.setCurrentIndex(0)
            self._html_toggle_btn.setText("< > HTML")

    def _get_current_html(self) -> str:
        if self.content_stack.currentIndex() == 1:
            return self._html_editor.toPlainText()
        return self._form.to_html() if self._form else ''

    def _save(self):
        result = self.guide.parse_sections()
        if result is None:
            return
        preamble, sections, postamble = result
        section = next((s for s in sections if s.id == self.section_id), None)
        if section is None:
            return
        section.name = self.name_edit.text()
        section.html_content = self._get_current_html()
        self.guide.save_sections(preamble, sections, postamble)
        self.saved.emit()


# ── Guide overview (storyboard) ───────────────────────────────────────────────

class SectionCard(QFrame):
    edit_clicked = Signal(str)     # section_id
    delete_clicked = Signal(str)   # section_id
    move_up_clicked = Signal(str)  # section_id
    move_down_clicked = Signal(str)

    def __init__(self, section, parent=None):
        super().__init__(parent)
        self.section_id = section.id
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("QFrame { border-radius: 4px; }")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        color = SECTION_COLORS.get(section.type, '#666')
        badge = QLabel(SECTION_LABELS.get(section.type, section.type))
        badge.setStyleSheet(
            f"background: {color}; color: white; font-weight: bold; "
            f"padding: 2px 8px; border-radius: 3px; min-width: 70px;"
        )
        badge.setAlignment(Qt.AlignCenter)
        layout.addWidget(badge)

        name_lbl = QLabel(section.name or "(unnamed)")
        name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(name_lbl)

        for icon, sig in [("▲", self.move_up_clicked), ("▼", self.move_down_clicked)]:
            btn = QPushButton(icon)
            btn.setFixedSize(28, 28)
            btn.clicked.connect(lambda checked=False, s=sig: s.emit(self.section_id))
            layout.addWidget(btn)

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedWidth(50)
        edit_btn.clicked.connect(lambda: self.edit_clicked.emit(self.section_id))
        layout.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 28)
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self.section_id))
        layout.addWidget(del_btn)


class GuideOverviewPanel(QWidget):
    edit_section = Signal(str)
    edit_raw_html = Signal()

    def __init__(self, guide, parent=None):
        super().__init__(parent)
        self.guide = guide
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Guide name
        self._title_lbl = QLabel()
        self._title_lbl.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(self._title_lbl)

        # Front page setting
        fp_row = QHBoxLayout()
        fp_row.addWidget(QLabel("Front page image:"))
        self._fp_edit = QLineEdit()
        self._fp_edit.textChanged.connect(lambda t: setattr(self.guide, 'front_page', t))
        fp_row.addWidget(self._fp_edit)
        browse_btn = QPushButton(tr("BTN_BROWSE"))
        browse_btn.clicked.connect(self._browse_front_page)
        fp_row.addWidget(browse_btn)
        layout.addLayout(fp_row)

        # Storyboard scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.NoFrame)
        self._board_widget = QWidget()
        self._board_layout = QVBoxLayout(self._board_widget)
        self._board_layout.setAlignment(Qt.AlignTop)
        self._board_layout.setSpacing(6)
        scroll.setWidget(self._board_widget)
        layout.addWidget(scroll, stretch=1)

        # Add section buttons
        add_lbl = QLabel("Add section:")
        add_lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(add_lbl)
        add_row = QHBoxLayout()
        for stype in SECTION_TYPES:
            btn = QPushButton(SECTION_LABELS.get(stype, stype))
            btn.clicked.connect(lambda checked=False, t=stype: self._add_section(t))
            add_row.addWidget(btn)
        layout.addLayout(add_row)

        # Action buttons
        btn_row = QHBoxLayout()
        export_btn = QPushButton(tr("BTN_EXPORT_PDF"))
        export_btn.clicked.connect(self._export_pdf)
        btn_row.addWidget(export_btn)
        btn_row.addStretch()
        html_btn = QPushButton("Edit Raw HTML")
        html_btn.clicked.connect(self.edit_raw_html)
        btn_row.addWidget(html_btn)
        layout.addLayout(btn_row)

    def refresh(self):
        self._title_lbl.setText(f"Guide: {self.guide.name}")
        self._fp_edit.blockSignals(True)
        self._fp_edit.setText(self.guide.front_page)
        self._fp_edit.blockSignals(False)

        # Clear storyboard
        while self._board_layout.count():
            item = self._board_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        result = self.guide.parse_sections()
        if result is None:
            lbl = QLabel("No structured sections. Add a section below, or 'Edit Raw HTML'.")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color: gray; font-style: italic;")
            self._board_layout.addWidget(lbl)
            return

        _, sections, _ = result
        if not sections:
            lbl = QLabel("No sections yet. Add one below.")
            lbl.setStyleSheet("color: gray; font-style: italic;")
            self._board_layout.addWidget(lbl)
            return

        for section in sections:
            card = SectionCard(section)
            card.edit_clicked.connect(self.edit_section)
            card.delete_clicked.connect(self._delete_section)
            card.move_up_clicked.connect(self._move_section_up)
            card.move_down_clicked.connect(self._move_section_down)
            self._board_layout.addWidget(card)

    def _browse_front_page(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Front Page Image", str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.avif)",
        )
        if path:
            self._fp_edit.setText(path)

    def _add_section(self, section_type):
        result = self.guide.parse_sections()
        if result is None:
            self.guide.initialize_sections()
            result = self.guide.parse_sections()
        if result is None:
            QMessageBox.warning(self, "Error", "Could not initialize guide structure.")
            return
        preamble, sections, postamble = result
        name = SECTION_LABELS.get(section_type, section_type)
        sections.append(GuideSection(section_type, name))
        self.guide.save_sections(preamble, sections, postamble)
        self.refresh()

    def _delete_section(self, section_id):
        result = self.guide.parse_sections()
        if result is None:
            return
        preamble, sections, postamble = result
        sections = [s for s in sections if s.id != section_id]
        self.guide.save_sections(preamble, sections, postamble)
        self.refresh()

    def _move_section_up(self, section_id):
        result = self.guide.parse_sections()
        if result is None:
            return
        preamble, sections, postamble = result
        idx = next((i for i, s in enumerate(sections) if s.id == section_id), None)
        if idx is not None and idx > 0:
            sections[idx - 1], sections[idx] = sections[idx], sections[idx - 1]
            self.guide.save_sections(preamble, sections, postamble)
            self.refresh()

    def _move_section_down(self, section_id):
        result = self.guide.parse_sections()
        if result is None:
            return
        preamble, sections, postamble = result
        idx = next((i for i, s in enumerate(sections) if s.id == section_id), None)
        if idx is not None and idx < len(sections) - 1:
            sections[idx], sections[idx + 1] = sections[idx + 1], sections[idx]
            self.guide.save_sections(preamble, sections, postamble)
            self.refresh()

    def _export_pdf(self):
        self.guide.render_to_file()
        QMessageBox.information(
            self, tr("DLG_EXPORT_COMPLETE"),
            tr("MSG_PDF_EXPORTED").format(path=self.guide.target_path),
        )


# ── Main guide editor widget ──────────────────────────────────────────────────

class GuideEditor(QWidget):
    """Top-level guide editor. Left: storyboard overview / section editor / raw HTML.
    Right: PDF preview."""

    def __init__(self, guide):
        super().__init__()
        self.guide = guide
        self.current_page = 1
        self.render_thread = None
        self.render_timer = None
        self._setup_ui()
        self._show_initial()

    def _setup_ui(self):
        splitter = QSplitter(Qt.Horizontal)

        # ── Left: stacked panels ──────────────────────────────────────────────
        self.stack = QStackedWidget()

        # Index 0 – overview / storyboard
        self.overview_panel = GuideOverviewPanel(self.guide)
        self.overview_panel.edit_section.connect(self.show_section)
        self.overview_panel.edit_raw_html.connect(self._activate_html)
        self.stack.addWidget(self.overview_panel)

        # Index 1 – section editor slot (replaced on demand)
        self.section_slot = QWidget()
        self.section_slot_layout = QVBoxLayout(self.section_slot)
        self.section_slot_layout.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.section_slot)

        # Index 2 – raw HTML editor for the whole guide
        html_widget = QWidget()
        html_layout = QVBoxLayout(html_widget)
        back_btn = QPushButton("← Back to Overview")
        back_btn.clicked.connect(self.show_overview)
        html_layout.addWidget(back_btn)

        self.html_editor = QTextEdit()
        self.html_editor.setAcceptRichText(False)
        self.html_editor.setLineWrapMode(QTextEdit.NoWrap)
        self.html_editor.setFont(QFont("Courier", 10))
        HTMLHighlighter(self.html_editor.document())
        self.html_editor.textChanged.connect(self._on_html_changed)
        html_layout.addWidget(self.html_editor)

        html_btns = QHBoxLayout()
        save_html_btn = QPushButton("Save HTML")
        save_html_btn.clicked.connect(self._save_html)
        html_btns.addWidget(save_html_btn)
        html_btns.addStretch()
        export_btn = QPushButton(tr("BTN_EXPORT_PDF"))
        export_btn.clicked.connect(self._export_pdf_from_html)
        html_btns.addWidget(export_btn)
        html_layout.addLayout(html_btns)
        self.stack.addWidget(html_widget)

        splitter.addWidget(self.stack)

        # ── Right: PDF preview ────────────────────────────────────────────────
        preview_widget = QWidget()
        pv_layout = QVBoxLayout(preview_widget)

        pv_title = QLabel(tr("TAB_PREVIEW"))
        pv_title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        pv_layout.addWidget(pv_title)

        zoom_row = QHBoxLayout()
        for icon, delta in [("−", -1), (tr("BTN_ZOOM_100"), 0), ("+", 1)]:
            btn = QPushButton(icon)
            btn.setFixedWidth(50 if delta == 0 else 30)
            btn.clicked.connect(lambda checked=False, d=delta: self._zoom(d))
            zoom_row.addWidget(btn)
        zoom_row.addStretch()
        pv_layout.addLayout(zoom_row)

        self.pdf_viewer = ZoomablePDFViewer()
        pv_layout.addWidget(self.pdf_viewer)

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
        splitter.setSizes([500, 500])

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(splitter)

    def _show_initial(self):
        if self.guide.parse_sections() is not None:
            self.stack.setCurrentIndex(0)
        else:
            self._load_html_editor()
            self.stack.setCurrentIndex(2)
        self.render_page(1)

    # ── Public API ────────────────────────────────────────────────────────────

    def show_overview(self):
        self.overview_panel.refresh()
        self.stack.setCurrentIndex(0)

    def show_section(self, section_id):
        while self.section_slot_layout.count():
            item = self.section_slot_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        panel = SectionEditorPanel(self.guide, section_id)
        panel.saved.connect(lambda: self.render_page(self.current_page))
        panel.back_requested.connect(self.show_overview)
        self.section_slot_layout.addWidget(panel)
        self.stack.setCurrentIndex(1)

    # ── Internal slots ────────────────────────────────────────────────────────

    def _activate_html(self):
        self._load_html_editor()
        self.stack.setCurrentIndex(2)

    def _load_html_editor(self):
        self.html_editor.blockSignals(True)
        self.html_editor.setPlainText(self.guide.get_html())
        self.html_editor.blockSignals(False)

    def _save_html(self):
        self.guide.save(self.html_editor.toPlainText())
        self.render_page(self.current_page)

    def _export_pdf_from_html(self):
        self.guide.render_to_file(html=self.html_editor.toPlainText())
        QMessageBox.information(
            self, tr("DLG_EXPORT_COMPLETE"),
            tr("MSG_PDF_EXPORTED").format(path=self.guide.target_path),
        )

    def _on_html_changed(self):
        if self.render_timer:
            self.render_timer.stop()
        self.render_timer = QTimer()
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(lambda: self.render_page(self.current_page))
        self.render_timer.start(1500)

    def render_page(self, page_number):
        if self.render_thread and self.render_thread.isRunning():
            self.render_thread.stop()
            self.render_thread.wait(500)
        if self.stack.currentIndex() == 2:
            html = self.html_editor.toPlainText()
        else:
            html = self.guide.get_html()
        self.render_thread = PDFPageRenderer(self.guide, page_number, html)
        self.render_thread.page_ready.connect(self._on_page_rendered)
        self.render_thread.start()

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
        if self.render_thread and self.render_thread.isRunning():
            self.render_thread.stop()
            self.render_thread.wait(1000)
            if self.render_thread.isRunning():
                self.render_thread.terminate()
                self.render_thread.wait()
        if self.render_timer:
            self.render_timer.stop()
