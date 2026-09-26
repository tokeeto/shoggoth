""" Layout
    Where we fit the tokens onto the allotted space.
    We build lines (since lines have formatting attributed to them),
    but might have to rebuild them if we need to change the font size.

    The idea here is that we can go back and forth and edit previous or
    next elements as needed without having to re-parse the tokens.

    TODO:
    Make lines act as linked-lists, grabbing text from the next line,
    or pushing text to the next line as needed.
"""

import math
from typing import NamedTuple

from shoggoth.renderer.richtext.constants import (
    DBL_UNDERLINE_Y_FACTOR, LINE_HEIGHT_FACTOR, QUOTE_BAR_SPACING, QUOTE_INDENT,
    STRIKETHROUGH_Y_FACTOR, UNDERLINE_Y_FACTOR,
)
from shoggoth.renderer.richtext.model import (
    Align, ImageCommand, LineCommand, Piece, PieceType, Style, TextCommand,
)

# Upper bound on extra layout passes spent vertically centering polygon text.
_MAX_VALIGN_PASSES = 12


class _Item(NamedTuple):
    """A placed thing on a line. `TEXT` covers icon-font glyphs too."""

    kind: PieceType                 # TEXT, IMAGE or HR
    width: float
    style: Style
    text: str = ''
    font: object = None
    icon: object = None
    letter_spaced: bool = False     # drawn glyph-by-glyph, never run-merged
    face: str = ''                  # font face name, to reload `font` at another size
    src: object = None              # IMAGE: icon source + tint, to re-fetch at
    color: object = None            #   another size (`font` = the sizing font)


class _Box(NamedTuple):
    """A region scaled to the target resolution (float coordinates)."""

    x: float
    y: float
    width: float
    height: float


class LayoutEngine:
    """Owns the whole text-fitting job: shrink to fit, lay out lines, return
    draw commands."""

    def __init__(self, resources):
        self.resources = resources

    def run(self, pieces, region, polygon, font_size, *, min_font_size,
            fill='#231f20', outline=0, outline_fill=None, scale=1.0,
            letter_spacing=1.0, valignment='top'):
        """`region`/`polygon`/`font_size`/`min_font_size`/`outline` must be
        nominal (pre-scale) values.

        Two passes: the fit and line breaking happen once at the nominal
        (full) size, which fixes which items sit on which line and each line's
        baseline. Then every line is re-measured with fonts and icons loaded
        at the target `scale` and flowed horizontally at that resolution. So
        baselines land exactly at their full-size Y (times `scale`), while X
        follows the target-size glyph advances, keeping spacing and kerning
        within a line consistent instead of mixing full-size positions with
        target-size glyphs."""
        if valignment == 'center':
            pieces = [Piece(PieceType.VALIGN)] + list(pieces)
        lines, size, fitted = self._fit(pieces, region, polygon, font_size,
                                        min_font_size, letter_spacing)
        if fitted.valign_line is not None:
            lines = self._center(pieces, region, polygon, size, letter_spacing,
                                 lines, fitted)
        if scale and scale != 1.0:
            lines = _scale_lines(lines, scale, self.resources, letter_spacing)
            region = _Box(region.x * scale, region.y * scale,
                          region.width * scale, region.height * scale)
            if polygon:
                polygon = [(x * scale, y * scale) for x, y in polygon]
            size = max(1, round(size * scale))
            if outline:
                outline = max(0, round(outline * scale))
        else:
            scale = 1.0
        context = _RenderContext(size, scale, fill, outline, outline_fill, region, polygon)
        commands = []
        for line in lines:
            commands.extend(line.render(context))
        return commands

    def _fit(self, pieces, region, polygon, font_size, min_font_size, letter_spacing):
        """Search for a fitting size and build its lines, always at the
        nominal (scale-1) size the caller passed in. Returns
        (list[_Line], final_size_px, the _LayoutPass that built them)."""
        size = round(font_size)
        while True:
            forced = size <= min_font_size
            layout_pass = _LayoutPass(self.resources, pieces, region, polygon, size,
                                      1.0, letter_spacing, forced)
            lines, fits, fraction = layout_pass.build()
            if fits or forced:
                break
            # Step down faster the earlier the overflow started.
            size -= 1
            if 0 < fraction < 0.8:
                size -= 1
            if 0 < fraction < 0.5:
                size -= 1
            if 0 < fraction < 0.3:
                size -= 1

        return lines, size, layout_pass

    def _center(self, pieces, region, polygon, size, letter_spacing, lines, fitted):
        """Vertically center the lines from `<valign>`'s line on, within the
        band between that line's top and the region's bottom, keeping the
        fitted size. Balances the ink box (cap height of the block's first
        line to descender of its last), so top and bottom gaps look equal.

        Without a polygon, line breaks don't depend on Y, so the block is just
        shifted. With one, moving text down changes the band widths and so
        the line count, so the offset is searched for: a fixed-point step
        (move by half the remaining imbalance) inside a bisection bracket.
        `lo` is the largest offset known to fit without sitting below center,
        `hi` the smallest known not to. The step usually lands in one or two
        passes; the bracket guarantees termination when there's no exact
        fixed point (e.g. one line more fits exactly when shifted down), and
        in that case the text stays at `lo`, a bit above center rather than
        overflowing or sinking low."""
        start, top = fitted.valign_line, fitted.valign_top
        limit = region.y + region.height
        balance = _imbalance(lines, start, top, limit)
        if balance is None or balance < 2:
            return lines
        if not polygon:
            for line in lines[start:]:
                line.y += math.floor(balance / 2)
            return lines

        best, lo, hi = lines, 0, None
        tried = {0}
        guess = math.floor(balance / 2)
        tolerance = max(1, size // 10)   # a bracket this narrow isn't worth a pass
        for _ in range(_MAX_VALIGN_PASSES):
            if hi is not None and hi - lo <= tolerance:
                break
            if hi is not None and not lo < guess < hi:
                guess = (lo + hi) // 2
            if guess <= lo or guess in tried:
                break
            tried.add(guess)
            candidate, fits, _ = _LayoutPass(
                self.resources, pieces, region, polygon, size, 1.0, letter_spacing,
                False, valign_line=start, valign_offset=guess).build()
            balance = _imbalance(candidate, start, top, limit) if fits else None
            if balance is not None and balance >= 0:
                best, lo = candidate, guess
            else:
                hi = guess
            guess = guess + math.floor(balance / 2) if balance is not None else hi
        return best


def _imbalance(lines, start, top, limit):
    """Bottom gap minus top gap of the ink of `lines[start:]` within the band
    `top`..`limit`; positive means the block sits above center. None if the
    block draws nothing."""
    block = [line for line in lines[start:] if line.is_rule or line.items]
    if not block:
        return None
    above, _ = _ink_extent(block[0])
    _, below = _ink_extent(block[-1])
    return (limit - (block[-1].y + below)) - ((block[0].y - above) - top)


def _ink_extent(line):
    """(height above, depth below) the baseline that `line` inks: cap height
    and descender of its text fonts (so the result doesn't depend on which
    letters happen to be there), the actual glyphs of icon-font items, and
    inline images as placed by `_Line.render`."""
    if line.is_rule:
        return 0, 0
    above = below = 0
    for item in line.items:
        if item.kind is PieceType.TEXT and item.text.strip():
            if item.face == 'icon':
                _, glyph_top, _, glyph_bottom = item.font.getbbox(item.text, anchor='ls')
            else:
                glyph_top = item.font.getbbox('H', anchor='ls')[1]
                glyph_bottom = item.font.getbbox('p', anchor='ls')[3]
            above, below = max(above, -glyph_top), max(below, glyph_bottom)
        elif item.kind is PieceType.IMAGE and item.icon is not None:
            above = max(above, item.icon.height * .85)
            below = max(below, item.icon.height * .15)
    return above, below


def _scale_lines(lines, scale, resources, letter_spacing):
    """Copy full-size `lines` to the target resolution: same items per line,
    baselines and vertical metrics multiplied by `scale`, but every item
    re-measured with its font (or icon) loaded at the scaled size. Horizontal
    placement is then redone by `_Line.render` from those widths."""
    def font_at(face, size_px):
        return resources.load_fonts(max(1, round(size_px * scale)))[face]

    def scale_item(item):
        if item.kind is PieceType.TEXT:
            font = font_at(item.face, item.font.size)
            width = resources.width_cache.width(item.text, font)
            if item.letter_spaced:
                width *= letter_spacing
            return item._replace(font=font, width=width)
        if item.kind is PieceType.IMAGE:
            if item.icon is None:
                return item
            regular = font_at('regular', item.font.size)
            icon = resources.get_icon(item.src, int(regular.size), color=item.color)
            return item._replace(font=regular, icon=icon, width=icon.width if icon else 0)
        return item._replace(width=item.width * scale)  # inline HR spans the band

    scaled = []
    for line in lines:
        new = _Line()
        new.is_rule = line.is_rule
        new.y = line.y * scale
        new.block_indent = line.block_indent * scale
        new.align = line.align
        new.size_px = line.size_px * scale
        new.line_height = line.line_height * scale
        new.quote = line.quote
        new.quote_first = line.quote_first
        new.has_dbl = line.has_dbl
        new.hang = line.hang
        if line.quote:
            new.text_indent = QUOTE_INDENT * scale
        elif line.hang:
            new.text_indent = resources.width_cache.width('b ', font_at('icon', line.size_px))
        new.items = [scale_item(item) for item in line.items]
        scaled.append(new)
    return scaled


class _Line:
    """A frozen line and everything render() needs to draw it. `is_rule` marks a
    standalone `<hr>` line (no items)."""

    __slots__ = ('is_rule', 'items', 'y', 'block_indent', 'text_indent', 'align',
                 'size_px', 'line_height', 'quote', 'quote_first', 'has_dbl',
                 'line_width', 'hang')

    def __init__(self):
        self.is_rule = False
        self.items = []
        self.y = 0.0
        self.block_indent = 0        # <indent N>, raw px, feeds the polygon carry
        self.text_indent = 0         # resolved quote indent OR bullet hang
        self.align = Align.LEFT
        self.size_px = 0
        self.line_height = 0
        self.quote = False           # inside <blockquote>
        self.quote_first = False     # first line of a run of quote lines
        self.has_dbl = False
        self.line_width = 0.0        # scratch, used only while building
        self.hang = False            # continuation line of a bullet paragraph

    def pop_unspaced_tail(self):
        """If this line has any items after its last plain space, remove that
        trailing run (the space itself included, same as a line-leading space)
        and return it so the caller can seed the next line with it -- this is
        what keeps e.g. an icon and the word glued to it (no space, possibly a
        non-breaking space) from ever being wrapped apart. Returns None if
        there is no space to roll back to, or nothing follows it."""
        for index in range(len(self.items) - 1, -1, -1):
            item = self.items[index]
            if item.kind is PieceType.TEXT and item.text == ' ':
                tail = self.items[index + 1:]
                if not tail:
                    return None
                self.line_width -= sum(popped.width for popped in self.items[index:])
                self.items = self.items[:index]
                return tail
        return None

    def render(self, context):
        if self.is_rule:
            left, width = context.content_bounds(self.y, self.block_indent, self.size_px)
            return [LineCommand(int(left), self.y, int(left + width), self.y,
                                context.fill, max(1, context.base_size // 18))]

        items = self.items
        if not items:
            return []

        commands = []
        base = context.base_size

        if self.quote:
            bar_top = self.y - (self.size_px * 0.8 if self.quote_first else self.line_height)
            for bar_x in (context.left, context.left + int(context.scale * QUOTE_BAR_SPACING)):
                commands.append(LineCommand(bar_x, bar_top, bar_x, self.y,
                                            context.fill, max(1, round(context.scale * 2))))

        left, width = context.content_bounds(self.y, self.block_indent, self.size_px)
        left += self.text_indent
        width -= self.text_indent

        if items[0].kind is PieceType.TEXT and items[0].text == ' ':
            items = items[1:]
        line_width = sum(item.width for item in items)
        if self.align is Align.CENTER:
            x = left + (width - line_width) / 2
        elif self.align is Align.RIGHT:
            x = left + width - line_width
        else:
            x = left
        x_start = x

        run = _Run(x)
        for item in items:
            if item.kind is PieceType.TEXT:
                if item.letter_spaced:
                    x += run.flush(commands, self.y, base, context)
                    run.reset(x)
                    commands.append(_text_command(item.text, item.font, x, self.y, context))
                    _add_decorations(commands, item.style.strike, item.style.underline,
                                     x, item.width, self.y, base, context)
                    x += item.width
                elif run.matches(item):
                    run.add(item)
                    x += item.width
                else:
                    x += run.flush(commands, self.y, base, context)
                    run.reset(x)
                    run.begin(item)
                    x += item.width
            elif item.kind is PieceType.IMAGE:
                x += run.flush(commands, self.y, base, context)
                run.reset(x)
                if item.icon is not None:
                    commands.append(ImageCommand(int(x), int(self.y - item.icon.height * .85),
                                                 item.icon))
                x += item.width
            else:  # inline HR
                x += run.flush(commands, self.y, base, context)
                run.reset(x)
                rule_y = int(self.y + base * 0.5)
                commands.append(LineCommand(int(left), rule_y, int(left + width), rule_y,
                                            context.fill, max(1, base // 18)))
                x += item.width
        x += run.flush(commands, self.y, base, context)

        if self.has_dbl:
            thickness = max(1, base // 18)
            first_y = int(self.y + base * DBL_UNDERLINE_Y_FACTOR)
            second_y = first_y + thickness + max(2, base // 10)
            for underline_y in (first_y, second_y):
                commands.append(LineCommand(int(x_start), underline_y,
                                            int(x_start + line_width), underline_y,
                                            context.fill, thickness))
        return commands


class _RenderContext:
    """Shared render config plus the one cross-line value: `carried_indent`, the
    polygon x-indent that persists down an indented block."""

    __slots__ = ('base_size', 'scale', 'fill', 'outline', 'outline_fill',
                 'left', 'region', 'polygon', 'carried_indent')

    def __init__(self, base_size, scale, fill, outline, outline_fill, region, polygon):
        self.base_size = base_size
        self.scale = scale
        self.fill = fill
        self.outline = outline
        self.outline_fill = outline_fill
        self.left = region.x
        self.region = region
        self.polygon = polygon
        self.carried_indent = 0

    def content_bounds(self, y, block_indent, size_px):
        """(left_x, width) of the drawable band at baseline `y`."""
        if not self.polygon:
            return self.left + block_indent, self.region.width - block_indent
        poly_left, poly_right = _polygon_span(self.polygon, y, size_px,
                                              self.left, self.region.width)
        if block_indent:
            if not self.carried_indent:
                self.carried_indent = poly_left + block_indent
            content_left = max(self.carried_indent, poly_left)
        else:
            self.carried_indent = 0
            content_left = poly_left
        return content_left, poly_right - content_left


def _polygon_span_at(polygon, y):
    """(min_x, max_x) where a horizontal line at `y` crosses the polygon, or None."""
    crossings = []
    for index in range(len(polygon) - 1):
        (x1, y1), (x2, y2) = polygon[index], polygon[index + 1]
        if y1 == y2:
            continue
        low, high = (y1, y2) if y1 < y2 else (y2, y1)
        # Half-open on the top edge so a sample on the seam between two stacked
        # bands crosses only one band's edges, not both.
        if y < low or y >= high:
            continue
        along = (y - y1) / (y2 - y1)
        crossings.append(x1 + along * (x2 - x1))
    if not crossings:
        return None
    return min(crossings), max(crossings)


def _polygon_span(polygon, y, size_px, fallback_left, fallback_width):
    """(left, right) of the polygon band, sampled at the baseline and at the top
    of the glyphs, taking whichever pair is more restrictive."""
    if not polygon:
        return fallback_left, fallback_left + fallback_width
    top = _polygon_span_at(polygon, y - size_px)
    base = _polygon_span_at(polygon, y)
    if top is None:
        return base if base is not None else (fallback_left, fallback_left + fallback_width)
    if base is None:
        return top
    return max(top[0], base[0]), min(top[1], base[1])


class _Run:
    """Accumulates consecutive same-font, same-decoration text items so a line
    of ~20 items becomes 2-3 shaped draw calls."""

    __slots__ = ('chars', 'width', 'font', 'x', 'strike', 'underline')

    def __init__(self, x):
        self.reset(x)

    def reset(self, x):
        self.chars = []
        self.width = 0.0
        self.font = None
        self.x = x
        self.strike = False
        self.underline = False

    def begin(self, item):
        self.font = item.font
        self.strike = item.style.strike
        self.underline = item.style.underline
        self.chars = [item.text]
        self.width = item.width

    def add(self, item):
        self.chars.append(item.text)
        self.width += item.width

    def matches(self, item):
        return (item.font is self.font
                and item.style.strike == self.strike
                and item.style.underline == self.underline)

    def flush(self, commands, line_y, base_size, context):
        """Emit the run and return the x correction (true kerned advance minus
        the summed per-item widths) for the caller to apply."""
        if not self.chars:
            return 0.0
        text = ''.join(self.chars)
        true_advance = self.font.getlength(text)
        commands.append(_text_command(text, self.font, self.x, line_y, context))
        _add_decorations(commands, self.strike, self.underline,
                         self.x, self.width, line_y, base_size, context)
        return true_advance - self.width


def _text_command(text, font, x, y, context):
    return TextCommand(x, y, text, font, context.fill, context.outline, context.outline_fill)


def _add_decorations(commands, strike, underline, x, width, y, base_size, context):
    if strike:
        strike_y = int(y + base_size * STRIKETHROUGH_Y_FACTOR)
        commands.append(LineCommand(int(x), strike_y, int(x + width), strike_y,
                                    context.fill, max(1, base_size // 16)))
    if underline:
        underline_y = int(y + base_size * UNDERLINE_Y_FACTOR)
        commands.append(LineCommand(int(x), underline_y, int(x + width), underline_y,
                                    context.fill, max(1, base_size // 18)))


class _LayoutPass:
    """One fitting pass at one font size. `build()` returns
    (list[_Line], fits, fraction); on a non-forced overflow it stops early and
    returns (None, False, fraction)."""

    def __init__(self, resources, pieces, region, polygon, base_size, scale,
                 letter_spacing, forced, valign_line=None, valign_offset=0):
        self.resources = resources
        self.pieces = pieces
        self.region = region
        self.polygon = polygon
        self.base_size = base_size
        self.scale = scale
        self.letter_spacing = letter_spacing
        self.forced = forced

        self.left = region.x
        self.y = region.y + base_size
        self.y_limit = region.y + region.height
        self.lines = []
        self._fraction = 1.0

        self._line = None
        self._first_of_paragraph = True
        self._bullet_paragraph = False

        # <valign>: `valign_line` is the index of the line the first marker
        # landed on and `valign_top` that line's top, before any offset.
        # `valign_offset` (from LayoutEngine._center) moves that line and
        # everything after it down.
        self.valign_line = None
        self.valign_top = None
        self._offset_line = valign_line
        self._offset = valign_offset
        self._applied_offset = 0

    # ── measurement ─────────────────────────────────────────────────────
    def _size_px(self, style):
        if style.size is None:
            return self.base_size
        return int(round(style.size * self.scale))

    def _font(self, face, size_px):
        return self.resources.load_fonts(size_px)[face]

    def _width(self, text, font):
        return self.resources.width_cache.width(text, font)

    def _spaced_width(self, text, font):
        if self.letter_spacing == 1.0 or not text:
            return self._width(text, font)
        return sum(self._width(character, font) for character in text) * self.letter_spacing

    def _text_items(self, text, font, style):
        if self.letter_spacing == 1.0 or not text:
            return [_Item(PieceType.TEXT, self._width(text, font), style, text=text, font=font,
                          face=style.font)]
        return [_Item(PieceType.TEXT, self._width(character, font) * self.letter_spacing,
                      style, text=character, font=font, letter_spaced=True, face=style.font)
                for character in text]

    def _wrap_width(self, y, block_indent, text_indent, size_px):
        if not self.polygon:
            return self.region.width - block_indent - text_indent
        poly_left, poly_right = _polygon_span(self.polygon, y, size_px,
                                              self.left, self.region.width)
        return poly_right - max(self.left + block_indent, poly_left) - text_indent

    def _text_indent(self, style, size_px):
        """A quote's fixed indent (wins) or a bullet's hanging indent (only once
        the paragraph has wrapped past its first physical line)."""
        if style.quote:
            return int(QUOTE_INDENT * self.scale)
        if self._bullet_paragraph and not self._first_of_paragraph:
            return self._width('b ', self._font('icon', size_px))
        return 0

    # ── line lifecycle ─────────────────────────────────────────────────
    def _open_line(self):
        if self._offset and len(self.lines) == self._offset_line:
            self.y += self._offset
            self._applied_offset = self._offset
        self._line = _Line()
        self._line.hang = self._bullet_paragraph and not self._first_of_paragraph

    def _close_line(self, closing_style):
        line = self._line
        items = line.items
        style = closing_style or (items[-1].style if items else Style())
        size_px = self._size_px(style)
        line.y = self.y
        line.block_indent = style.indent
        line.align = style.align
        line.size_px = size_px
        line.line_height = int(size_px * LINE_HEIGHT_FACTOR)
        line.quote = style.quote or any(item.style.quote for item in items)
        line.has_dbl = any(item.style.dbl_underline for item in items)
        if line.quote:
            line.text_indent = int(QUOTE_INDENT * self.scale)
        elif line.hang:
            line.text_indent = self._width('b ', self._font('icon', size_px))
        else:
            line.text_indent = 0
        self.lines.append(line)

    def _wrap_line(self, style):
        """Close the current line because the next piece doesn't fit, and open
        a fresh one to keep placing into. If the current line ends in a run
        with no space in it (an icon glued to its neighbours, say), that run
        is rolled back onto the new line first, so the wrap lands at the last
        real space instead of splitting the glued run apart."""
        tail = self._line.pop_unspaced_tail()
        self._close_line(style)
        self.y += self._size_px(style)
        self._first_of_paragraph = False
        self._open_line()
        if tail:
            self._line.items = tail
            self._line.line_width = sum(item.width for item in tail)

    def _overflowed(self, piece_index):
        """A non-forced overflow: record how far we got, tell the caller to stop."""
        if self.forced:
            return False
        self._fraction = piece_index / max(1, len(self.pieces))
        return True

    # ── the walk ───────────────────────────────────────────────────────
    def build(self):
        self._open_line()
        check_overflow = False

        for piece_index, piece in enumerate(self.pieces):
            kind = piece.type

            if kind is PieceType.LETTER_SPACING:
                continue

            if kind is PieceType.VALIGN:
                if self.valign_line is None:
                    self.valign_line = len(self.lines)
                    self.valign_top = self.y - self._applied_offset - self.base_size
                continue

            if kind is PieceType.VSPACE:
                self.y += int(piece.px * self.scale)
                continue

            if kind in (PieceType.PAR, PieceType.BREAK):
                style = piece.style
                size_px = self._size_px(style)
                if kind is PieceType.PAR and style.indent == 0:
                    advance = int(size_px * LINE_HEIGHT_FACTOR)
                else:
                    advance = size_px
                self._close_line(style)
                self.y += advance
                self._first_of_paragraph = kind is PieceType.PAR
                if kind is PieceType.PAR:
                    self._bullet_paragraph = False
                self._open_line()
                check_overflow = True
                continue

            if kind is PieceType.HR_BREAK:
                style = piece.style
                size_px = self._size_px(style)
                line_height = int(size_px * LINE_HEIGHT_FACTOR)
                if check_overflow:
                    check_overflow = False
                    if self.y > self.y_limit and self._overflowed(piece_index):
                        return None, False, self._fraction
                self._close_line(style)
                self.y += line_height / 2
                rule = _Line()
                rule.is_rule = True
                rule.y = int(self.y)
                rule.block_indent = style.indent
                rule.size_px = size_px
                self.lines.append(rule)
                self.y += line_height
                self._first_of_paragraph = True
                self._bullet_paragraph = False
                self._open_line()
                check_overflow = True
                continue

            if check_overflow:
                check_overflow = False
                if self.y > self.y_limit and self._overflowed(piece_index):
                    return None, False, self._fraction

            style = piece.style
            size_px = self._size_px(style)

            if kind in (PieceType.TEXT, PieceType.SPACE):
                text = piece.text if kind is PieceType.TEXT else ' '
                if self._place_text(piece_index, text, style, size_px):
                    return None, False, self._fraction
                continue

            if kind is PieceType.ICON:
                font = self._font('icon', size_px)
                item = _Item(PieceType.TEXT, self._width(piece.glyph, font), style,
                             text=piece.glyph, font=font, face='icon')
                if piece.glyph == 'b' and not self._line.items:
                    self._bullet_paragraph = True
            elif kind is PieceType.IMAGE:
                regular = self._font('regular', size_px)
                icon = self.resources.get_icon(piece.src, int(regular.size), color=piece.color)
                item = _Item(PieceType.IMAGE, icon.width if icon else 0, style, icon=icon,
                             font=regular, src=piece.src, color=piece.color)
            else:  # inline HR
                text_indent = self._text_indent(style, size_px)
                width = self._wrap_width(self.y, style.indent, text_indent, size_px)
                item = _Item(PieceType.HR, width, style)

            text_indent = self._text_indent(style, size_px)
            if self._line.line_width + item.width > self._wrap_width(
                    self.y, style.indent, text_indent, size_px):
                self._wrap_line(style)
                if self.y > self.y_limit and self._overflowed(piece_index):
                    return None, False, self._fraction

            self._line.items.append(item)
            self._line.line_width += item.width

        self._close_line(None)
        if self.lines and not self.lines[-1].is_rule and not self.lines[-1].items:
            self.lines.pop()
        if self.y > self.y_limit and self._overflowed(len(self.pieces)):
            return None, False, self._fraction
        self._mark_quote_runs()
        return self.lines, True, 1.0

    def _mark_quote_runs(self):
        """First line of every run of consecutive quote lines gets the short top
        bar; a non-quote or rule line ends a run."""
        previous_quote = False
        for line in self.lines:
            in_quote = not line.is_rule and line.quote
            line.quote_first = in_quote and not previous_quote
            previous_quote = in_quote

    def _place_text(self, piece_index, text, style, size_px):
        """Fit one word (or space), wrapping / hyphenating as needed. Returns
        True if a non-forced overflow means build() should bail out."""
        font = self._font(style.font, size_px)
        while True:
            width = self._spaced_width(text, font)
            text_indent = self._text_indent(style, size_px)
            available = self._wrap_width(self.y, style.indent, text_indent, size_px)
            if self._line.line_width + width <= available:
                break

            next_line_fits = (self.y + size_px) <= self.y_limit
            split = (self.resources.hyphenate_split(text, font, available - self._line.line_width)
                     if next_line_fits else None)
            if split is None and self._line.line_width == 0:
                if self._overflowed(piece_index):
                    return True
                break
            if split is not None:
                # The hyphen point already decides where this word breaks;
                # `head` stays on the closing line as-is, no rollback.
                head, text = split
                self._line.items.extend(self._text_items(head, font, style))
                self._close_line(style)
                self.y += size_px
                self._first_of_paragraph = False
                self._open_line()
            else:
                self._wrap_line(style)
            if self.y > self.y_limit and self._overflowed(piece_index):
                return True

        self._line.items.extend(self._text_items(text, font, style))
        self._line.line_width += width
        return False
