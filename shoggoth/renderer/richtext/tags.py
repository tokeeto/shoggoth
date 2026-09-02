"""The rich-text tag vocabulary and the trie / regex machinery that matches it.

* formatting tags (`FORMATTING_TAGS`)  -> a `Token`, trie-matched
* font-icon tags (`FONT_ICON_TAGS`)    -> one AHLCGSymbol glyph char, trie-matched
* replacement tags (`REPLACEMENT_TAGS`) -> plain string substitution, done first
* parametric tags (`<size 30>`, `<font "x">`, ...) -> matched by the regexes here
"""

import re

from shoggoth.files import font_dir
from shoggoth.i18n import tr
from shoggoth.renderer.richtext.model import Align, Token, TokenType


FORMATTING_TAGS = {
    '<b>': Token(TokenType.FORMAT, 'bold', start=True),
    '</b>': Token(TokenType.FORMAT, 'bold', start=False),
    '<i>': Token(TokenType.FORMAT, 'italic', start=True),
    '</i>': Token(TokenType.FORMAT, 'italic', start=False),
    '<bi>': Token(TokenType.FORMAT, 'bolditalic', start=True),
    '</bi>': Token(TokenType.FORMAT, 'bolditalic', start=False),
    '<t>': Token(TokenType.FORMAT, 'bolditalic', start=True),
    '[[': Token(TokenType.FORMAT, 'bolditalic', start=True),
    '</t>': Token(TokenType.FORMAT, 'bolditalic', start=False),
    ']]': Token(TokenType.FORMAT, 'bolditalic', start=False),
    '<icon>': Token(TokenType.FORMAT, 'icon', start=True),
    '</icon>': Token(TokenType.FORMAT, 'icon', start=False),
    '<center>': Token(TokenType.ALIGN, Align.CENTER, start=True),
    '</center>': Token(TokenType.ALIGN, Align.CENTER, start=False),
    '<left>': Token(TokenType.ALIGN, Align.LEFT, start=True),
    '</left>': Token(TokenType.ALIGN, Align.LEFT, start=False),
    '<right>': Token(TokenType.ALIGN, Align.RIGHT, start=True),
    '</right>': Token(TokenType.ALIGN, Align.RIGHT, start=False),
    '<blockquote>': Token(TokenType.STORY, 'quote', start=True),
    '</blockquote>': Token(TokenType.STORY, 'quote', start=False),
    '<u>': Token(TokenType.UNDERLINE, start=True),
    '</u>': Token(TokenType.UNDERLINE, start=False),
    '<dbl>': Token(TokenType.DBL_UNDERLINE, start=True),
    '</dbl>': Token(TokenType.DBL_UNDERLINE, start=False),
    '<br>': Token(TokenType.BREAK),
    '<hr>': Token(TokenType.HR),
    '</indent>': Token(TokenType.INDENT_POP),
}

REPLACEMENT_TAGS = {
    '<quote>': '‘',
    '<dquote>': '“',
    '<quoteend>': '’',
    '<dquoteend>': '”',
    '---': '—',
    '--': '–',
}

# Replacement tags whose expansion is translatable: tag -> (translation key, english default)
_TRANSLATED_REPLACEMENTS = {
    '<for>': ('<for>', '<b>Forced –</b>'),
    '<prey>': ('<prey>', '<b>Prey –</b>'),
    '<rev>': ('<rev>', '<b>Revelation –</b>'),
    '<spawn>': ('<spawn>', '<b>Spawn –</b>'),
    '<obj>': ('<obj>', '<b>Objective –</b>'),
    '<objective>': ('<objective>', '<b>Objective –</b>'),
}

FONT_ICON_TAGS = {
    '<codex>': '#',
    '<star>': '*',
    '<dash>': '-',
    '<sign_1>': '1',
    '<sign_2>': '2',
    '<sign_3>': '3',
    '<sign_4>': '4',
    '<sign_5>': '5',
    '<wild>': '?',
    '<tablet>': 'A',
    '<entry>': 'B',
    '<cultist>': 'C',
    '<blessing>': 'D',
    '<blood>': 'W',
    '<elder_sign>': 'E',
    '<fleur>': 'F',
    '<guardian>': 'G',
    '<frost>': 'H',
    '<seeker>': 'K',
    '<elder_thing>': 'L',
    '<mystic>': 'M',
    '<rogue>': 'R',
    '<skull>': 'S',
    '<auto_fail>': 'T',
    '<curse>': 'U',
    '<survivor>': 'V',
    '<agility>': 'a',
    '<agi>': 'a',
    '[agility]': 'a',
    '<bullet>': 'b',
    '<com>': 'c',
    '<combat>': 'c',
    '[combat]': 'c',
    '<horror>': 'd',
    '<resolution>': 'e',
    '<free>': 'f',
    '[fast]': 'f',
    '<damage>': 'h',
    '<intellect>': 'i',
    '[intellect]': 'i',
    '<int>': 'i',
    '<resource>': 'm',
    '<act>': 'n',
    '<action>': 'n',
    '[action]': 'n',
    '<open>': 'o',
    '<per>': 'p',
    '<per_large>': 'q',
    '<investigator>': 'q',
    '[per_investigator]': 'p',
    '<reaction>': 'r',
    '<unique>': 'u',
    '<willpower>': 'w',
    '<wil>': 'w',
    '[willpower]': 'w',
    '<day>': '<',
    '<night>': '>',
}

# Base font faces: name -> font file. ResourceCache seeds its mutable `fonts`
# map from this and adds `<font "...">` fonts resolved at parse time.
FONT_FILES = {
    'regular': {'path': font_dir / "Arno Pro" / "arnopro_regular.otf"},
    'caption': {'path': font_dir / "Arno Pro" / "arnopro_caption.otf"},
    'bold': {'path': font_dir / "Arno Pro" / "arnopro_bold.otf"},
    'semibold': {'path': font_dir / "Arno Pro" / "arnopro_semibold.ttf"},
    'display': {'path': font_dir / "Arno Pro" / "arnopro_display.otf"},
    'displaybold': {'path': font_dir / "Arno Pro" / "arnopro_bolddisplay.otf"},
    'italic': {'path': font_dir / "Arno Pro" / "arnopro_italic.otf"},
    'bolditalic': {'path': font_dir / "Arno Pro" / "arnopro_bolditalic.otf"},
    'icon': {'path': font_dir / "AHLCGSymbol.otf"},
    'cost': {'path': font_dir / "Arkhamic.ttf"},
    'title': {'path': font_dir / "Arkhamic.ttf"},
    'skill': {'path': font_dir / "Bolton.ttf"},
}

# Parametric tags (the rare ones that carry arguments).
SIZE_RE = re.compile(r'<size (\d+)>', flags=re.IGNORECASE)
MARGIN_RE = re.compile(r'<margin (\d+)(\s\d+)*>', flags=re.IGNORECASE)  # only the first number is used
INDENT_RE = re.compile(r'<indent (\d+)>', flags=re.IGNORECASE)
FONT_RE = re.compile(r'<font "(.+?)">', flags=re.IGNORECASE)
IMAGE_RE = re.compile(r'<image(\s\w+=\".+?\"){1,}?>', flags=re.IGNORECASE)
SPACING_RE = re.compile(r'<spacing ([\d.]+)>', flags=re.IGNORECASE)
_ATTRIBUTE_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def parse_tag_attributes(tag_string):
    """`<image src="x" color="y">` -> {'src': 'x', 'color': 'y'}."""
    return dict(_ATTRIBUTE_RE.findall(tag_string))


class _TrieNode:
    __slots__ = ('children', 'value')

    def __init__(self):
        self.children = {}
        self.value = None


def build_trie(tag_dict):
    """Build a case-insensitive prefix trie from {tag_string: payload}."""
    root = _TrieNode()
    for tag, payload in tag_dict.items():
        node = root
        for character in tag.lower():
            node = node.children.setdefault(character, _TrieNode())
        node.value = payload
    return root


def trie_match(root, text, position):
    """Longest tag matching at text[position]. Returns (payload, length) or (None, 0)."""
    node = root
    best_payload, best_length = None, 0
    index = position
    while index < len(text):
        character = text[index].lower()
        if character not in node.children:
            break
        node = node.children[character]
        index += 1
        if node.value is not None:
            best_payload, best_length = node.value, index - position
    return best_payload, best_length


_TOKEN_HELP = {
    TokenType.BREAK: 'line break',
    TokenType.HR: 'horizontal rule',
    TokenType.INDENT_POP: 'end indent',
    TokenType.UNDERLINE: 'underline',
    TokenType.DBL_UNDERLINE: 'double underline heading',
}


class TagTable:
    """The tag vocabulary resolved for one card language: the translated
    replacement map plus the tries and replacement order the parser consumes."""

    def __init__(self, translations):
        self.translations = translations or {}

        self.replacement_tags = dict(REPLACEMENT_TAGS)
        for tag, (key, fallback) in _TRANSLATED_REPLACEMENTS.items():
            self.replacement_tags[tag] = self.translations.get(key, fallback)

        self.formatting_trie = build_trie(FORMATTING_TAGS)
        self.icon_trie = build_trie(FONT_ICON_TAGS)
        # Longest tag first so `str.replace` does '---' before '--'.
        self.replacement_order = sorted(
            self.replacement_tags.items(), key=lambda item: -len(item[0]))

    def get_help_text(self, font_names):
        lines = [tr("HELP_SPECIAL_TAGS_INTRO"), "", tr("HELP_FORMATTING_TAGS")]
        for tag, token in FORMATTING_TAGS.items():
            if token.type in (TokenType.FORMAT, TokenType.ALIGN, TokenType.STORY):
                description = token.value.value if isinstance(token.value, Align) else token.value
            else:
                description = _TOKEN_HELP.get(token.type, token.type.name.lower())
            lines.append(f'  {tag}  ({description})')
        lines += ["", tr("HELP_REPLACEMENT_TAGS")]
        lines += [f"  {tag} = {result}" for tag, result in self.replacement_tags.items()]
        lines += ["", tr("HELP_ICON_TAGS")]
        lines += [f"  {tag}" for tag in FONT_ICON_TAGS]
        lines += ["", tr("HELP_AVAILABLE_FONTS")]
        lines += [f"  {name}" for name in font_names]
        return "\n".join(lines) + "\n"
