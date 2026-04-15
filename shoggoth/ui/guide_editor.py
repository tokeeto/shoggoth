"""
Guide Editor – structured form-based section editing with HTML fallback and PDF preview.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QTextEdit, QSplitter, QFileDialog, QScrollArea,
    QFrame, QMessageBox, QLineEdit, QStackedWidget, QSizePolicy,
    QListWidget, QListWidgetItem, QComboBox, QDialog, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
    QPixmap, QImage,
)

import re
from pathlib import Path
from shoggoth.i18n import tr
from bs4 import BeautifulSoup, NavigableString
from shoggoth.guide import SECTION_TYPES, GuideSection, SECTION_FIELDS

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


# ── Markdown ↔ HTML conversion ────────────────────────────────────────────────

def _md_inline(text: str) -> str:
    """Apply inline markdown: **bold** and *italic*."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    return text


def _md_to_html(md: str) -> str:
    """Convert simple markdown to HTML. Supports headings, paragraphs, bullet lists."""
    lines = md.split('\n')
    out = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        heading_match = re.match(r'^(#{1,3})\s+(.*)', stripped)
        if heading_match:
            level = len(heading_match.group(1))
            out.append(f'<h{level}>{_md_inline(heading_match.group(2))}</h{level}>')
            i += 1
        elif stripped.startswith('- ') or stripped.startswith('* '):
            items = []
            while i < len(lines):
                s = lines[i].strip()
                if s.startswith('- ') or s.startswith('* '):
                    items.append(f'<li>{_md_inline(s[2:])}</li>')
                    i += 1
                else:
                    break
            out.append('<ul>\n' + '\n'.join(items) + '\n</ul>')
        elif stripped == '':
            i += 1
        else:
            para_lines = []
            while i < len(lines):
                s = lines[i].strip()
                if s == '' or s.startswith('#') or s.startswith('- ') or s.startswith('* '):
                    break
                para_lines.append(s)
                i += 1
            out.append(f'<p>{_md_inline(" ".join(para_lines))}</p>')
    return '\n'.join(out)


def _elem_to_md_inline(elem) -> str:
    result = ''
    for child in elem.children:
        if isinstance(child, NavigableString):
            result += str(child)
        elif child.name in ('em', 'i'):
            result += f'*{child.get_text()}*'
        elif child.name in ('strong', 'b'):
            result += f'**{child.get_text()}**'
        else:
            result += child.get_text()
    return result


def _html_to_md(html: str) -> str:
    """Convert simple HTML to markdown. Handles headings, paragraphs, lists, divs."""
    soup = BeautifulSoup(html, 'html.parser')
    parts = []
    for elem in soup.children:
        if isinstance(elem, NavigableString):
            text = str(elem).strip()
            if text:
                parts.append(text)
        elif elem.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(elem.name[1])
            parts.append('#' * level + ' ' + elem.get_text().strip())
        elif elem.name == 'p':
            text = _elem_to_md_inline(elem).strip()
            if text:
                parts.append(text)
        elif elem.name in ('ul', 'ol'):
            for li in elem.find_all('li', recursive=False):
                parts.append('- ' + _elem_to_md_inline(li).strip())
        elif elem.name == 'div':
            inner = _html_to_md(elem.decode_contents())
            if inner.strip():
                parts.append(inner)
    return '\n\n'.join(p for p in parts if p.strip())


# ── Expanded editor dialog ────────────────────────────────────────────────────

class ExpandedEditorDialog(QDialog):
    """Modal popup with a large text editor for comfortable editing."""

    def __init__(self, title: str, content: str, highlight_html: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'Edit: {title}')
        self.resize(720, 520)
        layout = QVBoxLayout(self)
        self._edit = QTextEdit()
        self._edit.setAcceptRichText(False)
        self._edit.setFont(QFont('Courier', 10))
        self._edit.setPlainText(content)
        if highlight_html:
            HTMLHighlighter(self._edit.document())
        layout.addWidget(self._edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_content(self) -> str:
        return self._edit.toPlainText()


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
            img = self.guide.get_page(self.page_number, html=self.html or '')
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


# ── Field editor widgets ───────────────────────────────────────────────────────

class FieldEditorWidget(QFrame):
    """Base widget for editing one predefined section field."""

    def __init__(self, field_def, guide=None, parent=None):
        super().__init__(parent)
        self.field_def = field_def
        self.guide = guide
        self._status = 'ok'  # 'ok' | 'missing' | 'ambiguous'
        self.setFrameStyle(QFrame.StyledPanel)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)
        header_row = QHBoxLayout()
        self._header_lbl = QLabel(f'<b>{field_def.label}</b>')
        header_row.addWidget(self._header_lbl)
        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet('font-size: 8pt; font-style: italic;')
        header_row.addWidget(self._status_lbl)
        header_row.addStretch()
        self._expand_btn = QPushButton('⤢')
        self._expand_btn.setFixedSize(24, 24)
        self._expand_btn.setToolTip('Open in expanded editor')
        self._expand_btn.clicked.connect(self._expand)
        self._expand_btn.hide()
        header_row.addWidget(self._expand_btn)
        outer.addLayout(header_row)
        self._warn_lbl = QLabel()
        self._warn_lbl.setWordWrap(True)
        self._warn_lbl.setStyleSheet('color: #cc4400; font-size: 8pt;')
        self._warn_lbl.hide()
        outer.addWidget(self._warn_lbl)
        self._build_editor(outer)
        # Show expand button for any field that has a multi-line text editor
        if hasattr(self, '_edit') and isinstance(self._edit, QTextEdit):
            self._expand_btn.show()

    def _build_editor(self, layout):
        pass

    def get_value(self) -> str:
        """Return the full HTML element string for this field."""
        return ''

    def set_value(self, html_fragment: str):
        """Populate editor from the matched element's outer HTML."""

    def load_from_soup(self, wrapper):
        """Locate the field element in *wrapper* and configure widget state."""
        matches = self.field_def.locate(wrapper)
        if len(matches) == 0:
            self._status = 'missing'
            self.setStyleSheet('QFrame { border-left: 3px solid #aa7700; }')
            self._status_lbl.setText('(not in HTML — will be appended on save)')
            self._status_lbl.setStyleSheet('color: #aa7700; font-size: 8pt; font-style: italic;')
            self.set_value(self.field_def.default_html)
        elif len(matches) > 1:
            self._status = 'ambiguous'
            self.setStyleSheet('QFrame { border-left: 3px solid #cc4400; }')
            self._status_lbl.setText(f'ambiguous ({len(matches)} matches)')
            self._status_lbl.setStyleSheet('color: #cc4400; font-size: 8pt; font-weight: bold;')
            self._warn_lbl.setText(
                'Multiple elements match — this field is disabled. Edit raw HTML to resolve.'
            )
            self._warn_lbl.show()
            self.setEnabled(False)
        else:
            self._status = 'ok'
            self.setStyleSheet('QFrame { border-left: 3px solid #3d5a8a; }')
            self._status_lbl.clear()
            self._warn_lbl.hide()
            self.setEnabled(True)
            self.set_value(str(matches[0]))

    def apply_to_soup(self, wrapper):
        """Write current value back into *wrapper* (surgical update)."""
        if self._status == 'ambiguous':
            return
        matches = self.field_def.locate(wrapper)
        new_tag = BeautifulSoup(self.get_value(), 'html.parser').find()
        if new_tag is None:
            return
        if not matches:
            wrapper.append(new_tag)
        else:
            matches[0].replace_with(new_tag)

    def _expand(self):
        """Open the field's text editor content in a larger popup dialog."""
        if not hasattr(self, '_edit') or not isinstance(self._edit, QTextEdit):
            return
        is_html_field = self.field_def.kind in ('html', 'titled_html')
        in_md_mode = getattr(self, '_md_mode', False)
        dlg = ExpandedEditorDialog(
            self.field_def.label,
            self._edit.toPlainText(),
            highlight_html=is_html_field and not in_md_mode,
            parent=self,
        )
        if dlg.exec():
            self._edit.setPlainText(dlg.get_content())


class LineFieldWidget(FieldEditorWidget):
    """Single-line plain text (e.g. h1 header)."""

    def _build_editor(self, layout):
        self._edit = QLineEdit()
        self._edit.setPlaceholderText(f'{self.field_def.label}...')
        layout.addWidget(self._edit)

    def get_value(self) -> str:
        tag = self.field_def.selector_tag
        return f'<{tag}>{self._edit.text()}</{tag}>'

    def set_value(self, html_fragment: str):
        m = re.search(r'<[^>]+>(.*?)</[^>]+>', html_fragment, re.DOTALL)
        self._edit.setText(_strip_tags(m.group(1)) if m else '')


class StoryFieldWidget(FieldEditorWidget):
    """Multi-paragraph italic story/flavour text (div.story)."""

    def _build_editor(self, layout):
        hint = QLabel('Blank line = new paragraph. Text will be italicised.')
        hint.setStyleSheet('color: gray; font-size: 8pt;')
        layout.addWidget(hint)
        self._edit = QTextEdit()
        self._edit.setMinimumHeight(80)
        self._edit.setMaximumHeight(200)
        layout.addWidget(self._edit)

    def get_value(self) -> str:
        text = self._edit.toPlainText().strip()
        paras = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()] or ['']
        inner = '\n'.join(f'<p><em>{p}</em></p>' for p in paras)
        css = self.field_def.selector_class
        return f'<div class="{css}">\n{inner}\n</div>'

    def set_value(self, html_fragment: str):
        em_paras = re.findall(r'<em[^>]*>(.*?)</em>', html_fragment, re.DOTALL | re.IGNORECASE)
        if em_paras:
            self._edit.setPlainText('\n\n'.join(_strip_tags(p) for p in em_paras))
        else:
            paras = re.findall(r'<p[^>]*>(.*?)</p>', html_fragment, re.DOTALL | re.IGNORECASE)
            self._edit.setPlainText('\n\n'.join(_strip_tags(p) for p in paras))


class TextFieldWidget(FieldEditorWidget):
    """Multi-paragraph plain text."""

    def _build_editor(self, layout):
        hint = QLabel('Blank line = new paragraph.')
        hint.setStyleSheet('color: gray; font-size: 8pt;')
        layout.addWidget(hint)
        self._edit = QTextEdit()
        self._edit.setMinimumHeight(80)
        self._edit.setMaximumHeight(200)
        layout.addWidget(self._edit)

    def get_value(self) -> str:
        text = self._edit.toPlainText().strip()
        paras = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()] or ['']
        inner = '\n'.join(f'<p>{p}</p>' for p in paras)
        css = self.field_def.selector_class
        return f'<div class="{css}">\n{inner}\n</div>'

    def set_value(self, html_fragment: str):
        paras = re.findall(r'<p[^>]*>(.*?)</p>', html_fragment, re.DOTALL | re.IGNORECASE)
        self._edit.setPlainText('\n\n'.join(_strip_tags(p) for p in paras))


class HtmlFieldWidget(FieldEditorWidget):
    """Raw HTML editor with syntax highlighting and optional markdown mode."""

    def _build_editor(self, layout):
        self._md_mode = False
        self._highlighter = None
        ctrl_row = QHBoxLayout()
        self._mode_btn = QPushButton('Switch to Markdown')
        self._mode_btn.setCheckable(True)
        self._mode_btn.setFixedWidth(160)
        self._mode_btn.clicked.connect(self._toggle_mode)
        ctrl_row.addWidget(self._mode_btn)
        if self.field_def.key == 'toc':
            gen_btn = QPushButton('Generate')
            gen_btn.setToolTip('Populate from all non-cover/blank sections in this guide')
            gen_btn.clicked.connect(self._generate_toc)
            ctrl_row.addWidget(gen_btn)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)
        self._edit = QTextEdit()
        self._edit.setAcceptRichText(False)
        self._edit.setMinimumHeight(80)
        self._edit.setMaximumHeight(200)
        self._highlighter = HTMLHighlighter(self._edit.document())
        layout.addWidget(self._edit)

    def _generate_toc(self):
        if not self.guide:
            return
        result = self.guide.parse_sections()
        if not result:
            return
        _, sections, _ = result
        names = [s.name for s in sections if s.type not in ('cover', 'blank')]
        items = '\n'.join(f'<li>{name}</li>' for name in names)
        self._edit.setPlainText(
            f'<div class="toc">\n<h3>Table of Contents</h3>\n<ul>\n{items}\n</ul>\n</div>'
        )

    def _inner_html(self, html: str) -> str:
        """Extract the content inside the outer wrapper element."""
        css = self.field_def.selector_class
        tag = self.field_def.selector_tag
        soup = BeautifulSoup(html, 'html.parser')
        elem = soup.find(tag, class_=css) if css else soup.find(tag)
        return elem.decode_contents() if elem else html

    def _wrap_html(self, inner: str) -> str:
        css = self.field_def.selector_class
        tag = self.field_def.selector_tag
        if css:
            return f'<{tag} class="{css}">\n{inner}\n</{tag}>'
        return f'<{tag}>\n{inner}\n</{tag}>'

    def _toggle_mode(self, checked):
        if checked:
            # HTML → Markdown
            inner = self._inner_html(self._edit.toPlainText())
            self._edit.setPlainText(_html_to_md(inner))
            if self._highlighter:
                self._highlighter.setDocument(None)
                self._highlighter = None
            self._mode_btn.setText('Switch to HTML')
            self._md_mode = True
        else:
            # Markdown → HTML
            inner = _md_to_html(self._edit.toPlainText())
            self._edit.setPlainText(self._wrap_html(inner))
            self._highlighter = HTMLHighlighter(self._edit.document())
            self._mode_btn.setText('Switch to Markdown')
            self._md_mode = False

    def get_value(self) -> str:
        text = self._edit.toPlainText().strip()
        if self._md_mode:
            return self._wrap_html(_md_to_html(text))
        return text

    def set_value(self, html_fragment: str):
        if self._md_mode:
            self._edit.setPlainText(_html_to_md(self._inner_html(html_fragment)))
        else:
            self._edit.setPlainText(html_fragment)


class ListFieldWidget(FieldEditorWidget):
    """Editable ordered list."""

    def _build_editor(self, layout):
        self._list = EditableListWidget()
        layout.addWidget(self._list)

    def get_value(self) -> str:
        items = self._list.get_items()
        li = '\n'.join(f'<li>{item}</li>' for item in items)
        css = self.field_def.selector_class
        return f'<div class="{css}">\n<h3>Table of Contents</h3>\n<ul>\n{li}\n</ul>\n</div>'

    def set_value(self, html_fragment: str):
        items = re.findall(r'<li[^>]*>(.*?)</li>', html_fragment, re.DOTALL | re.IGNORECASE)
        self._list.set_items([_strip_tags(i).strip() for i in items])


class TitledListFieldWidget(FieldEditorWidget):
    """Title + editable list (e.g. Setup)."""

    def _build_editor(self, layout):
        row = QHBoxLayout()
        row.addWidget(QLabel('Title:'))
        self._title = QLineEdit()
        row.addWidget(self._title)
        layout.addLayout(row)
        self._list = EditableListWidget()
        layout.addWidget(self._list)

    def get_value(self) -> str:
        title = self._title.text().strip()
        items = self._list.get_items()
        li = '\n'.join(f'<li>{item}</li>' for item in items)
        css = self.field_def.selector_class
        return f'<div class="{css}">\n<h3>{title}</h3>\n<ul>\n{li}\n</ul>\n</div>'

    def set_value(self, html_fragment: str):
        m = re.search(r'<h\d[^>]*>(.*?)</h\d>', html_fragment, re.DOTALL | re.IGNORECASE)
        if m:
            self._title.setText(_strip_tags(m.group(1)))
        items = re.findall(r'<li[^>]*>(.*?)</li>', html_fragment, re.DOTALL | re.IGNORECASE)
        self._list.set_items([_strip_tags(i).strip() for i in items])


class TitledHtmlFieldWidget(FieldEditorWidget):
    """Title + raw HTML body (e.g. Resolution)."""

    def _build_editor(self, layout):
        self._md_mode = False
        self._highlighter = None
        row = QHBoxLayout()
        row.addWidget(QLabel('Title:'))
        self._title = QLineEdit()
        row.addWidget(self._title)
        layout.addLayout(row)
        mode_row = QHBoxLayout()
        self._mode_btn = QPushButton('Switch to Markdown')
        self._mode_btn.setCheckable(True)
        self._mode_btn.setFixedWidth(160)
        self._mode_btn.clicked.connect(self._toggle_mode)
        mode_row.addWidget(self._mode_btn)
        mode_row.addStretch()
        layout.addLayout(mode_row)
        self._edit = QTextEdit()
        self._edit.setAcceptRichText(False)
        self._edit.setMinimumHeight(80)
        self._edit.setMaximumHeight(200)
        self._highlighter = HTMLHighlighter(self._edit.document())
        layout.addWidget(self._edit)

    def _toggle_mode(self, checked):
        if checked:
            html = self._edit.toPlainText()
            self._edit.setPlainText(_html_to_md(html))
            if self._highlighter:
                self._highlighter.setDocument(None)
                self._highlighter = None
            self._mode_btn.setText('Switch to HTML')
            self._md_mode = True
        else:
            md = self._edit.toPlainText()
            self._edit.setPlainText(_md_to_html(md))
            self._highlighter = HTMLHighlighter(self._edit.document())
            self._mode_btn.setText('Switch to Markdown')
            self._md_mode = False

    def get_value(self) -> str:
        title = self._title.text().strip()
        body = self._edit.toPlainText().strip()
        if self._md_mode:
            body = _md_to_html(body)
        css = self.field_def.selector_class
        return f'<div class="{css}">\n<h3>{title}</h3>\n{body}\n</div>'

    def set_value(self, html_fragment: str):
        m = re.search(r'<h\d[^>]*>(.*?)</h\d>', html_fragment, re.DOTALL | re.IGNORECASE)
        if m:
            self._title.setText(_strip_tags(m.group(1)))
        inner = re.sub(r'</?div[^>]*>', '', html_fragment, flags=re.IGNORECASE).strip()
        inner = re.sub(r'<h\d[^>]*>.*?</h\d>', '', inner, flags=re.DOTALL | re.IGNORECASE).strip()
        if self._md_mode:
            self._edit.setPlainText(_html_to_md(inner))
        else:
            self._edit.setPlainText(inner)


_FIELD_WIDGET_MAP = {
    'line':        LineFieldWidget,
    'story':       StoryFieldWidget,
    'text':        TextFieldWidget,
    'html':        HtmlFieldWidget,
    'list':        ListFieldWidget,
    'titled_list': TitledListFieldWidget,
    'titled_html': TitledHtmlFieldWidget,
}


def make_field_widget(field_def, guide=None) -> FieldEditorWidget:
    cls = _FIELD_WIDGET_MAP.get(field_def.kind, HtmlFieldWidget)
    return cls(field_def, guide=guide)


# ── Section editor panel ──────────────────────────────────────────────────────


class SectionEditorPanel(QWidget):
    saved = Signal()
    back_requested = Signal()

    def __init__(self, guide, section_id, parent=None):
        super().__init__(parent)
        self.guide = guide
        self.section_id = section_id
        self._field_widgets: list = []
        self._section = None
        self._setup_ui()
        self._load()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Top bar
        top = QHBoxLayout()
        back_btn = QPushButton('← Overview')
        back_btn.clicked.connect(self.back_requested)
        top.addWidget(back_btn)
        top.addStretch()
        self._html_toggle_btn = QPushButton('< > HTML')
        self._html_toggle_btn.setCheckable(True)
        self._html_toggle_btn.toggled.connect(self._toggle_html)
        top.addWidget(self._html_toggle_btn)
        layout.addLayout(top)

        # Section name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel('Section name:'))
        self.name_edit = QLineEdit()
        name_row.addWidget(self.name_edit)
        layout.addLayout(name_row)

        # Encounter set link (shown only for scenario sections)
        self._encounter_row = QWidget()
        enc_layout = QHBoxLayout(self._encounter_row)
        enc_layout.setContentsMargins(0, 0, 0, 0)
        enc_layout.addWidget(QLabel('Linked Encounter Set:'))
        self._encounter_combo = QComboBox()
        enc_layout.addWidget(self._encounter_combo)
        self._encounter_row.hide()
        layout.addWidget(self._encounter_row)

        # Stacked: index 0 = field editors, index 1 = raw HTML
        self.content_stack = QStackedWidget()

        # Index 0 — scrollable field editors
        fields_outer = QWidget()
        fo_layout = QVBoxLayout(fields_outer)
        fo_layout.setContentsMargins(0, 0, 0, 0)
        fo_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.NoFrame)
        self._fields_container = QWidget()
        self._fields_layout = QVBoxLayout(self._fields_container)
        self._fields_layout.setAlignment(Qt.AlignTop)
        self._fields_layout.setSpacing(8)
        scroll.setWidget(self._fields_container)
        fo_layout.addWidget(scroll, stretch=1)
        self.content_stack.addWidget(fields_outer)  # index 0

        # Index 1 — raw HTML editor
        self._html_editor = QTextEdit()
        self._html_editor.setAcceptRichText(False)
        self._html_editor.setFont(QFont('Courier', 10))
        HTMLHighlighter(self._html_editor.document())
        self.content_stack.addWidget(self._html_editor)  # index 1

        layout.addWidget(self.content_stack, stretch=1)

        save_btn = QPushButton('Save Section')
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load(self):
        result = self.guide.parse_sections()
        if result is None:
            return
        _, sections, _ = result
        section = next((s for s in sections if s.id == self.section_id), None)
        if section is None:
            return
        self._section = section
        self.name_edit.setText(section.name or '')

        # Populate encounter set dropdown for scenario sections
        if section.type == 'scenario':
            self._encounter_row.show()
            self._encounter_combo.clear()
            self._encounter_combo.addItem('— None —', None)
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

        self._populate_fields(section)
        if not SECTION_FIELDS.get(section.type):
            # blank / unknown: go straight to HTML editor
            self._html_toggle_btn.setChecked(True)

    def _populate_fields(self, section):
        """Build field widgets from SECTION_FIELDS and load values from html_content."""
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._field_widgets.clear()

        field_defs = SECTION_FIELDS.get(section.type, [])
        if not field_defs:
            lbl = QLabel('No predefined fields for this section type.')
            lbl.setStyleSheet('color: gray; font-style: italic;')
            self._fields_layout.addWidget(lbl)
            return

        soup = BeautifulSoup(f'<div>{section.html_content}</div>', 'html.parser')
        wrapper = soup.find('div')
        for fd in field_defs:
            w = make_field_widget(fd, guide=self.guide)
            w.load_from_soup(wrapper)
            self._fields_layout.addWidget(w)
            self._field_widgets.append(w)

    # ── HTML generation ───────────────────────────────────────────────────────

    def _build_section_html(self) -> str:
        """Apply field widget values surgically to the section's html_content."""
        if self.content_stack.currentIndex() == 1:
            return self._html_editor.toPlainText()
        if self._section is None:
            return ''
        soup = BeautifulSoup(
            f'<div>{self._section.html_content}</div>', 'html.parser'
        )
        wrapper = soup.find('div')
        for w in self._field_widgets:
            w.apply_to_soup(wrapper)
        return wrapper.decode_contents()

    # ── HTML toggle ───────────────────────────────────────────────────────────

    def _toggle_html(self, checked):
        if checked:
            self._html_editor.setPlainText(self._build_section_html())
            self.content_stack.setCurrentIndex(1)
            self._html_toggle_btn.setText('Form view')
        else:
            if self._section is not None:
                self._section.html_content = self._html_editor.toPlainText()
                self._populate_fields(self._section)
            self.content_stack.setCurrentIndex(0)
            self._html_toggle_btn.setText('< > HTML')

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        result = self.guide.parse_sections()
        if result is None:
            return
        preamble, sections, postamble = result
        section = next((s for s in sections if s.id == self.section_id), None)
        if section is None:
            return
        section.name = self.name_edit.text()
        section.html_content = self._build_section_html()
        if self._encounter_row.isVisible():
            section.encounter_set_id = self._encounter_combo.currentData()
        if self._section is not None:
            self._section.html_content = section.html_content
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
        sections.append(GuideSection.new(section_type, name))
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
