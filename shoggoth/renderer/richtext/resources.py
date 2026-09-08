"""Asset loading and result memoization for the rich-text renderer: font faces,
inline icons, per-run glyph masks, per-character widths, hyphenation
dictionaries. One `ResourceCache` is shared by the layout engine and rasterizer.
"""

import io
import os
import pathlib
import platform
import re
from collections import OrderedDict

import pyphen
from PIL import Image, ImageColor, ImageFont, ImageOps

from shoggoth.perf import perf
from shoggoth.renderer.richtext.constants import GLYPH_RUN_CACHE_MAXSIZE
from shoggoth.renderer.richtext.tags import FONT_FILES


def colorize_icon(icon, color):
    """Tint a grayscale icon: black -> `color`, white stays white, greys blend,
    alpha preserved. `color` is any Pillow color (word, hex, `rgb(...)`)."""
    rgb = ImageColor.getcolor(color, 'RGB')
    icon = icon.convert('RGBA')
    colored = ImageOps.colorize(icon.convert('L'), black=rgb, white=(255, 255, 255))
    colored.putalpha(icon.getchannel('A'))
    return colored


def invert_icon(icon):
    alpha = icon.getchannel('A')
    icon = ImageOps.invert(icon.convert('RGB'))
    icon.putalpha(alpha)
    return icon


class GlyphRunCache:
    """Rasterized (mask, offset) for a whole shaped text run, keyed on
    (font, text, stroke width, sub-pixel bucket).

    Keying on the whole run means a hit reuses HarfBuzz's fully kerned output;
    summing cached per-character advances instead would drift from real kerning
    (measured ~4px on a short Arno Pro run). The draw position's fractional part
    is quantized to quarter-pixel buckets so near-identical offsets still hit;
    that only shifts antialiasing, never glyph spacing.
    """

    __slots__ = ('_cache',)

    def __init__(self):
        self._cache = OrderedDict()

    def get(self, font, text, mode, stroke_width, start):
        quantized_start = (round(start[0] * 4) / 4, round(start[1] * 4) / 4)
        key = (id(font), text, mode, stroke_width, quantized_start)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        mask, offset = font.getmask2(
            text, mode, stroke_width=stroke_width, anchor='ls', start=quantized_start,
        )
        result = (Image.new(mask.mode, (0, 0))._new(mask), offset)
        self._cache[key] = result
        if len(self._cache) > GLYPH_RUN_CACHE_MAXSIZE:
            self._cache.popitem(last=False)
        return result

    def clear(self):
        self._cache.clear()


class WidthCache:
    """String widths by summing cached per-character widths. Ignores kerning
    (negligible for body text, and one Pillow call per unique char instead of
    per token)."""

    __slots__ = ('_by_font',)

    def __init__(self):
        self._by_font = {}          # id(font) -> {character: width}

    def width(self, text, font):
        widths = self._by_font.setdefault(id(font), {})
        total = 0.0
        missing = []
        for character in text:
            cached = widths.get(character)
            if cached is None:
                missing.append(character)
            else:
                total += cached
        for character in set(missing):
            widths[character] = font.getlength(character)
        for character in missing:
            total += widths[character]
        return total

    def clear(self):
        self._by_font.clear()


class ResourceCache:
    """Fonts, icons, glyph/width caches and hyphenation dictionaries, shared
    across every render of one RichTextRenderer."""

    def __init__(self, card_renderer, hyphenation_enabled=True):
        self.card_renderer = card_renderer
        self.hyphenation_enabled = hyphenation_enabled

        # face name -> {'path': ...}; seeded from the static set, extended by
        # resolve_font() with '__user__<name>' entries for <font "..."> tags.
        self.fonts = dict(FONT_FILES)

        self.font_cache = {}          # size -> {face name: ImageFont}
        self._user_font_keys = {}     # <font> name -> face name (or None if unresolved)
        self.font_meta = {}           # ImageFont -> {family, path, size, ascent, descent}
        self.icon_cache = {}
        self.width_cache = WidthCache()
        self.glyph_run_cache = GlyphRunCache()
        self._hyphenators = {}        # locale -> pyphen.Pyphen or None

    def load_fonts(self, size):
        if size in self.font_cache:
            return self.font_cache[size]
        with perf.span('load_fonts (disk read + truetype init, all faces)'):
            loaded = {}
            for face_name, face_info in self.fonts.items():
                # BytesIO so FreeType keeps no open handle: on Windows an open
                # FT_Face blocks the asset updater from replacing the font file.
                font_bytes = io.BytesIO(pathlib.Path(face_info['path']).read_bytes())
                font = ImageFont.truetype(font_bytes, size)
                ascent, descent = font.getmetrics()
                self.font_meta[font] = {
                    'family': 'shoggoth-' + re.sub(r'[^A-Za-z0-9_-]+', '-', face_name),
                    'path': str(face_info['path']),
                    'size': size,
                    'ascent': ascent,
                    'descent': descent,
                }
                loaded[face_name] = font
            self.font_cache[size] = loaded
        return loaded

    def resolve_font(self, name, project=None):
        """Resolve a `<font "name">` to a face name in self.fonts.

        Returns (face_name, missing). On failure returns ('regular', True) and
        the caller strikes the text through as a "missing font" marker. Results
        (including failures) are cached.
        """
        if name in self.fonts:
            return name, False
        if name in self._user_font_keys:
            cached = self._user_font_keys[name]
            return ('regular', True) if cached is None else (cached, False)

        face_name = f'__user__{name}'
        path = (project.find_file(name) if project else None) or pathlib.Path(name)
        if path.exists() and path.suffix.lower() in ('.ttf', '.otf'):
            return self._register_user_font(name, face_name, path)

        with perf.span('Scan system fonts for custom <font> tag (fallback)'):
            system_path = self._find_system_font(name)
        if system_path:
            return self._register_user_font(name, face_name, system_path)

        self._user_font_keys[name] = None
        return 'regular', True

    def _register_user_font(self, name, face_name, path):
        self.fonts[face_name] = {'path': path, 'scale': 1, 'fallback': None}
        self.font_cache.clear()
        self._user_font_keys[name] = face_name
        return face_name, False

    def _find_system_font(self, name):
        name_lower = name.lower()
        if platform.system() in ('Linux', 'Darwin'):
            try:
                import subprocess
                result = subprocess.run(
                    ['fc-match', '--format=%{file}', name],
                    capture_output=True, text=True, timeout=2,
                )
                if result.returncode == 0 and result.stdout.strip():
                    path = pathlib.Path(result.stdout.strip())
                    if path.exists() and path.stem.lower() == name_lower:
                        return path
            except Exception:
                pass

        home = pathlib.Path.home()
        system = platform.system()
        if system == 'Windows':
            search_dirs = [
                pathlib.Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts',
                pathlib.Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'Windows' / 'Fonts',
            ]
        elif system == 'Darwin':
            search_dirs = [
                pathlib.Path('/System/Library/Fonts'),
                pathlib.Path('/Library/Fonts'),
                home / 'Library' / 'Fonts',
            ]
        else:
            search_dirs = [
                pathlib.Path('/usr/share/fonts'),
                pathlib.Path('/usr/local/share/fonts'),
                home / '.local' / 'share' / 'fonts',
                home / '.fonts',
            ]
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for extension in ('*.ttf', '*.otf', '*.TTF', '*.OTF'):
                for font_file in search_dir.rglob(extension):
                    if font_file.stem.lower() == name_lower:
                        return font_file
        return None

    def load_icon(self, icon_path, height):
        if str(icon_path).endswith('.svg'):
            return self.card_renderer.get_resized_cached(icon_path, (height, height))
        if (icon_path, height) in self.icon_cache:
            return self.icon_cache[(icon_path, height)]
        icon = self.card_renderer.get_cached(icon_path).convert("RGBA")
        width = int(height * icon.width / icon.height)
        icon = icon.resize((width, height))
        self.icon_cache[(icon_path, height)] = icon
        return icon

    def get_icon(self, icon_path, font_size, color=None):
        """Inline icon image at `font_size` height. `color` is "inverted" or any
        Pillow color, which tints the grayscale icon."""
        key = (icon_path, font_size, color)
        if key in self.icon_cache:
            return self.icon_cache[key]
        icon = self.load_icon(icon_path, font_size)
        if color == "inverted":
            icon = invert_icon(icon)
        elif color:
            try:
                icon = colorize_icon(icon, color)
            except ValueError:
                print(f"Unknown inline icon color: {color!r}")
        self.icon_cache[key] = icon
        return icon

    def _hyphenator(self):
        """Cached pyphen.Pyphen for the card's language, or None if it has no
        dictionary (e.g. CJK)."""
        locale = getattr(self.card_renderer, 'locale', None) or 'en'
        if locale not in self._hyphenators:
            dictionary = None
            try:
                resolved = pyphen.language_fallback(locale)
                if resolved:
                    dictionary = pyphen.Pyphen(lang=resolved)
            except Exception:
                dictionary = None
            self._hyphenators[locale] = dictionary
        return self._hyphenators[locale]

    def hyphenate_split(self, word, font, max_width):
        """Split `word` with a trailing hyphen so the head fits `max_width` px.
        Returns (head, tail) for the longest fitting split, or None."""
        if max_width <= 0 or not self.hyphenation_enabled:
            return None
        hyphenator = self._hyphenator()
        if hyphenator is None:
            return None

        # Hyphenate only the alphabetic core; leave surrounding punctuation on
        # whichever half it borders.
        start, end = 0, len(word)
        while start < end and not word[start].isalpha():
            start += 1
        while end > start and not word[end - 1].isalpha():
            end -= 1
        core = word[start:end]
        if not core.isalpha():
            return None

        prefix, suffix = word[:start], word[end:]
        for head, tail in hyphenator.iterate(core):
            candidate = prefix + head + '-'
            if self.width_cache.width(candidate, font) <= max_width:
                return candidate, tail + suffix
        return None

    def clear(self):
        """Drop every in-memory cache so updated assets are picked up next render."""
        self.font_cache.clear()
        self.font_meta.clear()
        self.width_cache.clear()
        self.glyph_run_cache.clear()
        self.icon_cache.clear()
