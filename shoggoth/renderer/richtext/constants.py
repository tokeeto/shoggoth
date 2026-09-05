"""Typography tuning. Fractions are of the current font size."""

LINE_HEIGHT_FACTOR = 1.30
STRIKETHROUGH_Y_FACTOR = -0.45
UNDERLINE_Y_FACTOR = 0.88
DBL_UNDERLINE_Y_FACTOR = 0.12
QUOTE_INDENT = 50                # text indent inside <blockquote>
QUOTE_BAR_SPACING = 10           # gap between the two blockquote bars

# Punctuation French typography prefixes with a space; that space must not be a
# line-break point, so "word :" stays together.
FRENCH_SPACED_PUNCT = {':', ';', '!', '?'}

# Live editing re-renders per keystroke, so a text-keyed glyph cache would grow
# one entry per edited variant forever. Entries are small masks; cap generously.
GLYPH_RUN_CACHE_MAXSIZE = 4000
