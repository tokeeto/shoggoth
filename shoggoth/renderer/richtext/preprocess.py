"""Pure transforms applied around tokenization: two string passes before the
tokenizer (bullet shorthand, smart quotes) and three token passes after it
(French spacing, ink-free line collapsing, `<hr>` merging).
Each takes a value and returns a new one.
"""

import re

from shoggoth.renderer.richtext.constants import FRENCH_SPACED_PUNCT
from shoggoth.renderer.richtext.model import Token, TokenType

# Token types that put ink on a line. A line with none of these (only control
# tags) applies its effects but takes no vertical space.
RENDERABLE_TOKEN_TYPES = frozenset({
    TokenType.TEXT, TokenType.FONT_ICON, TokenType.IMAGE_ICON,
    TokenType.HR, TokenType.BREAK,
})

# Control tokens allowed to sit between a newline and an `<hr>` without breaking
# the "rule on its own line" recognition in merge_hr_breaks.
CONTROL_TOKEN_TYPES = frozenset({
    TokenType.FORMAT, TokenType.ALIGN, TokenType.STORY,
    TokenType.INDENT_PUSH, TokenType.INDENT_POP,
    TokenType.SIZE, TokenType.SIZE_POP,
    TokenType.FONT_PUSH, TokenType.FONT_POP,
    TokenType.COLOR_PUSH, TokenType.COLOR_POP,
    TokenType.UNDERLINE, TokenType.DBL_UNDERLINE, TokenType.STRIKE,
    TokenType.MARGIN, TokenType.LETTER_SPACING, TokenType.VALIGN,
})

_SPACE = Token(TokenType.TEXT, ' ')
_NEWLINE = Token(TokenType.NEWLINE)

_BULLET_LINE = re.compile(r'^- (.*)(\n(?=- ))?', re.MULTILINE)


def expand_bullet_shorthand(text):
    """Turn "- item" lines into `<bullet> item`, with only a line break (not a
    paragraph gap) between consecutive items."""
    return _BULLET_LINE.sub(
        lambda match: f'<bullet> {match[1]}' + ('<br>' if match[2] else ''), text)


def apply_smart_quotes(text):
    """Curl straight quotes, leaving tag interiors and `\\"` escapes alone."""
    text = text.replace('\\"', '\x00DQ\x00').replace("\\'", '\x00SQ\x00')

    result = []
    in_tag = False
    previous_outside = None  # last char seen outside a tag (tags are transparent)
    for character in text:
        if character == '<':
            in_tag = True
            result.append(character)
        elif character == '>':
            in_tag = False
            result.append(character)
        elif in_tag:
            result.append(character)
        elif character == '"':
            opening = previous_outside is None or previous_outside in (' ', '\t', '\n')
            result.append('“' if opening else '”')
            previous_outside = character
        elif character == "'":
            opening = previous_outside is None or previous_outside in (' ', '\t', '\n')
            result.append('‘' if opening else '’')
            previous_outside = character
        else:
            result.append(character)
            previous_outside = character

    return ''.join(result).replace('\x00DQ\x00', '"').replace('\x00SQ\x00', "'")


def _is_word(token):
    return token.type is TokenType.TEXT and token.value != ' '


def merge_french_spacing(tokens):
    """Glue `word <space> <punct>` into one token so the space can't wrap."""
    result = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if (index + 2 < len(tokens) and _is_word(token)
                and tokens[index + 1] == _SPACE
                and tokens[index + 2].type is TokenType.TEXT
                and tokens[index + 2].value in FRENCH_SPACED_PUNCT):
            result.append(Token(TokenType.TEXT, token.value + ' ' + tokens[index + 2].value))
            index += 3
        else:
            result.append(token)
            index += 1
    return result


def collapse_control_lines(tokens):
    """Drop the vertical space of source lines that carry only control tags.

    Done by removing one of the two newlines bounding each such (non-empty)
    line, so runs of them and ones at the start/end collapse cleanly. A truly
    empty line (an explicit blank line) is left alone.
    """
    segments = [[]]
    for token in tokens:
        if token.type is TokenType.NEWLINE:
            segments.append([])
        else:
            segments[-1].append(token)

    def ink_free(segment):
        return segment and not any(t.type in RENDERABLE_TOKEN_TYPES for t in segment)

    result = []
    last = len(segments) - 1
    for index, segment in enumerate(segments):
        result.extend(segment)
        if index == last:
            break
        drop = ink_free(segment) or (index + 1 == last and ink_free(segments[index + 1]))
        if not drop:
            result.append(_NEWLINE)
    return result


def merge_hr_breaks(tokens):
    """Collapse `newline <hr> newline` into one `HR_BREAK` token so a divider
    takes one paragraph's vertical space, not two newlines' worth plus the rule.

    Control tokens (`CONTROL_TOKEN_TYPES`) between the newlines and the rule are
    re-emitted around the `HR_BREAK`: indent changes before it (so the rule is
    drawn at the post-change indent), everything else after (so the line above
    still flushes under the state it was typed with).
    """
    result = []
    index = 0
    while index < len(tokens):
        if tokens[index].type is TokenType.NEWLINE:
            lead_end = index + 1
            while lead_end < len(tokens) and tokens[lead_end].type in CONTROL_TOKEN_TYPES:
                lead_end += 1
            if lead_end < len(tokens) and tokens[lead_end].type is TokenType.HR:
                trail_end = lead_end + 1
                while trail_end < len(tokens) and tokens[trail_end].type in CONTROL_TOKEN_TYPES:
                    trail_end += 1
                if trail_end < len(tokens) and tokens[trail_end].type is TokenType.NEWLINE:
                    lead = tokens[index + 1:lead_end]
                    indent_changes = [t for t in lead if t.type in
                                      (TokenType.INDENT_PUSH, TokenType.INDENT_POP)]
                    other = [t for t in lead if t.type not in
                             (TokenType.INDENT_PUSH, TokenType.INDENT_POP)]
                    result.extend(indent_changes)
                    result.append(Token(TokenType.HR_BREAK))
                    result.extend(other)
                    result.extend(tokens[lead_end + 1:trail_end])
                    index = trail_end + 1
                    continue
        result.append(tokens[index])
        index += 1
    return result
