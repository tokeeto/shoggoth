"""
Custom text editor widget for Arkham Horror card text with syntax highlighting and autocomplete
"""
from PySide6.QtWidgets import QTextEdit, QCompleter, QToolTip, QFrame
from PySide6.QtCore import Qt, QStringListModel, QRect, QPoint
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
    QTextCursor, QPalette, QFontDatabase
)
import re

from shoggoth.files import font_dir

_editor_font_family = None


def _load_editor_font():
    """Register ShoggothEditorFont.otf (built by scripts/build_editor_font.py) and
    return its family name. The font's 'calt' ligature rules render markup tags like
    "<action>" as their icon glyph while leaving the underlying characters editable
    one at a time, so backspace still un-types the tag letter by letter."""
    global _editor_font_family
    if _editor_font_family is not None:
        return _editor_font_family

    path = font_dir / "ShoggothEditorFont.otf"
    families = []
    if path.exists():
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)

    _editor_font_family = families[0] if families else QFont().defaultFamily()
    return _editor_font_family


def _ligatures_enabled():
    """Read the 'enable_ligatures' setting. Defaults to True when no app/config
    is available yet (e.g. widgets constructed before the main window exists)."""
    import shoggoth
    config = getattr(getattr(shoggoth, 'app', None), 'config', None)
    if config is None:
        return True
    return config.getboolean('Shoggoth', 'enable_ligatures', True)


def _resolve_editor_font_family():
    """Family name for non-monospace text edits: ShoggothEditorFont when
    ligatures are enabled, otherwise the plain system font so markup tags
    like "<action>" stay literal characters instead of being drawn as icons."""
    return _load_editor_font() if _ligatures_enabled() else QFont().defaultFamily()


def refresh_ligature_setting():
    """Re-apply the current ligature setting's font family to every open,
    non-monospace ArkhamTextEdit. Called after the setting changes so already
    open card editors update without needing to be reopened."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if not app:
        return
    family = _resolve_editor_font_family()
    for widget in app.allWidgets():
        if isinstance(widget, ArkhamTextEdit) and not widget.monospace:
            font = widget.font()
            font.setFamily(family)
            widget.setFont(font)


class ArkhamTextHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Arkham Horror card text"""

    # Colors for light and dark backgrounds
    _COLORS_LIGHT = {
        'tag':     "#3355bb",  # Blue
        'unknown': "#cc2222",  # Red
        'icon':    "#a05020",  # Brown-orange
        'bold':    "#225522",  # Dark green
        'italic':  "#771188",  # Purple
        'trait':   "#886600",  # Dark gold
    }
    _COLORS_DARK = {
        'tag':     "#7799ff",  # Light blue
        'unknown': "#ff6666",  # Light red
        'icon':    "#ffaa66",  # Light orange
        'bold':    "#66cc66",  # Light green
        'italic':  "#cc88ff",  # Light purple
        'trait':   "#ddcc44",  # Gold
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.formats = {}
        self._is_dark = None  # unknown until first highlight
        self._build_formats(self._detect_dark())

    def _detect_dark(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            return app.palette().color(QPalette.ColorRole.Window).lightness() < 128
        return False

    def _build_formats(self, is_dark):
        self._is_dark = is_dark
        colors = self._COLORS_DARK if is_dark else self._COLORS_LIGHT

        tag_format = QTextCharFormat()
        tag_format.setForeground(QColor(colors['tag']))
        self.formats['tag'] = tag_format

        unknown_format = QTextCharFormat()
        unknown_format.setForeground(QColor(colors['unknown']))
        unknown_format.setUnderlineStyle(QTextCharFormat.WaveUnderline)
        unknown_format.setUnderlineColor(QColor(colors['unknown']))
        self.formats['unknown'] = unknown_format

        icon_format = QTextCharFormat()
        icon_format.setForeground(QColor(colors['icon']))
        self.formats['icon'] = icon_format

        bold_format = QTextCharFormat()
        bold_format.setFontWeight(QFont.Bold)
        bold_format.setForeground(QColor(colors['bold']))
        self.formats['bold'] = bold_format

        italic_format = QTextCharFormat()
        italic_format.setFontItalic(True)
        italic_format.setForeground(QColor(colors['italic']))
        self.formats['italic'] = italic_format

        trait_format = QTextCharFormat()
        trait_format.setFontItalic(True)
        trait_format.setForeground(QColor(colors['trait']))
        self.formats['trait'] = trait_format

        # Define known tags
        self.icon_tags = {
            'blessing', 'curse', 'tablet', 'cultist', 'elder_sign', 'skull',
            'auto_fail', 'elder_thing', 'frost', 'agility', 'agi', 'combat',
            'com', 'intellect', 'int', 'willpower', 'action', 'free', 'fast',
            'reaction', 'resource', 'damage', 'horror', 'clues', 'doom',
            'guardian', 'seeker', 'rogue', 'mystic', 'survivor', 'unique',
            'per', 'per_large', 'investigator', 'per_investigator', 'codex', 'star', 'dash', 'question',
            'resolution', 'bullet', 'day', 'night', 'fleur', 'entry', 'sign_1',
            'sign_2', 'sign_3', 'sign_4', 'sign_5'
        }

        self.special_tags = {
            'for', 'prey', 'rev', 'spawn', 'obj', 'objective', 'center', 'left',
            'right', 'story', 'blockquote', 'quote', 'dquote', 'quoteend', 'dquoteend',
            'n', 'name', 'copy', 'exi', 'exn', 'esn', 'est', 'esi', 'copyright',
            'image', 'margin',
            '/center', '/left', '/right', '/story', '/blockquote'
        }

        self.format_tags = {
            'b', '/b', 'i', '/i', 'bi', '/bi', 't', '/t', 'icon', '/icon'
        }

        self.known_traits = {
            'Power', 'Prison', "R'lyeh", 'Spider', 'Witch House',
            'Arkham', 'Innocent', 'Haunted', "St Mary's", 'Mexico City',
            'Uncharted', 'Lodge', 'Montréal', 'Resident', 'Providence',
            'Dark Young', 'Tactic', 'Private', 'Forgotten', 'Summit', 'Job',
            'Carnevale', 'Fated', 'Grant', 'Serpent', 'Cthulhu', 'Byakhee',
            'Shoggoth', 'Nest', 'Otherworld', 'Criminal', 'Assistant', 'Shattered',
            'Supply', 'Key', 'Script', 'Locus Site', 'Forest', 'Charm', 'Hex',
            'Present', 'Staff', 'Unpracticed', 'Curse', 'Havana', 'Cave', 'Elder Thing',
            'Field', 'Sorcerer', 'Ruin', 'Casino', 'Gug', 'Road', 'Weapon', 'Miskatonic',
            'Injury', 'Basement', 'Talent', 'Pnakotus', 'Set', 'Incomplete', 'Coterie',
            'City', 'Rot', 'Manor', 'Buenos Aires', 'Saturnite', 'Unhallowed', 'Expert',
            'Return', 'Double', 'Mutated', 'Enraged', 'Ancient One', 'Stable',
            'Boat', 'Crime Scene', 'Nightgaunt', 'Detective', 'Dhole', 'Innate',
            'Altered', 'Trick', 'Gambit', 'Blunder', 'Hunter', 'Lift', 'Brotherhood',
            'Arkham Asylum', 'Madness', 'Seafloor', 'Practiced', 'Avatar', 'Humanoid',
            'Patron', 'Game', 'Spell', 'Artifact', 'Entrepreneur', 'Spirit', 'Favor',
            'Cart', 'Synergy', 'Unlit', 'Ghoul', 'Mi-Go', 'Temple', 'Front', 'Fortune',
            'Relic', 'Sanctum', 'Tindalos', 'Scientist', 'Falcon Point', 'Rooftop',
            'Star Spawn', 'Hemlock Vale', 'Condition', 'Unstable', 'Keeper', 'Tome',
            'Hideout', 'Bystander', 'Flaw', 'Ooth-Nargai', 'Emissary', 'Colour',
            'Wilderness', 'Tool', 'Glacier', 'Ship', 'Mainland', 'Risen', 'Bayou',
            'Drifter', 'Silver Twilight', 'Dilemma', 'Present-Day', 'Mystery', 'River',
            'Endtimes', 'Jungle', 'Dreamlands', 'Town', 'Mountains', 'Ranged', 'Research',
            'Spectral', 'Mask', 'Castle', 'Bog', 'Hardship', 'Woods', 'Farm', 'Station',
            'Lit', 'Future', 'Walkway', 'Bold', 'Cairo', 'Clothing', 'London', 'Dreamer',
            'Eidolon', 'Sunken', 'Oriab', 'Tenochtitlán', 'Abyss', 'Dunwich', 'Leng',
            'Armor', 'Wastes', 'Desperate', 'Mountain', 'Terror', 'Mirage', 'Marrakesh',
            'Allied', 'Hall', 'Salem', 'Circle', 'Port', 'Plot', 'Mnar', 'Kingsport',
            'Melee', 'Augury', 'Island', 'Act 1', 'Stowaway', 'Yoth', 'Chosen', 'Upgrade',
            'Portal', 'Lead', 'Reporter', 'Forbidden', 'Broken', 'Blight', 'Enclave',
            'Possessed', 'Room', 'Dionsaur', 'Service', 'New Orleans', 'Outsider', 'Skai',
            'Insight', 'Boon', 'Blessed', 'Illicit', 'Alexandria', 'Past', 'Creature',
            'Item', 'Expedition', 'Witch', 'Elite', 'Yithian', 'Leader', 'Syndicate',
            'Vehicle', 'Cursed', 'Yuggoth', 'Eztli', 'Tower', 'Creature', 'Police', 'Central',
            'Cosmos', 'Scholar', 'Flora', 'Veteran', 'Civic', 'Paris', 'Guest', 'Surface',
            'Eldritch', 'Servitor', 'Warden', 'Believer', 'Venice', 'Abandoned', 'Connection',
            'Paradox', 'Firearm', 'Covenant', 'Train', 'Restricted', 'Developed', 'Ancient',
            'Dinosaur', 'Dormant', 'Coastal', 'Oozified', 'Distortion', 'Scion', 'Pact',
            'Glyph', 'Evidence', 'Kadath', 'Ocean', 'Occult', 'Extraterrestrial', 'Instrument',
            'Monster', 'Science', 'Item', 'Public', 'Task', 'Familiar', 'Conspirator',
            'Hybrid', 'Geist', 'Hazard', 'Desert', 'New York City', 'Ruined', 'Clairvoyant',
            'Song', 'Clover Club', 'Medic', 'Construct', 'Resolute', 'Wilderness Monster',
            'Kuala Lumpur', 'Obstacle', 'Crew', 'Tentacle', 'Second Floor', 'Campsite',
            'Exhibit', 'Bridge', 'Third Floor', 'Riverside', 'Innsmouth', 'Passageway',
            'Performer', 'Rival', 'Manifold', 'Void', 'Scheme', 'Istanbul', 'Attack',
            'Completed', 'Tarot', 'Midtown', 'Composure', 'Rail', 'Historical Society',
            'Sentinel Hill', 'Ritual Site', 'Ritual', 'Ruins', 'Ally', 'Government', 'Steps',
            'Bazaar', 'Ghast', 'Satellite', 'Dark', 'Poison', 'Agency', 'Wayfarer',
            'Lantern Club', 'Hazard Glyph', 'Cultist', 'Prop', 'Suspect', 'Inconspicuous',
            'Unbroken', 'Insect', 'Graveyard', 'Ground Floor', 'Ruins Ancient One', 'Depths',
            'Corruption', 'Vault', 'Shantak', 'Role', 'Artist', 'Misfortune', 'Ooze', 'Trap',
            'Lair', 'Vale', 'Footwear', 'Summon', 'Omen', ' Talent', 'Deep One', 'Socialite',
            'Machination', "Y'ha-nthlei", 'Extradimensional', 'Improvised', 'Zoog', 'Apiary',
            'Abomination'
        }

        # Compile patterns
        self.tag_pattern = re.compile(r'<([^>]+)>|\[([^\]]+)\]')
        self.double_bracket_pattern = re.compile(r'\[\[.*?\]\]')
        self.bold_pattern = re.compile(r'<b>.*?</b>')
        self.italic_pattern = re.compile(r'<i>.*?</i>')
        self.trait_pattern = re.compile(r'<t>.*?</t>')

    def highlightBlock(self, text):
        """Apply syntax highlighting to a block of text"""
        # Rebuild formats if the light/dark mode has changed since last highlight
        is_dark = self._detect_dark()
        if is_dark != self._is_dark:
            self._build_formats(is_dark)

        # First, handle bold and italic (these override other highlighting)
        for match in self.bold_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats['bold'])

        for match in self.italic_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats['italic'])

        for match in self.trait_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats['trait'])

        # Handle double brackets
        for match in self.double_bracket_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats['trait'])

        # Handle all tags
        for match in self.tag_pattern.finditer(text):
            start = match.start()
            length = match.end() - match.start()

            # Extract tag name (could be from <...> or [...]
            tag_content = match.group(1) or match.group(2)
            if not tag_content:
                continue

            # Extract just the tag name (remove attributes for <image ...> tags)
            tag_name = tag_content.split()[0].lower()

            # Determine format based on tag type
            if tag_name in self.icon_tags:
                self.setFormat(start, length, self.formats['icon'])
            elif tag_name in self.special_tags:
                self.setFormat(start, length, self.formats['tag'])
            elif tag_name in self.format_tags:
                # These are handled by bold/italic patterns above
                pass
            else:
                # Unknown tag - mark in red
                self.setFormat(start, length, self.formats['unknown'])


# Live-editing <-> stored-text translation ------------------------------------------
#
# Two of Qt's QTextDocument round-trips lose information the card markup actually
# cares about, so ArkhamTextEdit/NbspTextEdit translate at the toPlainText()/
# setPlainText() boundary rather than storing the app's real format live:
#
# 1. Non-breaking space (U+00A0): QTextDocument stores it fine (insertText/
#    setPlainText/insertPlainText all keep it verbatim -- confirmed via
#    document().toRawText(), which reflects the real stored characters), but
#    QTextDocument.toPlainText() (and QTextEdit.toPlainText(), and QTextBlock.text())
#    silently downgrades it to a regular U+0020 space on the way out, for reasons
#    undocumented but easy to reproduce with a bare vanilla QTextEdit. toRawText()
#    doesn't do this, hence using it below.
#
# 2. Paragraph vs. line break: Qt's Return already inserts a real paragraph break
#    (a new QTextBlock, U+2029 between blocks in toRawText()) and Shift+Return
#    already inserts a soft line break within the same block (U+2028) -- this is
#    native QTextEdit behavior, nothing we wire up ourselves. But toPlainText()
#    collapses *both* down to a plain '\n', losing the distinction the card markup
#    depends on: a literal '\n' in a card's text is a full paragraph break (extra
#    vertical space -- PieceType.PAR in renderer/richtext/layout.py), while a
#    literal '<br>' tag is a tight same-paragraph line break (PieceType.BREAK, no
#    extra space). So here U+2029 maps to '\n' and U+2028 maps to the literal
#    '<br>' tag text, each way, keeping Enter == paragraph break and
#    Shift+Enter == '<br>' consistent with how the renderer already reads them.
NBSP = ' '
_PARAGRAPH_SEPARATOR = ' '
_LINE_SEPARATOR = ' '
_BREAK_TAG = '<br>'


class _LiveTextEditMixin:
    """Shared Shift+Space / Enter / toPlainText / setPlainText handling -- see the
    module note above. Mixed into both ArkhamTextEdit and NbspTextEdit."""

    # Extra top margin (px) on a real paragraph break, so it's visually
    # distinguishable at a glance from a same-paragraph Shift+Enter line break --
    # otherwise both look identical while editing even though the renderer spaces
    # them very differently (PieceType.PAR vs PieceType.BREAK).
    _PARAGRAPH_SPACING_PX = 10

    def _handle_nbsp_shortcut(self, event):
        """Insert a real non-breaking space and return True if this event was
        Shift+Space."""
        if event.key() == Qt.Key_Space and event.modifiers() == Qt.ShiftModifier:
            cursor = self.textCursor()
            cursor.insertText(NBSP)
            self.setTextCursor(cursor)
            return True
        return False

    def _handle_paragraph_break_shortcut(self, event):
        """Let Qt insert its native paragraph break for a plain Return/Enter (no
        Shift -- Shift+Return's same-paragraph line break is left to Qt's own
        default handling), then mark the new block. Returns True if handled."""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            super(_LiveTextEditMixin, self).keyPressEvent(event)
            self._mark_paragraph_break(self.textCursor())
            return True
        return False

    def _mark_paragraph_break(self, cursor):
        fmt = cursor.blockFormat()
        fmt.setTopMargin(self._PARAGRAPH_SPACING_PX)
        cursor.setBlockFormat(fmt)

    def _mark_all_paragraph_breaks(self):
        """Apply _mark_paragraph_break retroactively to every block after the
        first. Needed once after bulk-loading content (setPlainText) since that
        doesn't go through keyPressEvent's per-Enter marking."""
        cursor = QTextCursor(self.document())
        block = self.document().begin().next()
        while block.isValid():
            cursor.setPosition(block.position())
            self._mark_paragraph_break(cursor)
            block = block.next()

    def toPlainText(self):
        raw = self.document().toRawText()
        return raw.replace(_PARAGRAPH_SEPARATOR, '\n').replace(_LINE_SEPARATOR, _BREAK_TAG)

    def setPlainText(self, text):
        # '\n' already becomes a real paragraph break via Qt's own setPlainText; only
        # '<br>' needs translating up front so it displays as a soft break in place.
        super().setPlainText(text.replace(_BREAK_TAG, _LINE_SEPARATOR) if text else text)
        self._mark_all_paragraph_breaks()


class ArkhamTextEdit(_LiveTextEditMixin, QTextEdit):
    """Custom text edit widget with autocomplete for Arkham Horror card text"""

    def __init__(self, parent=None, monospace=False):
        super().__init__(parent)
        self.monospace = monospace

        # Drop the native sunken scroll-area frame — it reads as a heavier box than
        # sibling QLineEdit-style fields and throws off alignment against them; every
        # caller wants this, so it belongs here rather than repeated at each call site.
        self.setFrameShape(QFrame.NoFrame)
        # QTextDocument's own margin (default 4px) would stack on top of the compact
        # editor theme's own CSS padding, double-padding the text. The CSS padding
        # alone is the intended inset, so this is zeroed out for the same reason.
        self.document().setDocumentMargin(0)

        # ShoggothEditorFont's ligatures render markup tags as icon glyphs, which is
        # what card text fields want — but that same substitution obfuscates raw JSON
        # (e.g. a "<action>" inside a text value stops looking like the literal
        # characters being edited). Callers displaying raw data (JSON editors) should
        # pass monospace=True for a plain, readable fixed-pitch font instead.
        if monospace:
            editor_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        else:
            editor_font = QFont(_resolve_editor_font_family())
        editor_font.setPointSize(self.font().pointSize())
        self.setFont(editor_font)

        # Enable syntax highlighting
        self.highlighter = ArkhamTextHighlighter(self.document())

        # Setup autocomplete
        self.setup_autocomplete()

        # Track if we're currently showing autocomplete
        self.completing = False

    def setup_autocomplete(self):
        """Setup autocomplete with common tags"""
        # Define all available tags
        tags = [
            # Formatting tags
            '<b>', '</b>', '<i>', '</i>', '<bi>', '</bi>', '<t>', '</t>',
            '[[', ']]',

            # Special text tags
            '<for>', '<prey>', '<rev>', '<spawn>', '<obj>', '<objective>',
            '<center>', '</center>', '<left>', '</left>', '<right>', '</right>',
            '<story>', '</story>', '<blockquote>', '</blockquote>',

            # Icon tags - stats
            '<agility>', '<agi>', '[agility]',
            '<combat>', '<com>', '[combat]',
            '<intellect>', '<int>', '[intellect]',
            '<willpower>', '[willpower]',

            # Icon tags - actions
            '<action>', '[action]',
            '<free>', '[fast]',
            '<reaction>',

            # Icon tags - tokens
            '<blessing>', '<curse>', '<tablet>', '<cultist>', '<elder_sign>',
            '<skull>', '<auto_fail>', '<elder_thing>', '<frost>',

            # Icon tags - resources
            '<resource>', '<damage>', '<horror>', '<clues>', '<doom>',
            '<per>', '<per_large>', '<investigator>', '[per_investigator]',

            # Icon tags - classes
            '<guardian>', '<seeker>', '<rogue>', '<mystic>', '<survivor>',

            # Special tags
            '<unique>', '<codex>', '<star>', '<dash>',
            '<question>', '<resolution>', '<bullet>',
            '<day>', '<night>',

            # Replacement tags
            '<quote>', '<dquote>', '<quoteend>', '<dquoteend>',

            # Dynamic tags
            '<name>', '<copy>', '<exi>', '<exn>', '<esn>', '<est>', '<esi>',
            '<copyright>',
        ]

        # Create completer
        self.completer = QCompleter(tags)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.activated.connect(self.insert_completion)

        # Create model for dynamic filtering
        self.completer_model = QStringListModel(tags)
        self.completer.setModel(self.completer_model)

    def insert_completion(self, completion):
        """Insert the selected completion"""
        cursor = self.textCursor()

        # Get the text that was already typed
        prefix = self.text_under_cursor()

        # Calculate how many characters to insert (completion minus what's already typed)
        if prefix:
            # Remove the prefix from the completion
            remaining = completion[len(prefix):]
            cursor.insertText(remaining)
        else:
            cursor.insertText(completion)

        self.setTextCursor(cursor)
        self.completing = False

    def text_under_cursor(self):
        """Get the partial tag text under cursor"""
        cursor = self.textCursor()
        text = cursor.block().text()
        position = cursor.positionInBlock()

        # Look backwards for '<' or '[['
        start = -1
        for i in range(position - 1, -1, -1):
            if text[i] == '<':
                start = i
                break
            elif i > 0 and text[i-1:i+1] == '[[':
                start = i - 1
                break

        if start == -1:
            return ''

        return text[start:position]

    def keyPressEvent(self, event):
        """Handle key press events for autocomplete and formatting shortcuts"""
        # Shift+Space inserts a non-breaking space - see _LiveTextEditMixin above.
        if self._handle_nbsp_shortcut(event):
            return

        # Handle formatting shortcuts
        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_B:
                self.insert_formatting_tag('b')
                return
            elif event.key() == Qt.Key_I:
                self.insert_formatting_tag('i')
                return
            elif event.key() == Qt.Key_T:
                self.insert_formatting_tag('t')
                return

        # If completer is visible and we pressed Enter/Return/Tab, accept completion
        if self.completer.popup().isVisible():
            if event.key() in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Tab):
                event.ignore()
                return

        # A plain Return/Enter creates a new paragraph - see _LiveTextEditMixin above.
        if self._handle_paragraph_break_shortcut(event):
            return

        # Handle normal key press
        super().keyPressEvent(event)

        # Get text under cursor
        completion_prefix = self.text_under_cursor()

        # Show completer if we typed '<' or '[['
        if completion_prefix and (completion_prefix.startswith('<') or completion_prefix.startswith('[[')):
            if completion_prefix != self.completer.completionPrefix():
                self.completer.setCompletionPrefix(completion_prefix)
                self.completer.popup().setCurrentIndex(
                    self.completer.completionModel().index(0, 0)
                )

            # Position popup under cursor
            cursor_rect = self.cursorRect()
            cursor_rect.setWidth(
                self.completer.popup().sizeHintForColumn(0)
                + self.completer.popup().verticalScrollBar().sizeHint().width()
            )
            cursor_rect.translate(0, cursor_rect.height())
            self.completer.complete(cursor_rect)
            self.completing = True
        else:
            self.completer.popup().hide()
            self.completing = False

    def insert_formatting_tag(self, tag):
        """Insert a formatting tag pair around selected text or at cursor"""
        cursor = self.textCursor()

        if cursor.hasSelection():
            # Get selected text
            selected_text = cursor.selectedText()

            # Replace with tagged version
            tagged_text = f'<{tag}>{selected_text}</{tag}>'
            cursor.insertText(tagged_text)
        else:
            # No selection - just insert the tag pair at cursor
            cursor.insertText(f'<{tag}></{tag}>')

            # Move cursor between the tags
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, len(f'</{tag}>'))
            self.setTextCursor(cursor)

    def focusInEvent(self, event):
        """Handle focus in event"""
        if self.completer:
            self.completer.setWidget(self)
        super().focusInEvent(event)


class NbspTextEdit(_LiveTextEditMixin, QTextEdit):
    """A plain QTextEdit (no Arkham syntax highlighting/autocomplete) that still
    supports Shift+Space to insert a non-breaking space (see _LiveTextEditMixin), for
    fields like flavor text that use a bare QTextEdit rather than ArkhamTextEdit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # See ArkhamTextEdit.__init__ — same reasoning for dropping the native frame
        # and zeroing the document margin (avoids double-padding with the CSS padding).
        self.setFrameShape(QFrame.NoFrame)
        self.document().setDocumentMargin(0)

    def keyPressEvent(self, event):
        if self._handle_nbsp_shortcut(event):
            return
        if self._handle_paragraph_break_shortcut(event):
            return
        super().keyPressEvent(event)


class LabeledArkhamTextEdit(QTextEdit):
    """A labeled Arkham text edit widget for use in forms"""

    def __init__(self, label_text, parent=None):
        from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

        super().__init__(parent)

        # Create container widget
        self.container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(label_text)
        self.label.setMinimumWidth(110)
        self.label.setAlignment(Qt.AlignTop)

        self.input = ArkhamTextEdit()
        self.input.setMaximumHeight(140)

        layout.addWidget(self.label)
        layout.addWidget(self.input)

        self.container.setLayout(layout)

    def toPlainText(self):
        return self.input.toPlainText()

    def setPlainText(self, text):
        self.input.setPlainText(text)