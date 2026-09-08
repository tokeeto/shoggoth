"""Data model shared across the rich-text pipeline.

Flow: `parser._tokenize` emits `Token`s, `parser._resolve_to_pieces` turns them
into `Piece`s carrying a resolved `Style`, `LayoutEngine` turns pieces into
`TextCommand` / `LineCommand` / `ImageCommand`, and `raster` / `html_capture`
consume those.
"""

from enum import Enum, auto
from typing import NamedTuple, Optional


class TokenType(Enum):
    """Kind of a tokenizer token. FORMAT..INDENT_POP are style-only: the parser
    folds them into piece styles and the layout engine never sees them."""

    NEWLINE = auto()
    TEXT = auto()
    FONT_ICON = auto()
    IMAGE_ICON = auto()
    HR = auto()
    HR_BREAK = auto()
    BREAK = auto()
    MARGIN = auto()
    LETTER_SPACING = auto()
    FORMAT = auto()          # <b> <i> <bi> <icon>
    ALIGN = auto()           # <center> <left> <right>
    STORY = auto()           # <blockquote>
    UNDERLINE = auto()       # <u>
    DBL_UNDERLINE = auto()   # <dbl>
    FONT_PUSH = auto()       # <font "name">
    FONT_POP = auto()
    SIZE = auto()            # <size N>
    SIZE_POP = auto()
    INDENT_PUSH = auto()     # <indent N>
    INDENT_POP = auto()      # </indent>


class PieceType(Enum):
    """Kind of a layout piece. TEXT..HR occupy horizontal space; the rest break
    or space out the vertical flow."""

    TEXT = auto()
    SPACE = auto()
    ICON = auto()            # AHLCGSymbol glyph
    IMAGE = auto()           # inline image file
    HR = auto()              # inline rule
    BREAK = auto()           # <br>
    PAR = auto()             # paragraph break (newline)
    HR_BREAK = auto()        # a rule alone on its line
    VSPACE = auto()          # <margin N>
    LETTER_SPACING = auto()  # <spacing N>, stripped before layout


class Align(Enum):
    LEFT = 'left'
    CENTER = 'center'
    RIGHT = 'right'


class Token(NamedTuple):
    type: TokenType
    value: object = None          # text / font face / Align / size int / spacing float
    start: Optional[bool] = None  # paired tags: True on open, False on close
    font: Optional[str] = None    # FONT_PUSH: resolved font-cache key
    strike: bool = False          # FONT_PUSH: font could not be resolved
    color: Optional[str] = None   # IMAGE_ICON tint


class Style(NamedTuple):
    """The fully resolved formatting context of one piece."""

    font: str = 'regular'
    size: Optional[int] = None    # None = shrinkable base size; int = fixed <size N>
    underline: bool = False
    dbl_underline: bool = False
    strike: bool = False          # missing-font marker
    align: Align = Align.LEFT
    indent: int = 0               # <indent N>, px
    quote: bool = False           # inside <blockquote>
    hang: bool = False            # paragraph opened with a leading bullet glyph


class Piece(NamedTuple):
    type: PieceType
    style: Style = Style()
    text: str = ''                # TEXT
    glyph: str = ''               # ICON
    src: str = ''                 # IMAGE
    color: Optional[str] = None   # IMAGE
    px: int = 0                   # VSPACE
    spacing: float = 1.0          # LETTER_SPACING


class TextCommand(NamedTuple):
    x: float
    y: float
    text: str
    font: object
    fill: str
    outline: int = 0
    outline_fill: Optional[str] = None


class LineCommand(NamedTuple):
    x1: float
    y1: float
    x2: float
    y2: float
    fill: str
    width: int


class ImageCommand(NamedTuple):
    x: int
    y: int
    icon: object
