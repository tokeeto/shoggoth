"""Vector-text back end: record the layout as absolutely-positioned HTML in the
card's pixel space, so a PDF pipeline can overlay it and keep text sharp at any
resolution. `CaptureState` is the per-thread on/off switch; `HtmlTextCapture`
accumulates the markup; `emit_html` converts one card's commands into it.
"""

import html as html_lib
import pathlib
import threading
from contextlib import contextmanager

from shoggoth.renderer.richtext.model import LineCommand, TextCommand


class HtmlTextCapture:
    """Accumulates text runs, glyphs and rules as absolutely-positioned HTML;
    inline images stay on the raster layer."""

    _css_lock = threading.Lock()

    def __init__(self):
        self.parts = []
        self.fonts = {}          # css font-family -> font file path
        # Post-layout crop (trim + bleed) that shifted the raster image but not
        # these already-recorded coordinates; undone in fragment(). See translate().
        self.offset_x = 0
        self.offset_y = 0

    def translate(self, dx, dy):
        """Record a crop of (dx, dy) from the top-left: the point that was at
        (dx, dy) is now the origin. Call once per crop, in the pre-rotation
        coordinate space the spans were recorded in."""
        self.offset_x += dx
        self.offset_y += dy

    def fragment(self, width, height, rotation=None):
        """The overlay fragment for one card side. `width`/`height` are the final
        exported image size; `rotation` ('cw'/'ccw') must match a 90-degree
        rotation applied to the card image after layout."""
        spans = '\n'.join(self.parts)
        if self.offset_x or self.offset_y:
            spans = (f'<div style="position:absolute;left:0;top:0;'
                     f'transform:translate({-self.offset_x}px,{-self.offset_y}px);">\n{spans}\n</div>')
        if rotation in ('cw', 'ccw'):
            # Pre-rotation canvas was height x width; map it on the way PIL's
            # rotate(expand=True) did.
            if rotation == 'cw':
                transform = f'translate({width}px,0) rotate(90deg)'
            else:
                transform = f'translate(0,{height}px) rotate(-90deg)'
            spans = (f'<div style="position:absolute;left:0;top:0;'
                     f'width:{height}px;height:{width}px;'
                     f'transform:{transform};transform-origin:0 0;">\n{spans}\n</div>')
        return (f'<div class="shoggoth-text-layer" data-width="{width}" data-height="{height}" '
                f'style="position:absolute;left:0;top:0;width:{width}px;height:{height}px;'
                f'overflow:hidden;">\n{spans}\n</div>\n')

    def font_css(self):
        """@font-face rules for every font family this capture used."""
        return ''.join(self._font_face_rule(family, path)
                       for family, path in sorted(self.fonts.items()))

    @staticmethod
    def _font_face_rule(family, path):
        source = pathlib.Path(path).absolute().as_uri()
        return f'@font-face {{ font-family: "{family}"; src: url("{source}"); }}\n'

    def merge_font_css_into(self, folder):
        """Append this capture's @font-face rules to folder/fonts.css, skipping
        families already declared. Thread-safe for parallel card exports."""
        css_path = pathlib.Path(folder) / 'fonts.css'
        with self._css_lock:
            existing = css_path.read_text(encoding='utf-8') if css_path.exists() else ''
            new_rules = [self._font_face_rule(family, path)
                         for family, path in sorted(self.fonts.items())
                         if f'font-family: "{family}"' not in existing]
            if new_rules:
                with open(css_path, 'a', encoding='utf-8') as css_file:
                    css_file.writelines(new_rules)


class CaptureState:
    """Per-thread HTML-capture switch, so parallel card exports sharing one
    RichTextRenderer keep separate text layers."""

    def __init__(self):
        self._thread_local = threading.local()

    @property
    def current(self):
        return getattr(self._thread_local, 'capture', None)

    @property
    def active(self):
        return self.current is not None

    def start(self):
        self._thread_local.capture = HtmlTextCapture()

    def finish(self):
        capture = self.current
        self._thread_local.capture = None
        return capture

    def shift(self, dx, dy):
        if self.current is not None:
            self.current.translate(dx, dy)

    @contextmanager
    def paused(self):
        """Rasterize text normally within this block (e.g. for rotated fields)."""
        capture = self.current
        self._thread_local.capture = None
        try:
            yield
        finally:
            self._thread_local.capture = capture


def emit_html(capture, commands, font_meta):
    """Append absolutely-positioned HTML for `commands` to `capture.parts`.

    Text is baseline-anchored; CSS positions by the top edge, so top = baseline
    minus ascent, with line-height pinned to ascent+descent to cancel CSS
    half-leading. Image commands stay on the raster layer.
    """
    for command in commands:
        if isinstance(command, TextCommand):
            span = _text_span(command, font_meta, capture)
            if span:
                capture.parts.append(span)
        elif isinstance(command, LineCommand):
            capture.parts.append(_line_box(command))


def _text_span(command, font_meta, capture):
    meta = font_meta.get(command.font)
    if meta is None:
        return ''
    family = meta['family']
    # Record the face so its @font-face rule lands in fonts.css; without this
    # the PDF overlay falls back to a system font.
    capture.fonts[family] = meta['path']

    descent = max(0, meta['descent'])
    if family == 'shoggoth-skill':          # Bolton reports too small a descent
        descent = meta['size'] * .2
    style = (
        f'position:absolute;white-space:pre;'
        f'left:{command.x:.2f}px;top:{command.y - meta["ascent"]:.2f}px;'
        f"font-family:'{family}';font-size:{meta['size']}px;"
        f'line-height:{meta["ascent"] + descent}px;'
        f'color:{command.fill or "#231f20"};'
    )
    if command.outline:
        # Approximate the raster stroke with 8-direction shadows.
        width = command.outline
        outline_fill = command.outline_fill or '#000000'
        shadows = ','.join(f'{dx}px {dy}px 0 {outline_fill}'
                           for dx in (-width, 0, width) for dy in (-width, 0, width)
                           if dx or dy)
        style += f'text-shadow:{shadows};'
    return f'<span style="{style}">{html_lib.escape(command.text)}</span>'


def _line_box(command):
    # Axis-aligned; PIL centers the stroke on the segment.
    width = command.width
    if command.y1 == command.y2:
        left, top = min(command.x1, command.x2), command.y1 - width / 2
        box_width, box_height = abs(command.x2 - command.x1), width
    else:
        left, top = command.x1 - width / 2, min(command.y1, command.y2)
        box_width, box_height = width, abs(command.y2 - command.y1)
    return (f'<div style="position:absolute;left:{left:.2f}px;top:{top:.2f}px;'
            f'width:{box_width:.2f}px;height:{box_height:.2f}px;'
            f'background:{command.fill or "#231f20"};"></div>')
