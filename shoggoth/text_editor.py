"""
Custom text editor widget for Arkham Horror card text with syntax highlighting and autocomplete
"""
from PySide6.QtWidgets import QTextEdit, QCompleter, QToolTip
from PySide6.QtCore import Qt, QStringListModel, QRect, QPoint
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
    QTextCursor, QPalette
)
import re


class ArkhamTextHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Arkham Horror card text"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Define formatting styles
        self.formats = {}
        
        # Tag format (for known <tag> and [[tag]])
        tag_format = QTextCharFormat()
        tag_format.setForeground(QColor("#0066cc"))  # Blue
        tag_format.setFontWeight(QFont.Bold)
        self.formats['tag'] = tag_format
        
        # Unknown tag format (for unknown tags)
        unknown_format = QTextCharFormat()
        unknown_format.setForeground(QColor("#cc0000"))  # Red
        unknown_format.setFontWeight(QFont.Bold)
        unknown_format.setUnderlineStyle(QTextCharFormat.WaveUnderline)
        unknown_format.setUnderlineColor(QColor("#cc0000"))
        self.formats['unknown'] = unknown_format
        
        # Icon tag format (for icon tags like <blessing>, <curse>)
        icon_format = QTextCharFormat()
        icon_format.setForeground(QColor("#cc6600"))  # Orange
        icon_format.setFontWeight(QFont.Bold)
        self.formats['icon'] = icon_format
        
        # Bold format
        bold_format = QTextCharFormat()
        bold_format.setFontWeight(QFont.Bold)
        bold_format.setForeground(QColor("#2e7d32"))  # Green
        self.formats['bold'] = bold_format
        
        # Italic format
        italic_format = QTextCharFormat()
        italic_format.setFontItalic(True)
        italic_format.setForeground(QColor("#7b1fa2"))  # Purple
        self.formats['italic'] = italic_format
        
        # Define known tags
        self.icon_tags = {
            'blessing', 'curse', 'tablet', 'cultist', 'elder_sign', 'skull',
            'auto_fail', 'elder_thing', 'frost', 'agility', 'agi', 'combat',
            'com', 'intellect', 'int', 'willpower', 'action', 'free', 'fast',
            'reaction', 'resource', 'damage', 'horror', 'clues', 'doom',
            'guardian', 'seeker', 'rogue', 'mystic', 'survivor', 'unique',
            'per', 'per_investigator', 'codex', 'star', 'dash', 'question',
            'resolution', 'bullet', 'day', 'night', 'fleur', 'entry', 'sign_1',
            'sign_2', 'sign_3', 'sign_4', 'sign_5'
        }
        
        self.special_tags = {
            'for', 'prey', 'rev', 'spawn', 'obj', 'objective', 'center', 'left',
            'right', 'story', 'blockquote', 'quote', 'dquote', 'quoteend', 'dquoteend',
            'n', 'name', 'copy', 'exi', 'exn', 'esn', 'est', 'esi', 'copyright',
            'image'
        }
        
        self.format_tags = {
            'b', '/b', 'i', '/i', 'bi', '/bi', 't', '/t', 'icon', '/icon',
            '/center', '/left', '/right', '/story', '/blockquote'
        }
        
        # Compile patterns
        self.tag_pattern = re.compile(r'<([^>]+)>|\[([^\]]+)\]')
        self.double_bracket_pattern = re.compile(r'\[\[.*?\]\]')
        self.bold_pattern = re.compile(r'<b>.*?</b>')
        self.italic_pattern = re.compile(r'<i>.*?</i>')
    
    def highlightBlock(self, text):
        """Apply syntax highlighting to a block of text"""
        # First, handle bold and italic (these override other highlighting)
        for match in self.bold_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats['bold'])
        
        for match in self.italic_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats['italic'])
        
        # Handle double brackets
        for match in self.double_bracket_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats['bold'])
        
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


class ArkhamTextEdit(QTextEdit):
    """Custom text edit widget with autocomplete for Arkham Horror card text"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
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
            '<per>', '[per_investigator]',
            
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