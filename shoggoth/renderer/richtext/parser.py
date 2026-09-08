"""Markup string -> layout pieces.

`_tokenize` scans the string into `Token`s (running the string/token pre- and
post-passes in `preprocess`). `_resolve_to_pieces` then folds every style-only
token (`<b>`, `<font>`, `<indent>`, `<center>`, `<size>`, `<u>`, `<dbl>`,
`<blockquote>`, ...) into the `Style` of the pieces it covers and drops it, so
the layout engine only sees space-occupying pieces (`TEXT`, `SPACE`, `ICON`,
`IMAGE`, `HR`) and flow breaks (`BREAK`, `PAR`, `HR_BREAK`, `VSPACE`).
"""

from shoggoth.renderer.richtext import preprocess
from shoggoth.renderer.richtext.model import (
    Align, Piece, PieceType, Style, Token, TokenType,
)
from shoggoth.renderer.richtext.tags import (
    FONT_RE, IMAGE_RE, INDENT_RE, MARGIN_RE, SIZE_RE, SPACING_RE,
    parse_tag_attributes, trie_match,
)

_TAG_STARTS = ('<', '[', ']')
_RUN_STOPS = frozenset('<[] \n')


def parse_pieces(text, tags, resources, *, base_font='regular',
                 alignment=Align.LEFT, project=None, french_punctuation=False):
    tokens = _tokenize(text, tags, resources, project=project,
                       french_punctuation=french_punctuation)
    return _resolve_to_pieces(tokens, base_font, alignment)


def _tokenize(text, tags, resources, *, project, french_punctuation):
    text = preprocess.expand_bullet_shorthand(text)
    text = preprocess.apply_smart_quotes(text)
    for tag, replacement in tags.replacement_order:
        text = text.replace(tag, replacement)

    formatting_trie = tags.formatting_trie
    icon_trie = tags.icon_trie
    tokens = []
    position = 0
    length = len(text)

    while position < length:
        character = text[position]

        if character == '\n':
            tokens.append(Token(TokenType.NEWLINE))
            position += 1
            continue

        if character == ' ':
            tokens.append(Token(TokenType.TEXT, ' '))
            position += 1
            continue

        if character in _TAG_STARTS:
            payload, matched_length = trie_match(formatting_trie, text, position)
            if payload is not None:
                tokens.append(payload)
                position += matched_length
                if (payload.type is TokenType.INDENT_POP
                        and position < length and text[position] == '\n'):
                    position += 1   # </indent> eats its trailing newline
                continue

            glyph, matched_length = trie_match(icon_trie, text, position)
            if glyph is not None:
                tokens.append(Token(TokenType.FONT_ICON, glyph))
                position += matched_length
                continue

            if character == '<':
                consumed = _match_parametric(text[position:], tokens, resources, project)
                if consumed:
                    position += consumed
                    if (tokens and tokens[-1].type is TokenType.INDENT_PUSH
                            and position < length and text[position] == '\n'):
                        position += 1   # <indent N> eats its trailing newline
                    continue

        start = position
        position += 1
        while position < length and text[position] not in _RUN_STOPS:
            position += 1
        tokens.append(Token(TokenType.TEXT, text[start:position]))

    if french_punctuation:
        tokens = preprocess.merge_french_spacing(tokens)
    tokens = preprocess.prevent_runts(tokens)
    tokens = preprocess.collapse_control_lines(tokens)
    tokens = preprocess.merge_hr_breaks(tokens)
    return tokens


def _match_parametric(remaining, tokens, resources, project):
    """Try the argument-carrying `<...>` tags at the start of `remaining`.
    Appends a token and returns the consumed character count, or 0 for no match."""
    match = SIZE_RE.match(remaining)
    if match:
        tokens.append(Token(TokenType.SIZE, int(match[1])))
        return len(match[0])

    match = INDENT_RE.match(remaining)
    if match:
        tokens.append(Token(TokenType.INDENT_PUSH, int(match[1])))
        return len(match[0])

    match = MARGIN_RE.match(remaining)
    if match:
        tokens.append(Token(TokenType.MARGIN, int(match[1])))
        return len(match[0])

    match = SPACING_RE.match(remaining)
    if match:
        tokens.append(Token(TokenType.LETTER_SPACING, float(match[1])))
        return len(match[0])

    match = FONT_RE.match(remaining)
    if match:
        font_key, missing = resources.resolve_font(match[1], project=project)
        tokens.append(Token(TokenType.FONT_PUSH, font=font_key, strike=missing))
        return len(match[0])

    if remaining.startswith('</font>'):
        tokens.append(Token(TokenType.FONT_POP))
        return len('</font>')

    if remaining.startswith('</size>'):
        tokens.append(Token(TokenType.SIZE_POP))
        return len('</size>')

    match = IMAGE_RE.match(remaining)
    if match:
        attributes = parse_tag_attributes(match[0])
        source = attributes.get('src')
        if source is not None:
            resolved = project.find_file(source) if project else None
            tokens.append(Token(TokenType.IMAGE_ICON,
                                value=str(resolved) if resolved else source,
                                color=attributes.get('color')))
        return len(match[0])

    return 0


def _resolve_to_pieces(tokens, base_font, base_align):
    # Scoped style state. <b>/<i>/... push `font` alone; <font "..."> pushes
    # `font` and `strike` together.
    state = {'font': base_font, 'strike': False, 'underline': False,
             'align': base_align, 'indent': 0, 'size': None}
    stacks = {key: [] for key in state}

    def push(key, value):
        stacks[key].append(state[key])
        state[key] = value

    def pop(key, default):
        state[key] = stacks[key].pop() if stacks[key] else default

    def set_scope(key, value, start, default):
        push(key, value) if start else pop(key, default)

    quote = False
    dbl_armed = False          # </dbl> seen; twin underline goes under this line
    hang = False               # paragraph opened with a leading bullet glyph
    line_has_content = False
    line_start = 0             # index in `pieces` of this line's first entry

    pieces = []

    def current_style():
        return Style(state['font'], state['size'], state['underline'], dbl_armed,
                     state['strike'], state['align'], state['indent'], quote, hang)

    def add(piece_type, **fields):
        nonlocal line_has_content
        pieces.append(Piece(piece_type, current_style(), **fields))
        line_has_content = True

    def line_break(piece_type):
        nonlocal line_has_content, hang, dbl_armed, line_start
        pieces.append(Piece(piece_type, current_style()))
        line_has_content = False
        dbl_armed = False
        line_start = len(pieces)
        if piece_type is not PieceType.BREAK:   # <br> keeps the bullet hang
            hang = False

    for token in tokens:
        kind = token.type

        if kind is TokenType.NEWLINE:
            line_break(PieceType.PAR)
        elif kind is TokenType.HR_BREAK:
            line_break(PieceType.HR_BREAK)
        elif kind is TokenType.BREAK:
            line_break(PieceType.BREAK)
        elif kind is TokenType.TEXT:
            add(PieceType.SPACE) if token.value == ' ' else add(PieceType.TEXT, text=token.value)
        elif kind is TokenType.FONT_ICON:
            at_line_start = not line_has_content
            add(PieceType.ICON, glyph=token.value)
            if token.value == 'b' and at_line_start:
                hang = True
                pieces[-1] = pieces[-1]._replace(style=pieces[-1].style._replace(hang=True))
        elif kind is TokenType.IMAGE_ICON:
            add(PieceType.IMAGE, src=token.value, color=token.color)
        elif kind is TokenType.HR:
            add(PieceType.HR)
        elif kind is TokenType.MARGIN:
            pieces.append(Piece(PieceType.VSPACE, px=token.value))
        elif kind is TokenType.LETTER_SPACING:
            pieces.append(Piece(PieceType.LETTER_SPACING, spacing=token.value))
        elif kind is TokenType.FORMAT:
            set_scope('font', token.value, token.start, base_font)
        elif kind is TokenType.ALIGN:
            set_scope('align', token.value, token.start, base_align)
        elif kind is TokenType.STORY:
            push('font', 'italic') if token.start else pop('font', base_font)
            quote = token.start
        elif kind is TokenType.UNDERLINE:
            set_scope('underline', True, token.start, False)
        elif kind is TokenType.DBL_UNDERLINE:
            # </dbl> arms a twin underline for its line: retro-mark every piece
            # already on the line, and keep it armed for any that still follow.
            if not token.start:
                dbl_armed = True
                for index in range(line_start, len(pieces)):
                    pieces[index] = pieces[index]._replace(
                        style=pieces[index].style._replace(dbl_underline=True))
        elif kind is TokenType.FONT_PUSH:
            push('font', token.font)
            push('strike', token.strike)
        elif kind is TokenType.FONT_POP:
            pop('font', base_font)
            pop('strike', False)
        elif kind is TokenType.SIZE:
            push('size', token.value)
        elif kind is TokenType.SIZE_POP:
            pop('size', None)
        elif kind is TokenType.INDENT_PUSH:
            push('indent', token.value)
        elif kind is TokenType.INDENT_POP:
            pop('indent', 0)

    return pieces
