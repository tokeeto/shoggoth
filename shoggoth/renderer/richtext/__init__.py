"""Arkham rich-text markup: parsing, line layout, rasterization and the vector
(HTML) text back end.

`RichTextRenderer` is the only name the rest of the app needs. Submodules:
`model` (enums + record types), `tags`, `resources`, `preprocess`, `parser`,
`layout`, `raster`, `html_capture`.
"""

from shoggoth.renderer.richtext.engine import RichTextRenderer
from shoggoth.renderer.richtext.html_capture import HtmlTextCapture

__all__ = ['RichTextRenderer', 'HtmlTextCapture']
