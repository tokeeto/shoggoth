"""`RichTextRenderer` -- the entry point the card renderer talks to.

A thin orchestrator over four collaborators: `TagTable` (the tag vocabulary),
`ResourceCache` (fonts / icons / caches / hyphenation), `LayoutEngine` (pieces
-> draw commands, with shrink-to-fit) and `CaptureState` (the per-thread HTML
capture switch). `render_text` parses to pieces, lays them out, and rasterizes
(or records HTML).
"""

from shoggoth.perf import perf
from shoggoth.renderer.richtext import parser, raster
from shoggoth.renderer.richtext.html_capture import CaptureState, emit_html
from shoggoth.renderer.richtext.layout import LayoutEngine
from shoggoth.renderer.richtext.model import Align, ImageCommand, PieceType
from shoggoth.renderer.richtext.resources import ResourceCache
from shoggoth.renderer.richtext.tags import TagTable


def _extract_letter_spacing(pieces):
    """Pull `<spacing N>` out of the piece list. It applies to the whole text,
    not from its position on, and the last one wins."""
    spacing = 1.0
    kept = []
    for piece in pieces:
        if piece.type is PieceType.LETTER_SPACING:
            spacing = piece.spacing
        else:
            kept.append(piece)
    return spacing, kept


class RichTextRenderer:
    def __init__(self, card_renderer, hyphenation_enabled=True, french_punctuation=False):
        self.card_renderer = card_renderer
        self.french_punctuation = french_punctuation

        self.tags = TagTable(card_renderer.translations)
        self.resources = ResourceCache(card_renderer, hyphenation_enabled)
        self.layout = LayoutEngine(self.resources)
        self.capture = CaptureState()

    @property
    def hyphenation_enabled(self):
        return self.resources.hyphenation_enabled

    @hyphenation_enabled.setter
    def hyphenation_enabled(self, value):
        self.resources.hyphenation_enabled = value

    def get_help_text(self):
        return self.tags.get_help_text(font_names=self.resources.fonts.keys())

    def clear_caches(self):
        """Drop every in-memory cache so updated assets are picked up next render."""
        self.resources.clear()

    # ── HTML capture (delegates to the per-thread CaptureState) ───────────
    def start_html_capture(self):
        """From now on (this thread), record text as HTML instead of rasterizing."""
        self.capture.start()

    def finish_html_capture(self):
        """Stop capturing; return the HtmlTextCapture (or None if not capturing)."""
        return self.capture.finish()

    def shift_html_capture(self, dx, dy):
        """Record a post-layout crop on this thread's active capture, if any."""
        self.capture.shift(dx, dy)

    @property
    def is_html_capturing(self):
        return self.capture.active

    def html_capture_paused(self):
        """Rasterize text normally within this block (e.g. for rotated fields)."""
        return self.capture.paused()

    def render_text(self, image, text, region, polygon=None, alignment='left',
                    font_size=32, min_font_size=None, font=None, outline=0,
                    outline_fill=None, fill='#231f20', scale=1.0,
                    project=None, valignment='top'):
        if not text:
            return

        font = font or 'regular'
        if min_font_size is None:
            min_font_size = font_size // 2

        with perf.span('parse_pieces'):
            pieces = parser.parse_pieces(
                text, self.tags, self.resources,
                base_font=font, alignment=Align(alignment),
                project=project, french_punctuation=self.french_punctuation,
            )
        letter_spacing, pieces = _extract_letter_spacing(pieces)

        with perf.span('layout (fit + build lines + render)'):
            commands = self.layout.run(
                pieces, region, polygon, font_size, min_font_size=min_font_size,
                fill=fill, outline=outline, outline_fill=outline_fill,
                scale=scale, letter_spacing=letter_spacing, valignment=valignment,
            )

        with perf.span('rasterize (render_commands / emit_html)'):
            capture = self.capture.current
            if capture is None:
                raster.render_commands(image, commands, self.resources.glyph_run_cache)
            else:
                # Vector mode: inline images stay raster; text and rules become HTML.
                raster.render_commands(
                    image, [c for c in commands if isinstance(c, ImageCommand)],
                    self.resources.glyph_run_cache,
                )
                emit_html(capture, commands, self.resources.font_meta)
