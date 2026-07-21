from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageOps
from collections import OrderedDict
from contextlib import contextmanager
import html as html_lib
import io
import os
import platform
import pathlib
import threading
import re
import pyphen
from shoggoth.files import font_dir
from shoggoth.i18n import tr
from shoggoth.perf import perf

# Bounds _GlyphRunCache: live editing re-renders on every keystroke, so an
# unbounded cache keyed on exact text would grow by roughly one entry per
# edited variant of every field, forever, over a long session. Entries are
# tiny (small grayscale masks), so this cap is generous, not a tight budget.
_GLYPH_RUN_CACHE_MAXSIZE = 4000

# Only keep regexes for the rare parametric tags (size, margin, indent, font, image)
_size_re = re.compile(r'<size (\d+)>', flags=re.IGNORECASE)
# <margin> accepts multiple space-separated numbers but only the first is used
_margin_re = re.compile(r'<margin (\d+)(\s\d+)*>', flags=re.IGNORECASE)
_indent_re = re.compile(r'<indent (\d+)>', flags=re.IGNORECASE)
_font_re = re.compile(r'<font "(.+?)">', flags=re.IGNORECASE)
_image_re = re.compile(r'<image(\s\w+=\".+?\"){1,}?>', flags=re.IGNORECASE)
_tag_kv = re.compile(r'(\w+)\s*=\s*"([^"]*)"')

# Typographic tuning (fractions are of the current font size)
LINE_HEIGHT_FACTOR = 1.30
STRIKETHROUGH_Y_FACTOR = 0.45   # bar offset below the text anchor
UNDERLINE_Y_FACTOR = 0.88
DBL_UNDERLINE_Y_FACTOR = 0.12
QUOTE_INDENT = 50               # text indent inside <blockquote>
QUOTE_BAR_SPACING = 10          # gap between the two blockquote bars


def _parse_tag_attributes(tag_string):
    return dict(_tag_kv.findall(tag_string))


class _TrieNode:
    __slots__ = ('children', 'value', 'tag_len')

    def __init__(self):
        self.children = {}
        self.value = None
        self.tag_len = 0


def _build_trie(tag_dict):
    """Build a trie from {tag_string: payload}.  Returns root node."""
    root = _TrieNode()
    for tag, payload in tag_dict.items():
        node = root
        for ch in tag:
            c = ch.lower()
            if c not in node.children:
                node.children[c] = _TrieNode()
            node = node.children[c]
        node.value = payload
        node.tag_len = len(tag)
    return root


def _trie_match(root, text, pos):
    """Longest-match lookup starting at text[pos]. Returns (payload, length) or (None, 0)."""
    node = root
    best_val = None
    best_len = 0
    i = pos
    end = len(text)
    while i < end:
        c = text[i].lower()
        if c not in node.children:
            break
        node = node.children[c]
        i += 1
        if node.value is not None:
            best_val = node.value
            best_len = i - pos
    return best_val, best_len


def colorize_icon(icon, color):
    """Tint a grayscale (primarily black) icon with a single color.

    Black pixels take the color, white stays white, anti-aliased grays blend
    between the two, and the alpha channel is preserved. `color` is anything
    Pillow understands: a color word, '#rgb'/'#rrggbb' hex, or 'rgb(r,g,b)'.
    """
    rgb = ImageColor.getcolor(color, 'RGB')
    icon = icon.convert('RGBA')
    colored = ImageOps.colorize(icon.convert('L'), black=rgb, white=(255, 255, 255))
    colored.putalpha(icon.getchannel('A'))
    return colored


def invert_icon(icon):
    alpha = icon.getchannel('A')
    icon = icon.convert('RGB')
    icon = ImageOps.invert(icon)
    icon.putalpha(alpha)
    return icon


class _GlyphRunCache:
    """Cache rasterized (mask, offset) results for exact repeated text runs.

    Unlike a per-character cache, this is keyed on the *whole* shaped run
    (font, text, stroke width), so a cache hit reuses raqm/HarfBuzz's fully
    kerned output verbatim -- it cannot drift out of sync with kerning or
    ligatures the way summing per-character advances would. This matters
    here: profiling showed Arno Pro's kerning shifts even a short run like
    "The q" by ~4px versus naive per-character advance summation, so only
    whole-run caching is safe to substitute for ImageDraw.text().

    The only approximation is the sub-pixel hinting phase (the fractional
    part of the draw position, which FreeType uses to nudge hinting): it's
    rounded to the nearest quarter-pixel bucket so identical runs drawn at
    very slightly different sub-pixel offsets still hit the cache. That can
    only shift antialiasing by a fraction of a pixel, never glyph spacing.
    """
    __slots__ = ('_cache',)

    def __init__(self):
        self._cache = OrderedDict()

    def get(self, font, text, mode, stroke_width, start):
        qstart = (round(start[0] * 4) / 4, round(start[1] * 4) / 4)
        key = (id(font), text, mode, stroke_width, qstart)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        mask, offset = font.getmask2(
            text, mode, stroke_width=stroke_width, anchor='ls', start=qstart,
        )
        wrapped = Image.new(mask.mode, (0, 0))._new(mask)
        result = (wrapped, offset)
        self._cache[key] = result
        if len(self._cache) > _GLYPH_RUN_CACHE_MAXSIZE:
            self._cache.popitem(last=False)
        return result

    def clear(self):
        self._cache.clear()


class _WidthCache:
    """Cache per-character widths for a (font_object) and compute string widths
    by summing cached values.  Falls back to getlength for chars not yet seen.
    Accuracy note: this ignores kerning, which is negligible for card body text
    and buys a massive speedup (one Pillow call per *unique char* vs per token).
    """
    __slots__ = ('_cache',)

    def __init__(self):
        self._cache = {}          # id(font_obj) -> {char: width}

    def width(self, text, font):
        fid = id(font)
        charmap = self._cache.get(fid)
        if charmap is None:
            charmap = {}
            self._cache[fid] = charmap

        total = 0.0
        missing = []
        for ch in text:
            w = charmap.get(ch)
            if w is not None:
                total += w
            else:
                missing.append(ch)

        if missing:
            # Batch-measure all missing chars at once
            unique_missing = set(missing)
            for ch in unique_missing:
                w = font.getlength(ch)
                charmap[ch] = w
            # Now sum the ones we missed
            for ch in missing:
                total += charmap[ch]

        return total

    def clear(self):
        self._cache.clear()


class HtmlTextCapture:
    """Collects rich text as absolutely positioned HTML instead of raster output.

    While a capture is active on a RichTextRenderer, render_text() lays text
    out exactly as usual (same wrapping, same font shrinking), but text runs,
    icon-font glyphs, and rules are recorded as HTML elements in the card's
    pixel coordinate space; only inline images are still drawn onto the card.
    A PDF pipeline can overlay the resulting fragment on the exported card
    image so text stays vector and prints at any resolution.
    """

    _css_lock = threading.Lock()

    def __init__(self):
        self.parts = []
        self.fonts = {}    # css font-family -> font file path

    def fragment(self, width, height, rotation=None):
        """Build the overlay fragment for one card side.

        width/height are the final exported image dimensions in pixels.
        rotation ('cw' or 'ccw') must match a 90-degree rotation that was
        applied to the card image after text layout, so the text is laid out
        in pre-rotation coordinates and rotated as a whole via CSS.
        """
        spans = '\n'.join(self.parts)
        if rotation in ('cw', 'ccw'):
            # Pre-rotation canvas was height x width; map it onto the final
            # image the same way PIL's rotate(expand=True) did.
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
        """@font-face rules for every font family used by this capture."""
        return ''.join(self._font_face_rule(family, path)
                       for family, path in sorted(self.fonts.items()))

    @staticmethod
    def _font_face_rule(family, path):
        src = pathlib.Path(path).absolute().as_uri()
        return f'@font-face {{ font-family: "{family}"; src: url("{src}"); }}\n'

    def merge_font_css_into(self, folder):
        """Append this capture's @font-face rules to folder/fonts.css,
        skipping families already declared there. Thread-safe, so parallel
        card exports into the same folder can share the file."""
        css_path = pathlib.Path(folder) / 'fonts.css'
        with self._css_lock:
            existing = css_path.read_text(encoding='utf-8') if css_path.exists() else ''
            new_rules = [self._font_face_rule(family, path)
                         for family, path in sorted(self.fonts.items())
                         if f'font-family: "{family}"' not in existing]
            if new_rules:
                with open(css_path, 'a', encoding='utf-8') as f:
                    f.writelines(new_rules)


class RichTextRenderer:
    def __init__(self, card_renderer, hyphenation_enabled=True):
        self.card_renderer = card_renderer
        self.icon_cache = {}
        self.font_cache = {}
        self.user_font_cache = {}
        self._user_font_keys = {}
        # Per-font metadata (path, metrics) for the HTML text layer,
        # keyed by the font object itself
        self._font_meta = {}
        # HTML capture is thread-local: parallel card exports each get their own
        self._html_tls = threading.local()

        self.hyphenation_enabled = hyphenation_enabled

        # ── Width cache (shared across all renders) ──────────────────────────
        self._wcache = _WidthCache()

        # ── Rasterized glyph-run cache (shared across all renders) ───────────
        self._glyph_run_cache = _GlyphRunCache()

        # ── Hyphenation dictionaries, keyed by card language ──────────────────
        self._hyphen_dicts = {}

        # ── Formatting tags ──────────────────────────────────────────────────
        # Each value is the token dict emitted verbatim by parse_text (shared,
        # treated as immutable).  get_help_text derives its descriptions from
        # these same entries, so a new tag only needs to be added here.
        self.formatting_tags = {
            '<b>': {'type': 'format', 'value': 'bold', 'start': True},
            '</b>': {'type': 'format', 'value': 'bold', 'start': False},
            '<i>': {'type': 'format', 'value': 'italic', 'start': True},
            '</i>': {'type': 'format', 'value': 'italic', 'start': False},
            '<bi>': {'type': 'format', 'value': 'bolditalic', 'start': True},
            '</bi>': {'type': 'format', 'value': 'bolditalic', 'start': False},
            '<t>': {'type': 'format', 'value': 'bolditalic', 'start': True},
            '[[': {'type': 'format', 'value': 'bolditalic', 'start': True},
            '</t>': {'type': 'format', 'value': 'bolditalic', 'start': False},
            ']]': {'type': 'format', 'value': 'bolditalic', 'start': False},
            '<icon>': {'type': 'format', 'value': 'icon', 'start': True},
            '</icon>': {'type': 'format', 'value': 'icon', 'start': False},
            '<center>': {'type': 'align', 'value': 'center', 'start': True},
            '</center>': {'type': 'align', 'value': 'center', 'start': False},
            '<left>': {'type': 'align', 'value': 'left', 'start': True},
            '</left>': {'type': 'align', 'value': 'left', 'start': False},
            '<right>': {'type': 'align', 'value': 'right', 'start': True},
            '</right>': {'type': 'align', 'value': 'right', 'start': False},
            # NOTE: 'indent' tokens have no handler in _layout, so <story>
            # currently parses but has no layout effect.
            '<story>': {'type': 'indent', 'value': 4, 'start': True},
            '</story>': {'type': 'indent', 'value': 4, 'start': False},
            '<blockquote>': {'type': 'story', 'value': 'quote', 'start': True},
            '</blockquote>': {'type': 'story', 'value': 'quote', 'start': False},
            '<u>': {'type': 'underline', 'start': True},
            '</u>': {'type': 'underline', 'start': False},
            '<dbl>': {'type': 'dbl_underline', 'start': True},
            '</dbl>': {'type': 'dbl_underline', 'start': False},
            '<br>': {'type': 'break'},
            '<hr>': {'type': 'hr'},
            '</indent>': {'type': 'indent_pop'},
        }

        self.replacement_tags = {
            '<for>': self.get_translation('<for>', '<b>Forced –</b>'),
            '<prey>': self.get_translation('<prey>', '<b>Prey –</b>'),
            '<rev>': self.get_translation('<rev>', '<b>Revelation –</b>'),
            '<spawn>': self.get_translation('<spawn>', '<b>Spawn –</b>'),
            '<obj>': self.get_translation('<obj>', '<b>Objective –</b>'),
            '<objective>': self.get_translation('<objective>', '<b>Objective –</b>'),
            '<quote>': '\u2018',
            '<dquote>': '\u201c',
            '<quoteend>': '\u2019',
            '<dquoteend>': '\u201d',
            '---': '\u2014',
            '--': '\u2013',
        }

        self.font_icon_tags = {
            '<codex>': '#',
            '<star>': '*',
            '<dash>': '-',
            '<sign_1>': '1',
            '<sign_2>': '2',
            '<sign_3>': '3',
            '<sign_4>': '4',
            '<sign_5>': '5',
            '<wild>': '?',
            '<tablet>': 'A',
            '<entry>': 'B',
            '<cultist>': 'C',
            '<blessing>': 'D',
            '<blood>': 'W',
            '<elder_sign>': 'E',
            '<fleur>': 'F',
            '<guardian>': 'G',
            '<frost>': 'H',
            '<seeker>': 'K',
            '<elder_thing>': 'L',
            '<mystic>': 'M',
            '<rogue>': 'R',
            '<skull>': 'S',
            '<auto_fail>': 'T',
            '<curse>': 'U',
            '<survivor>': 'V',
            '<agility>': 'a',
            '<agi>': 'a',
            '[agility]': 'a',
            '<bullet>': 'b',
            '<com>': 'c',
            '<combat>': 'c',
            '[combat]': 'c',
            '<horror>': 'd',
            '<resolution>': 'e',
            '<free>': 'f',
            '[fast]': 'f',
            '<damage>': 'h',
            '<intellect>': 'i',
            '[intellect]': 'i',
            '<int>': 'i',
            '<resource>': 'm',
            '<act>': 'n',
            '<action>': 'n',
            '[action]': 'n',
            '<open>': 'o',
            '<per>': 'p',
            '<per_large>': 'q',
            '<investigator>': 'q',
            '[per_investigator]': 'p',
            '<reaction>': 'r',
            '<unique>': 'u',
            '<willpower>': 'w',
            '<wil>': 'w',
            '[willpower]': 'w',
            '<day>': '<',
            '<night>': '>',
        }

        self.fonts = {
            'regular': {'path': font_dir / "Arno Pro" / "arnopro_regular.otf"},
            'caption': {'path': font_dir / "Arno Pro" / "arnopro_caption.otf"},
            'bold': {'path': font_dir / "Arno Pro" / "arnopro_bold.otf"},
            'semibold': {'path': font_dir / "Arno Pro" / "arnopro_semibold.ttf"},
            'italic': {'path': font_dir / "Arno Pro" / "arnopro_italic.otf"},
            'bolditalic': {'path': font_dir / "Arno Pro" / "arnopro_bolditalic.otf"},
            'icon': {'path': font_dir / "AHLCGSymbol.otf"},
            'cost': {'path': font_dir / "Arkhamic.ttf"},
            'title': {'path': font_dir / "Arkhamic.ttf"},
            'skill': {'path': font_dir / "Bolton.ttf"},
        }

        self._rebuild_tries()

    def get_translation(self, key, fallback):
        return self.card_renderer.translations.get(key, fallback)

    def _rebuild_tries(self):
        """(Re)build the tag-matching tries from the current tag dictionaries."""
        self._fmt_trie = _build_trie(self.formatting_tags)
        self._icon_trie = _build_trie(self.font_icon_tags)
        # Pre-sort replacement tags longest-first for safe str.replace order
        self._replacement_order = sorted(self.replacement_tags.items(), key=lambda kv: -len(kv[0]))

    _HELP_BY_TOKEN_TYPE = {
        'break': 'line break',
        'hr': 'horizontal rule',
        'indent_pop': 'end indent',
        'underline': 'underline',
        'dbl_underline': 'double underline heading',
    }

    def get_help_text(self):
        text = tr("HELP_SPECIAL_TAGS_INTRO") + "\n\n"
        text += tr("HELP_FORMATTING_TAGS") + "\n"
        for tag, token in self.formatting_tags.items():
            token_type = token['type']
            if token_type in ('format', 'align', 'story'):
                desc = token['value']
            elif token_type == 'indent':
                desc = f'indent {token["value"]}'
            else:
                desc = self._HELP_BY_TOKEN_TYPE.get(token_type, token_type)
            text += f'  {tag}  ({desc})\n'
        text += "\n" + tr("HELP_REPLACEMENT_TAGS") + "\n"
        for tag, result in self.replacement_tags.items():
            text += f"  {tag} = {result}\n"
        text += "\n" + tr("HELP_ICON_TAGS") + "\n"
        for tag in self.font_icon_tags:
            text += f"  {tag}\n"
        text += "\n" + tr("HELP_AVAILABLE_FONTS") + "\n"
        for name in self.fonts:
            text += f"  {name}\n"
        return text

    def load_fonts(self, size):
        if size in self.font_cache:
            return self.font_cache[size]
        with perf.span('load_fonts (disk read + truetype init, all faces)'):
            loaded_fonts = {}
            for font_type, font_info in self.fonts.items():
                # Read into BytesIO so FreeType does not keep the file handle open.
                # On Windows an open FT_Face holds a CreateFile handle that blocks
                # the asset updater from overwriting the font file mid-session.
                font_bytes = io.BytesIO(pathlib.Path(font_info['path']).read_bytes())
                font = ImageFont.truetype(font_bytes, size)
                ascent, descent = font.getmetrics()
                self._font_meta[font] = {
                    # sanitized so user font names are safe inside CSS/HTML quotes
                    'family': 'shoggoth-' + re.sub(r'[^A-Za-z0-9_-]+', '-', font_type),
                    'path': str(font_info['path']),
                    'size': size,
                    'ascent': ascent,
                    'descent': descent,
                }
                loaded_fonts[font_type] = font
            self.font_cache[size] = loaded_fonts
        return loaded_fonts

    def clear_caches(self):
        """Drop all in-memory caches so updated assets are picked up on next render."""
        self.font_cache.clear()
        self._font_meta.clear()
        self._wcache.clear()
        self._glyph_run_cache.clear()
        self.icon_cache.clear()

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
                    p = pathlib.Path(result.stdout.strip())
                    if p.exists() and p.stem.lower() == name_lower:
                        return p
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
            for ext in ('*.ttf', '*.otf', '*.TTF', '*.OTF'):
                for font_file in search_dir.rglob(ext):
                    if font_file.stem.lower() == name_lower:
                        return font_file
        return None

    def _resolve_font(self, name, project=None):
        """Resolve a <font "..."> name to a key in self.fonts.

        Returns (font_key, missing).  When the font cannot be found in the
        project files or on the system, falls back to ('regular', True); the
        caller renders the text struck-through as a visible "missing font"
        marker.  Lookups (including failures) are cached in _user_font_keys.
        """
        if name in self.fonts:
            return name, False
        if name in self._user_font_keys:
            entry = self._user_font_keys[name]
            return ('regular', True) if entry is None else (entry, False)
        font_key = f'__user__{name}'
        p = None
        if project:
            p = project.find_file(name)
        if not p:
            p = pathlib.Path(name)
        if p.exists() and p.suffix.lower() in ('.ttf', '.otf'):
            self.fonts[font_key] = {'path': p, 'scale': 1, 'fallback': None}
            self.font_cache.clear()
            self._user_font_keys[name] = font_key
            return font_key, False
        with perf.span('Scan system fonts for custom <font> tag (fallback)'):
            system_path = self._find_system_font(name)
        if system_path:
            self.fonts[font_key] = {'path': system_path, 'scale': 1, 'fallback': None}
            self.font_cache.clear()
            self._user_font_keys[name] = font_key
            return font_key, False
        self._user_font_keys[name] = None
        return 'regular', True

    def load_icon(self, icon_path, height):
        if str(icon_path).endswith('.svg'):
            return self.card_renderer.get_resized_cached(icon_path, (height, height))
        if (icon_path, height) in self.icon_cache:
            return self.icon_cache[(icon_path, height)]

        icon = self.card_renderer.get_cached(icon_path).convert("RGBA")
        aspect_ratio = icon.width / icon.height
        new_width = int(height * aspect_ratio)
        icon = icon.resize((new_width, height))
        self.icon_cache[(icon_path, height)] = icon
        return icon

    def _get_icon(self, icon_path, font_size, color=None):
        """Returns an image as an in-line icon.

        color can be "inverted" or any Pillow color (word, hex, rgb(...)),
        which tints a grayscale icon so black becomes that color.
        """
        key = (icon_path, font_size, color)
        if key in self.icon_cache:
            return self.icon_cache[key]
        icon_img = self.load_icon(icon_path, font_size)
        if color == "inverted":
            icon_img = invert_icon(icon_img)
        elif color:
            try:
                icon_img = colorize_icon(icon_img, color)
            except ValueError:
                print(f"Unknown inline icon color: {color!r}")
        self.icon_cache[key] = icon_img
        return icon_img

    def _expand_bullet_shorthand(self, text):
        lines = text.split('\n')
        result = []
        in_list = False
        for line in lines:
            if line.startswith('- '):
                if not in_list:
                    result.append('<indent 25>')
                    in_list = True
                result.append('<bullet> ' + line[2:])
            else:
                if in_list:
                    result.append('</indent>')
                    in_list = False
                result.append(line)
        if in_list:
            result.append('</indent>')
        return '\n'.join(result)

    def _apply_smart_quotes(self, text):
        # Protect backslash-escaped quotes so users can opt out of smart conversion
        text = text.replace('\\"', '\x00DQ\x00')
        text = text.replace("\\'", '\x00SQ\x00')

        result = []
        in_tag = False
        prev_outside = None  # last char seen outside a tag (tags are transparent to context)

        for ch in text:
            if ch == '<':
                in_tag = True
                result.append(ch)
            elif ch == '>':
                in_tag = False
                result.append(ch)
            elif in_tag:
                result.append(ch)
            elif ch == '"':
                result.append('\u201c' if prev_outside is None or prev_outside in (' ', '\t', '\n') else '\u201d')
                prev_outside = ch
            elif ch == "'":
                result.append('\u2018' if prev_outside is None or prev_outside in (' ', '\t', '\n') else '\u2019')
                prev_outside = ch
            else:
                result.append(ch)
                prev_outside = ch

        text = ''.join(result)
        text = text.replace('\x00DQ\x00', '"')
        text = text.replace('\x00SQ\x00', "'")
        return text

    def _get_hyphenator(self):
        """Return a cached pyphen.Pyphen for the card's language, or None if
        no hyphenation dictionary is available for it (e.g. CJK languages)."""
        locale = getattr(self.card_renderer, 'locale', None) or 'en'
        if locale not in self._hyphen_dicts:
            dic = None
            try:
                resolved = pyphen.language_fallback(locale)
                if resolved:
                    dic = pyphen.Pyphen(lang=resolved)
            except Exception:
                dic = None
            self._hyphen_dicts[locale] = dic
        return self._hyphen_dicts[locale]

    def _hyphenate_split(self, word, font_obj, max_width):
        """Try to split `word` with a hyphen so the head (including the
        trailing '-') renders within max_width pixels using font_obj.

        Returns (head, tail) for the longest fitting split, or None if the
        word has no dictionary, no letters to hyphenate, or no split point
        narrow enough to fit.
        """
        if max_width <= 0 or not self.hyphenation_enabled:
            return None
        hyphenator = self._get_hyphenator()
        if hyphenator is None:
            return None

        # Only hyphenate the alphabetic core, leaving surrounding punctuation
        # (quotes, commas, dashes, ...) attached to whichever half it belongs to.
        start, end = 0, len(word)
        while start < end and not word[start].isalpha():
            start += 1
        while end > start and not word[end - 1].isalpha():
            end -= 1
        core = word[start:end]
        if not core.isalpha():
            return None

        prefix, suffix = word[:start], word[end:]
        wcache = self._wcache
        for head, tail in hyphenator.iterate(core):
            # iterate() returns the raw split with no hyphen mark attached
            candidate = prefix + head + '-'
            if wcache.width(candidate, font_obj) <= max_width:
                return candidate, tail + suffix
        return None

    def _merge_last_two_words(self, toks):
        """Merge the last two plain-text words in a token list into a non-breaking unit."""
        last_space_i = None
        for i in range(len(toks) - 1, -1, -1):
            if toks[i]['type'] == 'text' and toks[i]['value'] == ' ':
                last_space_i = i
                break

        if last_space_i is None:
            return list(toks)

        # Everything after the last space must be plain text (the last word only)
        suffix = toks[last_space_i + 1:]
        if not suffix or any(t['type'] != 'text' or t['value'] == ' ' for t in suffix):
            return list(toks)

        # The token immediately before the space must also be plain text
        pre_i = last_space_i - 1
        if pre_i < 0 or toks[pre_i]['type'] != 'text' or toks[pre_i]['value'] == ' ':
            return list(toks)

        # Merge: embed the space inside the token so the layout engine won't break there
        combined = toks[pre_i]['value'] + ' ' + ''.join(t['value'] for t in suffix)
        return list(toks[:pre_i]) + [{'type': 'text', 'value': combined}]

    def _prevent_runts(self, tokens):
        """Combine the last two plain-text words of each paragraph to prevent single-word last lines."""
        if not tokens:
            return tokens

        result = []
        para = []
        for tok in tokens:
            if tok['type'] == 'newline':
                result.extend(self._merge_last_two_words(para))
                result.append(tok)
                para = []
            else:
                para.append(tok)
        result.extend(self._merge_last_two_words(para))
        return result

    def _merge_hr_breaks(self, tokens):
        """Collapse "<newline><hr><newline>" into a single 'hr_break' token.

        On official cards a horizontal rule still only takes up a single
        paragraph's worth of vertical space; left as three separate tokens,
        the two newlines would each add a full paragraph advance on top of
        the rule itself. Any other placement of <hr> (no newline on one or
        both sides) is left untouched and renders inline as before.
        """
        result = []
        i, n = 0, len(tokens)
        while i < n:
            if (tokens[i]['type'] == 'newline' and i + 2 < n
                    and tokens[i + 1]['type'] == 'hr'
                    and tokens[i + 2]['type'] == 'newline'):
                result.append({'type': 'hr_break'})
                i += 3
            else:
                result.append(tokens[i])
                i += 1
        return result

    def parse_text(self, text, project=None):
        tokens = []
        text = self._expand_bullet_shorthand(text)
        text = self._apply_smart_quotes(text)

        # Replacement tags (longest-first to avoid partial matches like -- before ---)
        for tag, new in self._replacement_order:
            text = text.replace(tag, new)

        pos = 0
        length = len(text)
        # Local refs for speed in tight loop
        fmt_trie = self._fmt_trie
        icon_trie = self._icon_trie

        while pos < length:
            ch = text[pos]

            # Newline
            if ch == '\n':
                tokens.append({'type': 'newline'})
                pos += 1
                continue

            # Space
            if ch == ' ':
                tokens.append({'type': 'text', 'value': ' '})
                pos += 1
                continue

            # Potential tag start
            if ch in ('<', '[', ']'):
                # 1) Formatting trie
                payload, tlen = _trie_match(fmt_trie, text, pos)
                if payload is not None:
                    tokens.append(payload)  # pre-built token dict (shared, immutable)
                    pos += tlen
                    # indent_pop eats trailing newline
                    if payload.get('type') == 'indent_pop' and pos < length and text[pos] == '\n':
                        pos += 1
                    continue

                # 2) Icon trie
                icon_char, tlen = _trie_match(icon_trie, text, pos)
                if icon_char is not None:
                    tokens.append({'type': 'font_icon', 'value': icon_char})
                    pos += tlen
                    continue

                # 3) Parametric tags (rare – regex only on these)
                if ch == '<':
                    remaining = text[pos:]

                    m = _size_re.match(remaining)
                    if m:
                        tokens.append({'type': 'size', 'value': int(m[1])})
                        pos += len(m[0])
                        continue

                    m = _indent_re.match(remaining)
                    if m:
                        tokens.append({'type': 'indent_push', 'value': int(m[1])})
                        pos += len(m[0])
                        # <indent> eats trailing newline
                        if pos < length and text[pos] == '\n':
                            pos += 1
                        continue

                    m = _margin_re.match(remaining)
                    if m:
                        tokens.append({'type': 'margin', 'value': int(m[1])})
                        pos += len(m[0])
                        continue

                    m = _font_re.match(remaining)
                    if m:
                        font_key, missing = self._resolve_font(m[1], project=project)
                        tokens.append({'type': 'font_push', 'font': font_key, 'strikethrough': missing})
                        pos += len(m[0])
                        continue

                    if remaining.startswith('</font>'):
                        tokens.append({'type': 'font_pop'})
                        pos += len('</font>')
                        continue

                    if remaining.startswith('</size>'):
                        tokens.append({'type': 'size_pop'})
                        pos += len('</size>')
                        continue

                    m = _image_re.match(remaining)
                    if m:
                        attrs = _parse_tag_attributes(m[0])
                        if 'src' in attrs:
                            src = attrs['src']
                            if project:
                                resolved = project.find_file(src)
                                if resolved:
                                    src = str(resolved)
                            tokens.append({'type': 'image_icon', 'value': src, 'color': attrs.get('color')})
                        pos += len(m[0])
                        continue

            # Plain text run
            # Scan forward until the next potential delimiter
            start = pos
            pos += 1
            while pos < length:
                c = text[pos]
                if c in ('<', '[', ']', ' ', '\n'):
                    break
                pos += 1
            tokens.append({'type': 'text', 'value': text[start:pos]})

        tokens = self._prevent_runts(tokens)
        tokens = self._merge_hr_breaks(tokens)
        return tokens

    def _layout(self, tokens, region, polygon, font_size, base_font='regular',
                alignment='left', fill='#231f20', outline=0, outline_fill=None,
                force=False, scale=1.0):
        fonts = self.load_fonts(font_size)
        line_height = int(font_size * LINE_HEIGHT_FACTOR)

        x_orig = region.x
        y = region.y + font_size
        y_limit = region.y + region.height

        commands = []

        # Scoped formatting state.  Opening tags push the previous value onto
        # the matching stack; closing tags restore it (falling back to the
        # given default on unbalanced input).
        state = {
            'font': base_font,
            'fonts': fonts,           # size-scoped font set, changed by <size>
            'strikethrough': False,
            'underline': False,
            'align': alignment,
            'block_indent': 0,
        }
        stacks = {key: [] for key in state}

        def push_scope(key, value):
            stacks[key].append(state[key])
            state[key] = value

        def pop_scope(key, default):
            state[key] = stacks[key].pop() if stacks[key] else default

        def set_scope(key, value, start, default):
            if start:
                push_scope(key, value)
            else:
                pop_scope(key, default)

        # Blockquote state
        quote = False
        quote_last = False
        quote_first = False

        dbl_underline_pending = False

        # Hanging indent after a leading bullet
        current_indent = 0
        indent_current = False

        prev_block_indent = 0

        # Line buffer
        pending = []
        current_line_width = 0.0
        has_renderable = False        # replaces any() check in flush

        # Overflow after a newline is only checked once the next renderable
        # token arrives, so trailing blank lines never trigger it.
        overflow_check_pending = False

        # Width helper
        wcache = self._wcache

        # Polygon helpers
        def poly_bounds(yy):
            if not polygon:
                return x_orig, x_orig + region.width
            xs = []
            for idx in range(len(polygon) - 1):
                (x1, y1), (x2, y2) = polygon[idx], polygon[idx + 1]
                if (y1 < yy and y2 < yy) or (y1 > yy and y2 > yy) or y1 == y2:
                    continue
                t = (yy - y1) / (y2 - y1)
                xs.append(x1 + t * (x2 - x1))
            if not xs:
                return x_orig, x_orig + region.width
            return min(xs), max(xs)

        def eff_bounds(yy):
            nonlocal prev_block_indent
            li = state['block_indent']
            if polygon:
                p_left, p_right = poly_bounds(yy)
                if li:
                    if not prev_block_indent:
                        prev_block_indent = p_left + li
                    eff_x = max(prev_block_indent, p_left)
                else:
                    prev_block_indent = 0
                    eff_x = p_left
                eff_w = p_right - eff_x
            else:
                eff_x = x_orig + li
                eff_w = region.width - li
            return eff_x, eff_w

        def line_indent():
            # Mirrors the indent flush() applies when drawing: a blockquote's
            # fixed indent overrides any hanging bullet indent for the line.
            if quote or quote_first or quote_last:
                return int(QUOTE_INDENT * scale)
            return current_indent if indent_current else 0

        def wrap_width(yy):
            indent = line_indent()
            if polygon:
                p_left, p_right = poly_bounds(yy)
                return p_right - max(x_orig + state['block_indent'], p_left) - indent
            return region.width - state['block_indent'] - indent

        def flush():
            """Emit draw commands for the line buffered in `pending`."""
            nonlocal quote_first, quote_last, dbl_underline_pending

            if not has_renderable:
                quote_first = False
                dbl_underline_pending = False
                return

            indent = current_indent if indent_current else 0

            line_y = y

            if quote or quote_first or quote_last:
                bar_top = line_y - (font_size * 0.8 if quote_first else line_height)
                quote_first = False
                for bar_x in (x_orig, x_orig + int(scale*QUOTE_BAR_SPACING)):
                    commands.append({'cmd': 'line',
                                     'x1': bar_x, 'y1': bar_top, 'x2': bar_x, 'y2': line_y,
                                     'fill': fill, 'width': int(scale*2)})
                    indent = int(QUOTE_INDENT * scale)

            eff_x, eff_w = eff_bounds(line_y)
            eff_x += indent
            eff_w -= indent

            items = pending
            if items and items[0].get('cmd') == 'text' and items[0].get('value') == ' ':
                items = items[1:]

            line_w = sum(item['width'] for item in items)
            if state['align'] == 'center':
                x_pos = eff_x + (eff_w - line_w) / 2
            elif state['align'] == 'right':
                x_pos = eff_x + eff_w - line_w
            else:
                x_pos = eff_x

            line_x_start = x_pos  # capture for double underline

            # ── Merge adjacent same-font text/glyph items into single draws ──
            # This is the critical optimisation: a typical line of 10 words + spaces
            # becomes 2-3 draw.text() calls instead of ~20.
            merge_text = []   # accumulator: chars for current merge run
            merge_font = None
            merge_x = 0.0
            merge_w = 0.0
            merge_strike = False
            merge_underline = False

            def _emit_merged():
                nonlocal merge_text, merge_font, merge_w, merge_strike, merge_underline
                if not merge_text:
                    return 0.0
                val = ''.join(merge_text)
                # True advance (with kerning) may differ from our per-char sum.
                # Return the correction so callers can fix x_pos at font boundaries.
                true_advance = merge_font.getlength(val)
                commands.append({
                    'cmd': 'text',
                    'x': merge_x, 'y': line_y,
                    'value': val,
                    'font': merge_font,
                    'line_height': line_height,
                    'fill': fill, 'outline': outline, 'outline_fill': outline_fill,
                })
                if merge_strike:
                    sy = int(line_y + font_size * STRIKETHROUGH_Y_FACTOR)
                    commands.append({
                        'cmd': 'line',
                        'x1': int(merge_x), 'y1': sy,
                        'x2': int(merge_x + merge_w), 'y2': sy,
                        'fill': fill, 'width': max(1, font_size // 16),
                    })
                if merge_underline:
                    uy = int(line_y + font_size * UNDERLINE_Y_FACTOR)
                    commands.append({
                        'cmd': 'line',
                        'x1': int(merge_x), 'y1': uy,
                        'x2': int(merge_x + merge_w), 'y2': uy,
                        'fill': fill, 'width': max(1, font_size // 18),
                    })
                merge_text = []
                merge_font = None  # force next run to start fresh at current x_pos
                return true_advance - merge_w

            for item in items:
                c = item['cmd']
                if c in ('text', 'glyph'):
                    fobj = item['font']
                    st = item.get('strikethrough', False)
                    ul = item.get('underline', False)
                    # Continue merging if same font, strikethrough, and underline state
                    if fobj is merge_font and st == merge_strike and ul == merge_underline:
                        merge_text.append(item['value'])
                        merge_w += item['width']
                    else:
                        x_pos += _emit_merged()
                        merge_font = fobj
                        merge_strike = st
                        merge_underline = ul
                        merge_x = x_pos
                        merge_w = item['width']
                        merge_text = [item['value']]
                    x_pos += item['width']
                elif c == 'image':
                    x_pos += _emit_merged()
                    if item['icon'] is not None:
                        # line_y is the baseline; center the icon on the em box,
                        # whose top sits ascent pixels above the baseline
                        icon_y = int(line_y - item['icon'].height*.85)
                        commands.append({'cmd': 'image',
                                         'x': int(x_pos), 'y': icon_y,
                                         'icon': item['icon']})
                    x_pos += item['width']
                elif c == 'hr':
                    x_pos += _emit_merged()
                    hr_y = int(line_y + font_size * 0.5)
                    commands.append({
                        'cmd': 'line',
                        'x1': int(eff_x), 'y1': hr_y,
                        'x2': int(eff_x + eff_w), 'y2': hr_y,
                        'fill': fill, 'width': max(1, font_size // 18),
                    })
                    x_pos += item['width']

            _emit_merged()

            if dbl_underline_pending:
                dbl_underline_pending = False
                u_thick = max(1, font_size // 18)
                u_y1 = int(line_y + font_size * DBL_UNDERLINE_Y_FACTOR)
                u_y2 = u_y1 + u_thick + max(2, font_size // 10)
                u_x1 = int(line_x_start)
                u_x2 = int(line_x_start + line_w)
                for u_y in (u_y1, u_y2):
                    commands.append({'cmd': 'line', 'x1': u_x1, 'y1': u_y,
                                     'x2': u_x2, 'y2': u_y, 'fill': fill, 'width': u_thick})

            quote_last = False

        def start_new_line(advance):
            """Flush the buffered line, reset per-line state, and advance y."""
            nonlocal has_renderable, current_line_width, y
            flush()
            pending.clear()
            has_renderable = False
            current_line_width = 0
            y += advance

        # Main token loop
        num_tokens = len(tokens)
        for i, token in enumerate(tokens):
            t = token['type']

            if t == 'format':
                set_scope('font', token['value'], token['start'], base_font)

            elif t == 'story':
                if token['start']:
                    push_scope('font', 'italic')
                    quote = True
                    quote_first = True
                else:
                    pop_scope('font', base_font)
                    quote = False
                    quote_last = True

            elif t == 'font_push':
                push_scope('font', token['font'])
                push_scope('strikethrough', token['strikethrough'])

            elif t == 'font_pop':
                pop_scope('font', base_font)
                pop_scope('strikethrough', False)

            elif t == 'underline':
                set_scope('underline', True, token['start'], False)

            elif t == 'dbl_underline':
                if not token['start']:
                    dbl_underline_pending = True

            elif t == 'align':
                set_scope('align', token['value'], token['start'], alignment)

            elif t == 'margin':
                y += token['value']

            elif t == 'indent_push':
                push_scope('block_indent', token['value'])

            elif t == 'indent_pop':
                pop_scope('block_indent', 0)

            elif t == 'size':
                scaled_size = int(round(token['value'] * scale))
                push_scope('fonts', self.load_fonts(scaled_size))
                line_height = int(scaled_size * LINE_HEIGHT_FACTOR)

            elif t == 'size_pop':
                pop_scope('fonts', fonts)
                line_height = int(state['fonts']['regular'].size * LINE_HEIGHT_FACTOR)

            elif t in ('newline', 'break'):
                # A newline advances a full line height; <br> (and newlines
                # inside an indented block) advance by the bare font size.
                if t == 'newline' and state['block_indent'] == 0:
                    advance = line_height
                else:
                    advance = state['fonts']['regular'].size
                start_new_line(advance)
                current_indent = 0
                indent_current = False
                quote_last = False
                overflow_check_pending = True

            elif t == 'hr_break':
                # Emitted by _merge_hr_breaks for "\n<hr>\n": the rule itself
                # occupies one full line height (split above/below it),
                # rather than the two line heights the surrounding newlines
                # would otherwise add up to, so a divider keeps the spacing
                # of a single paragraph break like it does on official cards.
                if overflow_check_pending:
                    overflow_check_pending = False
                    if y > y_limit and not force:
                        return commands, False, i / num_tokens

                start_new_line(0)  # flush the line before the break, no advance yet

                half = line_height / 2
                y += half
                eff_x, eff_w = eff_bounds(y)
                hr_y = int(y)
                commands.append({
                    'cmd': 'line',
                    'x1': int(eff_x), 'y1': hr_y,
                    'x2': int(eff_x + eff_w), 'y2': hr_y,
                    'fill': fill, 'width': max(1, font_size // 18),
                })
                y += line_height

                current_indent = 0
                indent_current = False
                quote_last = False
                overflow_check_pending = True

            elif t in ('text', 'font_icon', 'image_icon', 'hr'):
                if overflow_check_pending:
                    overflow_check_pending = False
                    if y > y_limit and not force:
                        return commands, False, i / num_tokens

                if t == 'text':
                    value = token['value']
                    font_obj = state['fonts'][state['font']]
                    while True:
                        w = wcache.width(value, font_obj)
                        avail = wrap_width(y)
                        if current_line_width + w <= avail:
                            break

                        # Word doesn't fit on the current line: try to hyphenate
                        # it so part of it can still fill the remaining space
                        # (or, if the line is empty, the full line width).
                        split = self._hyphenate_split(value, font_obj, avail - current_line_width)
                        if split is None and current_line_width == 0:
                            break  # can't split further and it's alone on the line: accept overflow

                        if split is not None:
                            head, tail = split
                            pending.append({
                                'cmd': 'text',
                                'value': head,
                                'font': font_obj,
                                'width': wcache.width(head, font_obj),
                                'strikethrough': state['strikethrough'],
                                'underline': state['underline'],
                            })
                            has_renderable = True
                            value = tail

                        start_new_line(state['fonts']['regular'].size)
                        indent_current = current_indent > 0
                        if y > y_limit and not force:
                            return commands, False, i / num_tokens

                    item = {
                        'cmd': 'text',
                        'value': value,
                        'font': font_obj,
                        'width': w,
                        'strikethrough': state['strikethrough'],
                        'underline': state['underline'],
                    }
                elif t == 'font_icon':
                    font_obj = state['fonts']['icon']
                    w = wcache.width(token['value'], font_obj)
                    item = {'cmd': 'glyph', 'value': token['value'], 'font': font_obj, 'width': w}
                    # A bullet at line start sets a hanging indent for the
                    # wrapped continuation lines of this list entry
                    if token['value'] == 'b' and not pending:
                        current_indent = wcache.width('b ', font_obj)
                elif t == 'image_icon':
                    regular = state['fonts']['regular']
                    icon_img = self._get_icon(token['value'], int(regular.size), color=token.get('color'))
                    w = icon_img.width if icon_img else 0
                    item = {'cmd': 'image', 'icon': icon_img, 'width': w,
                            'ascent': self._font_meta[regular]['ascent'],
                            'font_size': regular.size}
                else:  # hr
                    w = wrap_width(y)
                    item = {'cmd': 'hr', 'width': w}

                if t != 'text' and current_line_width + w > wrap_width(y):
                    start_new_line(state['fonts']['regular'].size)
                    indent_current = current_indent > 0
                    if y > y_limit and not force:
                        return commands, False, i / num_tokens

                pending.append(item)
                has_renderable = True
                current_line_width += w

        # Final line
        if pending:
            flush()
            if y > y_limit and not force:
                return commands, False, 1.0

        return commands, True, 1.0

    # ── HTML text layer ──────────────────────────────────────────────────
    # See HtmlTextCapture. Capture state is per-thread so that parallel card
    # exports sharing this renderer don't mix their text layers.

    def start_html_capture(self):
        """From now on (on this thread), capture text as HTML instead of rasterizing it."""
        self._html_tls.capture = HtmlTextCapture()

    def finish_html_capture(self):
        """Stop capturing and return the HtmlTextCapture (or None if not capturing)."""
        capture = getattr(self._html_tls, 'capture', None)
        self._html_tls.capture = None
        return capture

    @contextmanager
    def html_capture_paused(self):
        """Rasterize text normally within this block (e.g. for rotated fields)."""
        capture = getattr(self._html_tls, 'capture', None)
        self._html_tls.capture = None
        try:
            yield
        finally:
            self._html_tls.capture = capture

    def _emit_html(self, capture, commands):
        """Convert layout commands to absolutely positioned HTML elements.

        Text is anchored by baseline in the commands; CSS positions boxes by
        their top edge, so the top is baseline minus the font's ascent, with
        line-height pinned to ascent+descent to cancel CSS half-leading.
        """
        parts = capture.parts
        for cmd in commands:
            c = cmd['cmd']
            if c in ('text', 'glyph'):
                meta = self._font_meta.get(cmd['font'])
                if meta is None:
                    continue
                family = meta['family']
                capture.fonts[family] = meta['path']
                style = (
                    f'position:absolute;white-space:pre;'
                    f'left:{cmd["x"]:.2f}px;top:{cmd["y"] - meta["ascent"]:.2f}px;'
                    f"font-family:'{family}';font-size:{meta['size']}px;"
                    f'line-height:{meta["ascent"] + meta["descent"]}px;'
                    f'color:{cmd["fill"] or "#231f20"};'
                )
                if cmd.get('outline'):
                    # Approximate the raster stroke with 8-direction shadows
                    w = cmd['outline']
                    outline_fill = cmd.get('outline_fill') or '#000000'
                    shadows = ','.join(f'{dx}px {dy}px 0 {outline_fill}'
                                       for dx in (-w, 0, w) for dy in (-w, 0, w)
                                       if dx or dy)
                    style += f'text-shadow:{shadows};'
                parts.append(f'<span style="{style}">{html_lib.escape(cmd["value"])}</span>')
            elif c == 'line':
                # Lines are always axis-aligned; PIL centers the stroke on the segment
                x1, y1, x2, y2, w = cmd['x1'], cmd['y1'], cmd['x2'], cmd['y2'], cmd['width']
                if y1 == y2:
                    left, top, box_w, box_h = min(x1, x2), y1 - w / 2, abs(x2 - x1), w
                else:
                    left, top, box_w, box_h = x1 - w / 2, min(y1, y2), w, abs(y2 - y1)
                parts.append(
                    f'<div style="position:absolute;left:{left:.2f}px;top:{top:.2f}px;'
                    f'width:{box_w:.2f}px;height:{box_h:.2f}px;'
                    f'background:{cmd["fill"] or "#231f20"};"></div>')
            # 'image' commands stay in the raster layer

    def _render(self, image, commands):
        draw = ImageDraw.Draw(image)
        fontmode = draw.fontmode
        for cmd in commands:
            c = cmd['cmd']
            if c == 'text' or c == 'glyph':
                if not cmd['outline']:
                    # No stroke: reuse a cached, already-shaped (kerned) glyph
                    # run instead of re-running FreeType/raqm shaping. Stroked
                    # runs fall through to draw.text unchanged (see
                    # _GlyphRunCache docstring for why this can't be extended
                    # to arbitrary per-character composition).
                    x, y = cmd['x'], cmd['y']
                    ix, iy = int(x), int(y)
                    mask, offset = self._glyph_run_cache.get(
                        cmd['font'], cmd['value'], fontmode, 0, (x - ix, y - iy),
                    )
                    px, py = ix + offset[0], iy + offset[1]
                    if mask.size[0] and mask.size[1]:
                        image.paste(cmd['fill'], (px, py, px + mask.size[0], py + mask.size[1]), mask)
                    continue
                draw.text(
                    (cmd['x'], cmd['y']),
                    cmd['value'],
                    fill=cmd['fill'],
                    font=cmd['font'],
                    stroke_width=cmd['outline'],
                    stroke_fill=cmd['outline_fill'],
                    anchor='ls'
                )
            elif c == 'image':
                image.paste(cmd['icon'], (cmd['x'], cmd['y']), cmd['icon'])
            elif c == 'line':
                draw.line(
                    [(cmd['x1'], cmd['y1']), (cmd['x2'], cmd['y2'])],
                    fill=cmd['fill'],
                    width=cmd['width'],
                )

    def render_text(self, image, text, region, polygon=None, alignment='left',
                    font_size=32, min_font_size=None, font=None, outline=0,
                    outline_fill=None, fill='#231f20', scale=1.0,
                    project=None, valignment='top'):
        if not text:
            return

        with perf.span('parse_text (tokenize)'):
            tokens = self.parse_text(text, project=project)

        if not font:
            font = 'regular'
        if min_font_size is None:
            min_font_size = font_size // 2

        current_size = font_size
        with perf.span('layout shrink-fit loop (_layout, all size steps)'):
            while current_size >= min_font_size:
                force = current_size == min_font_size
                commands, fits, frac = self._layout(
                    tokens, region, polygon, current_size,
                    base_font=font, alignment=alignment,
                    fill=fill, outline=outline, outline_fill=outline_fill,
                    force=force, scale=scale,
                )
                if fits or force:
                    break

                # Accelerate font-size reduction based on how early the overflow occurred
                current_size -= 1
                if 0 < frac < 0.8:
                    current_size -= 1
                if 0 < frac < 0.5:
                    current_size -= 1
                if 0 < frac < 0.3:
                    current_size -= 1

        if valignment == 'center' and commands:
            ys = [cmd['y'] for cmd in commands if 'y' in cmd]
            if ys:
                text_bottom = max(ys) + int(current_size * LINE_HEIGHT_FACTOR)
                text_height = text_bottom - region.y
                offset = (region.height - text_height) // 2
                if offset > 0:
                    for cmd in commands:
                        for key in ('y', 'y1', 'y2'):
                            if key in cmd:
                                cmd[key] += offset
        with perf.span('rasterize (_render/_emit_html)'):
            capture = getattr(self._html_tls, 'capture', None)
            if capture is None:
                self._render(image, commands)
            else:
                # Vector text mode: inline images (recolored icons etc.)
                # stay raster; text, glyphs, and rules become HTML.
                self._render(image, [c for c in commands if c['cmd'] == 'image'])
                self._emit_html(capture, commands)
