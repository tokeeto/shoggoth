"""Card rendering package.

Public names are re-exported here so the rest of the app keeps importing
`from shoggoth.renderer import CardRenderer, ...` unchanged after the split of
the old flat `renderer.py` / `rich_text.py` modules into this package.
"""

from shoggoth.renderer.card_renderer import (
    CardRenderer,
    CARD_SIZES,
    trim_dimensions,
    DEFAULT_TEXT_FIELDS,
    discovered_text_fields,
    _pdf_page_dims,
    _render_pdf_page,
    Region,
    _ImgDims,
    scale,
)

__all__ = [
    'CardRenderer',
    'CARD_SIZES',
    'trim_dimensions',
    'DEFAULT_TEXT_FIELDS',
    'discovered_text_fields',
    '_pdf_page_dims',
    '_render_pdf_page',
    'Region',
    '_ImgDims',
    'scale',
]
