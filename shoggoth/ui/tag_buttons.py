"""
A small row of buttons that insert common markup tags into an ArkhamTextEdit.

Two kinds of button, matching how the tags work:
  * pair   — a start+end tag pair that wraps the selection (or the cursor), like Ctrl+B
  * single — one standalone tag placed after the cursor / current selection
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase

from shoggoth.files import font_dir
from shoggoth.i18n import tr

# name -> spec. `label` is a translation key, or `icon_glyph` shows a glyph of the icon
# font instead (falling back to the literal tag text when the font isn't available).
TAG_BUTTON_SPECS = {
    'story': {'kind': 'pair', 'label': "TAG_BTN_STORY", 'start': '<blockquote>', 'end': '</blockquote>'},
    'forced': {'kind': 'single', 'label': "TAG_BTN_FORCED", 'tag': '<for>'},
    'elder_sign': {'kind': 'single', 'icon_glyph': 'E', 'tag': '<elder_sign>'},
    'bold': {'kind': 'pair', 'label': "TAG_BTN_BOLD", 'start': '<b>', 'end': '</b>', 'style': 'bold'},
    'italic': {'kind': 'pair', 'label': "TAG_BTN_ITALIC", 'start': '<i>', 'end': '</i>', 'style': 'italic'},
    'valign': {'kind': 'single', 'label': "TAG_BTN_VALIGN", 'tag': '<valign>'},
    'image': {'kind': 'single', 'label': "TAG_BTN_IMAGE", 'tag': '<image src="path" color="red">',
              'select': 'path'},
}

DEFAULT_TAG_BUTTONS = ('forced', 'elder_sign', 'bold', 'italic', 'valign', 'image')
# Campaign text (act/agenda backs, story) is mostly blockquote prose
STORY_TAG_BUTTONS = ('story',) + DEFAULT_TAG_BUTTONS

_icon_family = None


def _icon_font_family():
    """Family of the card icon font (AHLCGSymbol), or None if the asset pack lacks it."""
    global _icon_family
    if _icon_family is None:
        families = []
        path = font_dir / "AHLCGSymbol.otf"
        if path.exists():
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
        _icon_family = families[0] if families else ""
    return _icon_family or None


class TagButtonRow(QWidget):
    """Buttons for `names` (keys of TAG_BUTTON_SPECS) acting on `edit`."""

    def __init__(self, edit, names=DEFAULT_TAG_BUTTONS, parent=None):
        super().__init__(parent)
        self.edit = edit

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        for name in names:
            spec = TAG_BUTTON_SPECS[name]
            button = QPushButton()
            button.setProperty("chip", "tag")
            # Keep focus (and the selection) in the text edit while clicking
            button.setFocusPolicy(Qt.NoFocus)
            self._style_button(button, spec)
            button.clicked.connect(lambda _=False, spec=spec: self._apply(spec))
            layout.addWidget(button)
        layout.addStretch()

    @staticmethod
    def _style_button(button, spec):
        if 'icon_glyph' in spec:
            family = _icon_font_family()
            if family:
                button.setText(spec['icon_glyph'])
                font = QFont(family)
                font.setPointSize(12)
                button.setFont(font)
            else:
                button.setText(spec['tag'])
            button.setToolTip(spec['tag'])
            return

        button.setText(tr(spec['label']))
        font = button.font()
        if spec.get('style') == 'bold':
            font.setBold(True)
        elif spec.get('style') == 'italic':
            font.setItalic(True)
        button.setFont(font)
        button.setToolTip(spec['tag'] if spec['kind'] == 'single' else f"{spec['start']}…{spec['end']}")

    def _apply(self, spec):
        edit = self.edit
        cursor = edit.textCursor()
        cursor.beginEditBlock()
        if spec['kind'] == 'pair':
            edit.insert_tag_pair(spec['start'], spec['end'])
        else:
            edit.insert_single_tag(spec['tag'], spec.get('select'))
        cursor.endEditBlock()
        edit.setFocus()
