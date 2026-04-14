from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageOps
import os
import platform
import pathlib
import numpy as np
import re
from shoggoth.files import font_dir, icon_dir, overlay_dir
from shoggoth.i18n import tr

# Only keep regexes for the rare parametric tags (size, margin, indent, font, image)
_size_re = re.compile(r'<size (\d+?)>', flags=re.IGNORECASE)
_margin_re = re.compile(r'<margin (\d+?)(\s\d+?)*>', flags=re.IGNORECASE)
_indent_re = re.compile(r'<indent (\d+?)>', flags=re.IGNORECASE)
_font_re = re.compile(r'<font "(.+?)">', flags=re.IGNORECASE)
_image_re = re.compile(r'<image(\s\w+=\".+?\"){1,}?>', flags=re.IGNORECASE)
_tag_kv = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def _parse_tag_attributes(tag_string):
    return dict(re.findall(_tag_kv, tag_string))


# ── Trie for O(1)-per-char tag matching ──────────────────────────────────────

class _TrieNode:
    __slots__ = ('children', 'value', 'tag_len')
    def __init__(self):
        self.children = {}
        self.value = None   # payload when a complete tag ends here
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


# ── Icon helpers ─────────────────────────────────────────────────────────────

def recolor_icon(icon, color):
    data = np.array(icon)
    red, green, blue, alpha = data.T
    black_areas = (red == 0) & (blue == 0) & (green == 0)
    data[..., :-1][black_areas.T] = ImageColor.getcolor(color, "RGB")
    return Image.fromarray(data)


def invert_icon(icon):
    alpha = icon.getchannel('A')
    icon = icon.convert('RGB')
    icon = ImageOps.invert(icon)
    icon.putalpha(alpha)
    return icon


# ── Character-width cache ────────────────────────────────────────────────────

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


# ── Main class ───────────────────────────────────────────────────────────────

class RichTextRenderer:
    def __init__(self, card_renderer):
        self.card_renderer = card_renderer
        self.icon_cache = {}
        self.inverted_icon_cache = {}    # NEW: cache inverted icons
        self.font_cache = {}
        self.user_font_cache = {}
        self._user_font_keys = {}

        self.alignment = 'left'
        self.min_font_size = 10

        # ── Width cache (shared across all renders) ──────────────────────────
        self._wcache = _WidthCache()

        # ── Formatting tags ──────────────────────────────────────────────────
        self.formatting_tags = {
            '<b>': {'start': True, 'font': 'bold'},
            '</b>': {'start': False, 'font': 'bold'},
            '<i>': {'start': True, 'font': 'italic'},
            '</i>': {'start': False, 'font': 'italic'},
            '<bi>': {'start': True, 'font': 'bolditalic'},
            '</bi>': {'start': False, 'font': 'bolditalic'},
            '<t>': {'start': True, 'font': 'bolditalic'},
            '[[': {'start': True, 'font': 'bolditalic'},
            '</t>': {'start': False, 'font': 'bolditalic'},
            ']]': {'start': False, 'font': 'bolditalic'},
            '<icon>': {'start': True, 'font': 'icon'},
            '</icon>': {'start': False, 'font': 'icon'},
            '<center>': {'start': True, 'align': 'center'},
            '</center>': {'start': False, 'align': 'center'},
            '<left>': {'start': True, 'align': 'left'},
            '</left>': {'start': False, 'align': 'left'},
            '<right>': {'start': True, 'align': 'right'},
            '</right>': {'start': False, 'align': 'right'},
            '<story>': {'start': True, 'indent': 4},
            '</story>': {'start': False, 'indent': 4},
            '<blockquote>': {'start': True, 'format': 'quote', 'block': True},
            '</blockquote>': {'start': False, 'format': 'quote', 'block': True},
            '<br>': {'break': True},
            '</indent>': {'indent_pop': True},
        }

        self.replacement_tags = {
            '<for>': '<b>Forced –</b>',
            '<prey>': '<b>Prey –</b>',
            '<rev>': '<b>Revelation –</b>',
            '<spawn>': '<b>Spawn –</b>',
            '<obj>': '<b>Objective –</b>',
            '<objective>': '<b>Objective –</b>',
            '<quote>': '\u2018',
            '<dquote>': '\u201c',
            '<quoteend>': '\u2019',
            '<dquoteend>': '\u201d',
            '\'': '\u2019',
            '---': '\u2014',
            '--': '\u2013',
        }

        self.font_icon_tags = {
            '<codex>': '#',
            '<star>': '*',
            '<dash>': '-',
            '<sign_1>': '1', '<sign_2>': '2', '<sign_3>': '3',
            '<sign_4>': '4', '<sign_5>': '5',
            '<question>': '?',
            '<tablet>': 'A', '<entry>': 'B', '<cultist>': 'C',
            '<blessing>': 'D', '<elder_sign>': 'E', '<fleur>': 'F',
            '<guardian>': 'G', '<frost>': 'H', '<seeker>': 'K',
            '<elder_thing>': 'L', '<mystic>': 'M', '<rogue>': 'R',
            '<skull>': 'S', '<auto_fail>': 'T', '<curse>': 'U',
            '<survivor>': 'V',
            '<agility>': 'a', '<agi>': 'a', '[agility]': 'a',
            '<bullet>': 'b',
            '<com>': 'c', '<combat>': 'c', '[combat]': 'c',
            '<horror>': 'd', '<resolution>': 'e',
            '<free>': 'f', '[fast]': 'f',
            '<damage>': 'h',
            '<intellect>': 'i', '[intellect]': 'i', '<int>': 'i',
            '<resource>': 'm',
            '<act>': 'n', '<action>': 'n', '[action]': 'n',
            '<open>': 'o',
            '<per>': 'p', '[per_investigator]': 'p',
            '<reaction>': 'r',
            '<unique>': 'u',
            '<willpower>': 'w', '[willpower]': 'w',
            '<day>': '<', '<night>': '>',
        }

        self.fonts = {
            'regular':   {'path': font_dir / "Arno Pro" / "arnopro_regular.otf",    'scale': 1, 'fallback': None},
            'caption':   {'path': font_dir / "Arno Pro" / "arnopro_caption.otf",    'scale': 1, 'fallback': None},
            'bold':      {'path': font_dir / "Arno Pro" / "arnopro_bold.otf",       'scale': 1, 'fallback': None},
            'semibold':  {'path': font_dir / "Arno Pro" / "arnopro_semibold.ttf",   'scale': 1, 'fallback': None},
            'italic':    {'path': font_dir / "Arno Pro" / "arnopro_italic.otf",     'scale': 1, 'fallback': None},
            'bolditalic':{'path': font_dir / "Arno Pro" / "arnopro_bolditalic.otf", 'scale': 1, 'fallback': None},
            'icon':      {'path': font_dir / "AHLCGSymbol.otf",                     'scale': 1, 'fallback': None},
            'cost':      {'path': font_dir / "Arkhamic.ttf",                        'scale': 1, 'fallback': None},
            'title':     {'path': font_dir / "Arkhamic.ttf",                        'scale': 1, 'fallback': None},
            'skill':     {'path': font_dir / "Bolton.ttf",                          'scale': 1, 'fallback': None},
        }

        # ── Build tries on init (one-time cost) ─────────────────────────────
        self._rebuild_tries()

    # ── Trie construction ────────────────────────────────────────────────────

    def _rebuild_tries(self):
        """(Re)build the two tries from current tag dictionaries."""
        # Formatting trie: each payload is a pre-built token dict
        fmt_map = {}
        for tag, info in self.formatting_tags.items():
            if 'font' in info:
                fmt_map[tag] = {'type': 'format', 'value': info['font'], 'start': info['start']}
            elif 'align' in info:
                fmt_map[tag] = {'type': 'align', 'value': info['align'], 'start': info['start']}
            elif 'indent' in info:
                fmt_map[tag] = {'type': 'indent', 'value': info['indent'], 'start': info['start']}
            elif 'format' in info:
                fmt_map[tag] = {'type': 'story', 'value': info['format'], 'start': info['start']}
            elif 'break' in info:
                fmt_map[tag] = {'type': 'break'}
            elif 'indent_pop' in info:
                fmt_map[tag] = {'type': 'indent_pop'}
        self._fmt_trie = _build_trie(fmt_map)

        # Icon trie: payload = character
        icon_map = {tag: char for tag, char in self.font_icon_tags.items()}
        self._icon_trie = _build_trie(icon_map)

        # Also pre-sort replacement tags longest-first for safe str.replace order
        self._replacement_order = sorted(self.replacement_tags.items(), key=lambda kv: -len(kv[0]))

    # ── Public helpers (unchanged API) ───────────────────────────────────────

    def get_help_text(self):
        text = tr("HELP_SPECIAL_TAGS_INTRO") + "\n\n"
        text += tr("HELP_FORMATTING_TAGS") + "\n"
        for tag, options in self.formatting_tags.items():
            if options.get('start'):
                text += f'{tag}{options.get("font") or options.get("align")}'
            else:
                text += f'{tag}\n'
        text += "\n" + tr("HELP_REPLACEMENT_TAGS") + "\n"
        for tag, result in self.replacement_tags.items():
            text += f"{tag} = {result}\n"
        text += "\n" + tr("HELP_ICON_TAGS") + "\n"
        for tag in self.font_icon_tags:
            text += f"{tag}\n"
        text += "\n" + tr("HELP_AVAILABLE_FONTS") + "\n"
        for tag, options in self.fonts.items():
            text += f"{tag}: {options['path']}\n"
        return text

    def load_fonts(self, size):
        if size in self.font_cache:
            return self.font_cache[size]
        loaded_fonts = {}
        for font_type, font_info in self.fonts.items():
            loaded_fonts[font_type] = ImageFont.truetype(str(font_info['path']), size)
        self.font_cache[size] = loaded_fonts
        return loaded_fonts

    def load_font(self, font):
        if font not in self.fonts:
            self.fonts[font] = {'path': font, 'scale': 1, 'fallback': None}
        self.load_fonts

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

    def _resolve_font(self, name):
        if name in self.fonts:
            return name, False
        if name in self._user_font_keys:
            entry = self._user_font_keys[name]
            return ('regular', True) if entry is None else (entry, False)
        font_key = f'__user__{name}'
        p = pathlib.Path(name)
        if p.exists() and p.suffix.lower() in ('.ttf', '.otf'):
            self.fonts[font_key] = {'path': p, 'scale': 1, 'fallback': None}
            self.font_cache.clear()
            self._user_font_keys[name] = font_key
            return font_key, False
        system_path = self._find_system_font(name)
        if system_path:
            self.fonts[font_key] = {'path': system_path, 'scale': 1, 'fallback': None}
            self.font_cache.clear()
            self._user_font_keys[name] = font_key
            return font_key, False
        self._user_font_keys[name] = None
        return 'regular', True

    def load_icon(self, icon_path, height):
        if str(icon_path)[-4:] == '.svg':
            return self.card_renderer.get_resized_cached(icon_path, (height, height))
        if (icon_path, height) in self.icon_cache:
            return self.icon_cache[(icon_path, height)]
        if os.path.exists(icon_path):
            full_path = icon_path
        else:
            full_path = icon_dir / f"{icon_path}.png"
            if not os.path.exists(full_path):
                return None
        try:
            icon = Image.open(full_path).convert("RGBA")
            aspect_ratio = icon.width / icon.height
            new_width = int(height * aspect_ratio)
            icon = icon.resize((new_width, height), Image.LANCZOS)
            self.icon_cache[(icon_path, height)] = icon
            return icon
        except Exception:
            return None

    def _get_inverted_icon(self, icon_path, font_size):
        """Load + invert an icon, caching the inverted result."""
        key = (icon_path, font_size)
        cached = self.inverted_icon_cache.get(key)
        if cached is not None:
            return cached
        icon_img = self.load_icon(icon_path, font_size)
        if icon_img:
            icon_img = invert_icon(icon_img)
        self.inverted_icon_cache[key] = icon_img
        return icon_img

    # ── Bullet shorthand ─────────────────────────────────────────────────────

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

    # ── Parser (trie-based, single pass) ─────────────────────────────────────

    def parse_text(self, text):
        tokens = []
        text = self._expand_bullet_shorthand(text)

        # Replacement tags (longest-first to avoid partial matches like -- before ---)
        for tag, new in self._replacement_order:
            text = text.replace(tag, new)

        pos = 0
        length = len(text)
        # Local refs for speed in tight loop
        fmt_trie = self._fmt_trie
        icon_trie = self._icon_trie
        tok_append = tokens.append

        while pos < length:
            ch = text[pos]

            # ── Newline ──────────────────────────────────────────────────────
            if ch == '\n':
                tok_append({'type': 'newline'})
                pos += 1
                continue

            # ── Space ────────────────────────────────────────────────────────
            if ch == ' ':
                tok_append({'type': 'text', 'value': ' '})
                pos += 1
                continue

            # ── Potential tag start ──────────────────────────────────────────
            if ch in ('<', '[', ']'):
                # 1) Formatting trie
                payload, tlen = _trie_match(fmt_trie, text, pos)
                if payload is not None:
                    tok_append(payload)  # pre-built token dict (shared, immutable)
                    pos += tlen
                    # indent_pop eats trailing newline
                    if payload.get('type') == 'indent_pop' and pos < length and text[pos] == '\n':
                        pos += 1
                    continue

                # 2) Icon trie
                icon_char, tlen = _trie_match(icon_trie, text, pos)
                if icon_char is not None:
                    tok_append({'type': 'font_icon', 'value': icon_char})
                    pos += tlen
                    continue

                # 3) Parametric tags (rare – regex only on these)
                if ch == '<':
                    remaining = text[pos:]

                    m = _size_re.match(remaining)
                    if m:
                        tok_append({'type': 'size', 'value': m[1]})
                        pos += len(m[0])
                        continue

                    m = _indent_re.match(remaining)
                    if m:
                        tok_append({'type': 'indent_push', 'value': int(m[1])})
                        pos += len(m[0])
                        if pos < length and text[pos] == '\n':
                            pos += 1
                        continue

                    m = _margin_re.match(remaining)
                    if m:
                        tok_append({'type': 'margin', 'value': int(m[1])})
                        pos += len(m[0])
                        continue

                    m = _font_re.match(remaining)
                    if m:
                        font_key, strikethrough = self._resolve_font(m[1])
                        tok_append({'type': 'font_push', 'font': font_key, 'strikethrough': strikethrough})
                        pos += len(m[0])
                        continue

                    if remaining.startswith('</font>'):
                        tok_append({'type': 'font_pop'})
                        pos += 7
                        continue

                    if remaining.startswith('</size>'):
                        tok_append({'type': 'size_pop'})
                        pos += 7
                        continue

                    m = _image_re.match(remaining)
                    if m:
                        attrs = _parse_tag_attributes(m[0])
                        if 'src' in attrs:
                            tok_append({'type': 'image_icon', 'value': attrs['src']})
                        pos += len(m[0])
                        continue

            # ── Plain text run ───────────────────────────────────────────────
            # Scan forward until the next potential delimiter
            start = pos
            pos += 1
            while pos < length:
                c = text[pos]
                if c in ('<', '[', ']', ' ', '\n'):
                    break
                pos += 1
            tok_append({'type': 'text', 'value': text[start:pos]})

        return tokens

    # ── Layout engine ────────────────────────────────────────────────────────

    def _layout(self, tokens, region, polygon, font_size, base_font='regular',
                alignment='left', fill='#231f20', outline=0, outline_fill=None,
                force=False):
        fonts = self.load_fonts(font_size)
        current_fonts = fonts
        size_stack = []
        line_height = int(font_size * 1.30)

        x_orig = region.x
        y = region.y
        max_height = region.height

        commands = []
        cmd_append = commands.append

        # ── Formatting state ─────────────────────────────────────────────────
        current_font = base_font
        font_stack = []
        current_strikethrough = False
        strikethrough_stack = []
        current_alignment = alignment
        alignment_stack = []

        # ── Indent / block state ─────────────────────────────────────────────
        block_indent = 0
        prev_block_indent = 0
        indent_stack = []
        current_indent = 0
        indent_current = False

        # ── Blockquote state ─────────────────────────────────────────────────
        quote = False
        quote_last = False

        # ── Line buffer ──────────────────────────────────────────────────────
        pending = []
        pending_append = pending.append
        current_line_width = 0.0
        has_renderable = False        # replaces any() check in flush

        overflow_check_pending = False

        # ── Width helper ─────────────────────────────────────────────────────
        wcache = self._wcache

        # ── Polygon helpers ──────────────────────────────────────────────────

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
            li = block_indent
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

        def wrap_width(yy):
            if polygon:
                p_left, p_right = poly_bounds(yy)
                return p_right - max(x_orig + block_indent, p_left)
            return region.width - block_indent

        def flush():
            nonlocal quote_last, has_renderable

            if not has_renderable:
                quote_last = False
                return

            indent = current_indent if indent_current else 0

            if quote or quote_last:
                bar_bottom = y + (font_size * 0.8 if quote_last else line_height)
                cmd_append({'cmd': 'line',
                            'x1': x_orig, 'y1': y, 'x2': x_orig, 'y2': bar_bottom,
                            'fill': fill, 'width': 2})
                cmd_append({'cmd': 'line',
                            'x1': x_orig + 10, 'y1': y, 'x2': x_orig + 10, 'y2': bar_bottom,
                            'fill': fill, 'width': 2})
                indent = 20

            eff_x, eff_w = eff_bounds(y)
            eff_x += indent
            eff_w -= indent

            items = pending
            if items and items[0].get('cmd') == 'text' and items[0].get('value') == ' ':
                items = items[1:]

            line_w = sum(item['width'] for item in items)
            if current_alignment == 'center':
                x_pos = eff_x + (eff_w - line_w) / 2
            elif current_alignment == 'right':
                x_pos = eff_x + eff_w - line_w
            else:
                x_pos = eff_x

            # ── Merge adjacent same-font text/glyph items into single draws ──
            # This is the critical optimisation: a typical line of 10 words + spaces
            # becomes 2-3 draw.text() calls instead of ~20.
            merge_text = []   # accumulator: chars for current merge run
            merge_font = None
            merge_x = 0.0
            merge_w = 0.0
            merge_strike = False

            def _emit_merged():
                nonlocal merge_text, merge_font, merge_w, merge_strike
                if not merge_text:
                    return
                val = ''.join(merge_text)
                cmd_append({
                    'cmd': 'text',
                    'x': merge_x, 'y': y,
                    'value': val,
                    'font': merge_font,
                    'fill': fill, 'outline': outline, 'outline_fill': outline_fill,
                })
                if merge_strike:
                    sy = int(y + font_size * 0.45)
                    cmd_append({
                        'cmd': 'line',
                        'x1': int(merge_x), 'y1': sy,
                        'x2': int(merge_x + merge_w), 'y2': sy,
                        'fill': fill, 'width': max(1, font_size // 16),
                    })
                merge_text = []

            for item in items:
                c = item['cmd']
                if c in ('text', 'glyph'):
                    fobj = item['font']
                    st = item.get('strikethrough', False)
                    # Continue merging if same font and same strikethrough state
                    if fobj is merge_font and st == merge_strike:
                        merge_text.append(item['value'])
                        merge_w += item['width']
                    else:
                        _emit_merged()
                        merge_font = fobj
                        merge_strike = st
                        merge_x = x_pos
                        merge_w = item['width']
                        merge_text = [item['value']]
                    x_pos += item['width']
                elif c == 'image':
                    _emit_merged()
                    if item['icon'] is not None:
                        icon_y = int(y - (item['icon'].height - font_size) // 2)
                        cmd_append({'cmd': 'image',
                                    'x': int(x_pos), 'y': icon_y,
                                    'icon': item['icon']})
                    x_pos += item['width']

            _emit_merged()

            quote_last = False

        # ── Main token loop ──────────────────────────────────────────────────

        num_tokens = len(tokens)
        for i, token in enumerate(tokens):
            t = token['type']

            if t == 'format':
                if token['start']:
                    font_stack.append(current_font)
                    current_font = token['value']
                else:
                    current_font = font_stack.pop() if font_stack else base_font

            elif t == 'story':
                if token['start']:
                    font_stack.append(current_font)
                    current_font = 'italic'
                    quote = True
                else:
                    current_font = font_stack.pop() if font_stack else base_font
                    quote = False
                    quote_last = True

            elif t == 'font_push':
                font_stack.append(current_font)
                strikethrough_stack.append(current_strikethrough)
                current_font = token['font']
                current_strikethrough = token['strikethrough']

            elif t == 'font_pop':
                current_font = font_stack.pop() if font_stack else base_font
                current_strikethrough = strikethrough_stack.pop() if strikethrough_stack else False

            elif t == 'align':
                if token['start']:
                    alignment_stack.append(current_alignment)
                    current_alignment = token['value']
                else:
                    current_alignment = alignment_stack.pop() if alignment_stack else alignment

            elif t == 'margin':
                y += token['value']

            elif t == 'indent_push':
                indent_stack.append(block_indent)
                block_indent = token['value']

            elif t == 'indent_pop':
                block_indent = indent_stack.pop() if indent_stack else 0

            elif t == 'size':
                size_stack.append(current_fonts)
                current_fonts = self.load_fonts(int(token['value']))

            elif t == 'size_pop':
                current_fonts = size_stack.pop() if size_stack else fonts

            elif t == 'newline':
                flush()
                current_indent = 0
                indent_current = False
                quote_last = False
                pending.clear()
                has_renderable = False
                current_line_width = 0
                y += font_size if block_indent > 0 else line_height
                overflow_check_pending = True

            elif t == 'break':
                flush()
                current_indent = 0
                indent_current = False
                quote_last = False
                pending.clear()
                has_renderable = False
                current_line_width = 0
                y += font_size
                overflow_check_pending = True

            elif t in ('text', 'font_icon', 'image_icon'):
                if overflow_check_pending:
                    overflow_check_pending = False
                    if y + line_height > region.y + max_height:
                        if not force:
                            return commands, False, i / num_tokens

                if t == 'text':
                    font_obj = current_fonts[current_font]
                    w = wcache.width(token['value'], font_obj)
                    item = {
                        'cmd': 'text',
                        'value': token['value'],
                        'font': font_obj,
                        'width': w,
                        'strikethrough': current_strikethrough,
                    }
                elif t == 'font_icon':
                    font_obj = current_fonts['icon']
                    w = wcache.width(token['value'], font_obj)
                    item = {'cmd': 'glyph', 'value': token['value'], 'font': font_obj, 'width': w}
                    if token['value'] == 'b' and not pending:
                        current_indent = wcache.width('b ', font_obj)
                else:  # image_icon
                    icon_img = self._get_inverted_icon(token['value'], font_size)
                    w = icon_img.width if icon_img else 0
                    item = {'cmd': 'image', 'icon': icon_img, 'width': w}

                if current_line_width + w > wrap_width(y):
                    flush()
                    indent_current = current_indent > 0
                    pending.clear()
                    has_renderable = False
                    current_line_width = 0
                    y += font_size
                    if y + line_height > region.y + max_height:
                        if not force:
                            return commands, False, i / num_tokens

                pending_append(item)
                has_renderable = True
                current_line_width += w

        # ── Final line ───────────────────────────────────────────────────────
        if pending:
            flush()
            if y + line_height > region.y + max_height:
                if not force:
                    return commands, False, 1.0

        if not pending and overflow_check_pending:
            if y > region.y + max_height:
                if not force:
                    return commands, False, 1.0

        return commands, True, 1.0

    def _render(self, image, commands):
        draw = ImageDraw.Draw(image)
        for cmd in commands:
            c = cmd['cmd']
            if c == 'text' or c == 'glyph':
                draw.text(
                    (cmd['x'], cmd['y']),
                    cmd['value'],
                    fill=cmd['fill'],
                    font=cmd['font'],
                    stroke_width=cmd['outline'],
                    stroke_fill=cmd['outline_fill'],
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
                    outline_fill=None, fill='#231f20', halign='top'):
        if not text:
            return

        tokens = self.parse_text(text)

        if not font:
            font = 'regular'
        if min_font_size is None:
            min_font_size = font_size // 2

        current_size = font_size
        while current_size >= min_font_size:
            force = current_size == min_font_size
            commands, fits, frac = self._layout(
                tokens, region, polygon, current_size,
                base_font=font, alignment=alignment,
                fill=fill, outline=outline, outline_fill=outline_fill,
                force=force,
            )
            if fits or force:
                self._render(image, commands)
                break

            # Accelerate font-size reduction based on how early the overflow occurred
            current_size -= 1
            if 0 < frac < 0.8:
                current_size -= 1
            if 0 < frac < 0.5:
                current_size -= 1
            if 0 < frac < 0.3:
                current_size -= 1