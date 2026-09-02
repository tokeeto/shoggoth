"""Layout: attributed pieces -> draw commands, in three phases.

1. `_LayoutPass.build()` walks the pieces, fitting each onto the current line;
   a finished line is frozen as a `_Line`. It produces a line list and nothing
   else.
2. `LayoutEngine._fit` runs phase 1 at decreasing font sizes until the text
   fits (the search is done in nominal, scale-1 units so the choice does not
   drift with export resolution), then one real-scale pass.
3. `_Line.render` turns one finished line into commands. Called once per line
   at the end; the results are concatenated.
"""

from types import SimpleNamespace
from typing import NamedTuple

from shoggoth.renderer.richtext.constants import (
    DBL_UNDERLINE_Y_FACTOR, LINE_HEIGHT_FACTOR, QUOTE_BAR_SPACING, QUOTE_INDENT,
    STRIKETHROUGH_Y_FACTOR, UNDERLINE_Y_FACTOR,
)
from shoggoth.renderer.richtext.model import (
    Align, ImageCommand, LineCommand, PieceType, Style, TextCommand,
)


class _Item(NamedTuple):
    """A placed thing on a line. `TEXT` covers icon-font glyphs too."""

    kind: PieceType                 # TEXT, IMAGE or HR
    width: float
    style: Style
    text: str = ''
    font: object = None
    icon: object = None
    letter_spaced: bool = False     # drawn glyph-by-glyph, never run-merged


class LayoutEngine:
    """Owns the whole text-fitting job: shrink to fit, lay out lines, return
    draw commands."""

    def __init__(self, resources):
        self.resources = resources

    def run(self, pieces, region, polygon, font_size, *, min_font_size,
            fill='#231f20', outline=0, outline_fill=None, scale=1.0,
            letter_spacing=1.0, valignment='top'):
        lines, size = self._fit(pieces, region, polygon, font_size,
                                min_font_size, scale, letter_spacing)
        context = _RenderContext(size, scale, fill, outline, outline_fill, region, polygon)
        commands = []
        for line in lines:
            commands.extend(line.render(context))
        if valignment == 'center':
            commands = _center_vertically(commands, region, size)
        return commands

    def _fit(self, pieces, region, polygon, font_size, min_font_size, scale,
             letter_spacing):
        """Returns (list[_Line], final_size_px)."""
        rescale = scale and scale != 1.0
        if rescale:
            search_region = SimpleNamespace(
                x=region.x / scale, y=region.y / scale,
                width=region.width / scale, height=region.height / scale)
            search_polygon = [(x / scale, y / scale) for x, y in polygon] if polygon else None
            search_size = font_size / scale
            search_min = min_font_size / scale
            search_scale = 1.0
        else:
            search_region, search_polygon = region, polygon
            search_size, search_min, search_scale = font_size, min_font_size, scale

        size = round(search_size)
        while True:
            forced = size <= search_min
            lines, fits, fraction = _LayoutPass(
                self.resources, pieces, search_region, search_polygon, size,
                search_scale, letter_spacing, forced).build()
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

        if rescale:
            size = max(min_font_size, round(size * scale))
            lines, _, _ = _LayoutPass(
                self.resources, pieces, region, polygon, size, scale,
                letter_spacing, True).build()
        return lines, size


def _center_vertically(commands, region, size):
    baselines = [c.y for c in commands if isinstance(c, (TextCommand, ImageCommand))]
    if not baselines:
        return commands
    text_bottom = max(baselines) + int(size * LINE_HEIGHT_FACTOR)
    offset = (region.height - (text_bottom - region.y)) // 2
    if offset <= 0:
        return commands
    shifted = []
    for command in commands:
        if isinstance(command, LineCommand):
            shifted.append(command._replace(y1=command.y1 + offset, y2=command.y2 + offset))
        else:
            shifted.append(command._replace(y=command.y + offset))
    return shifted


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
                                            context.fill, int(context.scale * 2)))

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
                 letter_spacing, forced):
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
            return [_Item(PieceType.TEXT, self._width(text, font), style, text=text, font=font)]
        return [_Item(PieceType.TEXT, self._width(character, font) * self.letter_spacing,
                      style, text=character, font=font, letter_spaced=True)
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
                             text=piece.glyph, font=font)
                if piece.glyph == 'b' and not self._line.items:
                    self._bullet_paragraph = True
            elif kind is PieceType.IMAGE:
                regular = self._font('regular', size_px)
                icon = self.resources.get_icon(piece.src, int(regular.size), color=piece.color)
                item = _Item(PieceType.IMAGE, icon.width if icon else 0, style, icon=icon)
            else:  # inline HR
                text_indent = self._text_indent(style, size_px)
                width = self._wrap_width(self.y, style.indent, text_indent, size_px)
                item = _Item(PieceType.HR, width, style)

            text_indent = self._text_indent(style, size_px)
            if self._line.line_width + item.width > self._wrap_width(
                    self.y, style.indent, text_indent, size_px):
                self._close_line(style)
                self.y += size_px
                self._first_of_paragraph = False
                self._open_line()
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
                head, text = split
                self._line.items.extend(self._text_items(head, font, style))
            self._close_line(style)
            self.y += size_px
            self._first_of_paragraph = False
            self._open_line()
            if self.y > self.y_limit and self._overflowed(piece_index):
                return True

        self._line.items.extend(self._text_items(text, font, style))
        self._line.line_width += width
        return False
