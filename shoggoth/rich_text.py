from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageOps
import io
import os
import platform
import pathlib
import numpy as np
import re
import pyphen
from shoggoth.files import font_dir
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


class RichTextRenderer:
    def __init__(self, card_renderer):
        self.card_renderer = card_renderer
        self.icon_cache = {}
        self.font_cache = {}
        self.user_font_cache = {}
        self._user_font_keys = {}

        self.alignment = 'left'
        self.min_font_size = 10

        # ── Width cache (shared across all renders) ──────────────────────────
        self._wcache = _WidthCache()

        # ── Hyphenation dictionaries, keyed by card language ──────────────────
        self._hyphen_dicts = {}

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
            '<u>': {'start': True, 'underline': True},
            '</u>': {'start': False, 'underline': True},
            '<dbl>': {'start': True, 'dbl_underline': True},
            '</dbl>': {'start': False, 'dbl_underline': True},
            '<br>': {'break': True},
            '<hr>': {'hr': True},
            '</indent>': {'indent_pop': True},
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
        """(Re)build the two tries from current tag dictionaries."""
        # Formatting trie: each payload is a pre-built token dict
        fmt_map = {}
        for tag, info in self.formatting_tags.items():
            if 'font' in info:
                fmt_map[tag] = {'type': 'format',
                'value': info['font'], 'start': info['start']}
            elif 'align' in info:
                fmt_map[tag] = {'type': 'align', 'value': info['align'], 'start': info['start']}
            elif 'indent' in info:
                fmt_map[tag] = {'type': 'indent', 'value': info['indent'], 'start': info['start']}
            elif 'format' in info:
                fmt_map[tag] = {'type': 'story', 'value': info['format'], 'start': info['start']}
            elif 'break' in info:
                fmt_map[tag] = {'type': 'break'}
            elif 'hr' in info:
                fmt_map[tag] = {'type': 'hr'}
            elif 'indent_pop' in info:
                fmt_map[tag] = {'type': 'indent_pop'}
            elif 'underline' in info:
                fmt_map[tag] = {'type': 'underline', 'start': info['start']}
            elif 'dbl_underline' in info:
                fmt_map[tag] = {'type': 'dbl_underline', 'start': info['start']}
        self._fmt_trie = _build_trie(fmt_map)

        # Icon trie: payload = character
        icon_map = {tag: char for tag, char in self.font_icon_tags.items()}
        self._icon_trie = _build_trie(icon_map)

        # Also pre-sort replacement tags longest-first for safe str.replace order
        self._replacement_order = sorted(self.replacement_tags.items(), key=lambda kv: -len(kv[0]))

    def get_help_text(self):
        text = tr("HELP_SPECIAL_TAGS_INTRO") + "\n\n"
        text += tr("HELP_FORMATTING_TAGS") + "\n"
        for tag, options in self.formatting_tags.items():
            if options.get('font'):
                text += f'  {tag}  ({options["font"]})\n'
            elif options.get('align'):
                text += f'  {tag}  ({options["align"]})\n'
            elif options.get('indent'):
                text += f'  {tag}  (indent {options["indent"]})\n'
            elif options.get('format'):
                text += f'  {tag}  ({options["format"]})\n'
            elif options.get('break'):
                text += f'  {tag}  (line break)\n'
            elif options.get('hr'):
                text += f'  {tag}  (horizontal rule)\n'
            elif options.get('indent_pop'):
                text += f'  {tag}  (end indent)\n'
            elif options.get('underline'):
                text += f'  {tag}  (underline)\n'
            elif options.get('dbl_underline'):
                text += f'  {tag}  (double underline heading)\n'
            else:
                text += f'  {tag}\n'
        text += "\n" + tr("HELP_REPLACEMENT_TAGS") + "\n"
        for tag, result in self.replacement_tags.items():
            text += f"  {tag} = {result}\n"
        text += "\n" + tr("HELP_ICON_TAGS") + "\n"
        for tag in self.font_icon_tags:
            text += f"  {tag}\n"
        text += "\n" + tr("HELP_AVAILABLE_FONTS") + "\n"
        for tag, options in self.fonts.items():
            text += f"  {tag}\n"
        return text

    def load_fonts(self, size):
        if size in self.font_cache:
            return self.font_cache[size]
        loaded_fonts = {}
        for font_type, font_info in self.fonts.items():
            # Read into BytesIO so FreeType does not keep the file handle open.
            # On Windows an open FT_Face holds a CreateFile handle that blocks
            # the asset updater from overwriting the font file mid-session.
            font_bytes = io.BytesIO(pathlib.Path(font_info['path']).read_bytes())
            loaded_fonts[font_type] = ImageFont.truetype(font_bytes, size)
        self.font_cache[size] = loaded_fonts
        return loaded_fonts

    def clear_caches(self):
        """Drop all in-memory caches so updated assets are picked up on next render."""
        self.font_cache.clear()
        self._wcache.clear()
        self.icon_cache.clear()
        self.inverted_icon_cache.clear()

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

    def _resolve_font(self, name, project=None):
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

        icon = self.card_renderer.get_cached(icon_path).convert("RGBA")
        aspect_ratio = icon.width / icon.height
        new_width = int(height * aspect_ratio)
        icon = icon.resize((new_width, height))
        self.icon_cache[(icon_path, height)] = icon
        return icon

    def _get_icon(self, icon_path, font_size, color=None):
        """Returns an image as a in-line icon """
        key = (icon_path, font_size, color)
        if key in self.icon_cache:
            return self.icon_cache[key]
        icon_img = self.load_icon(icon_path, font_size)
        if color == "inverted":
            icon_img = invert_icon(icon_img)
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
        if max_width <= 0:
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
        tok_append = tokens.append

        while pos < length:
            ch = text[pos]

            # Newline
            if ch == '\n':
                tok_append({'type': 'newline'})
                pos += 1
                continue

            # Space
            if ch == ' ':
                tok_append({'type': 'text', 'value': ' '})
                pos += 1
                continue

            # Potential tag start
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
                        font_key, strikethrough = self._resolve_font(m[1], project=project)
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
                            tok_append({'type': 'image_icon', 'value': attrs['src'], 'color': attrs.get('color')})
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
            tok_append({'type': 'text', 'value': text[start:pos]})

        tokens = self._prevent_runts(tokens)
        return tokens

    def _layout(self, tokens, region, polygon, font_size, base_font='regular',
                alignment='left', fill='#231f20', outline=0, outline_fill=None,
                force=False, scale=1.0):
        fonts = self.load_fonts(font_size)
        current_fonts = fonts
        size_stack = []

        line_height = int(font_size * 1.30)

        x_orig = region.x
        y = region.y + font_size
        max_height = region.height

        commands = []
        cmd_append = commands.append

        # Formatting state
        current_font = base_font
        font_stack = []
        current_strikethrough = False
        strikethrough_stack = []
        current_alignment = alignment
        alignment_stack = []

        # Indent / block state
        block_indent = 0
        prev_block_indent = 0
        indent_stack = []
        current_indent = 0
        indent_current = False

        # Blockquote state
        quote = False
        quote_last = False

        # Underline state
        current_underline = False
        underline_stack = []
        dbl_underline_pending = False

        # Line buffer
        pending = []
        pending_append = pending.append
        current_line_width = 0.0
        has_renderable = False        # replaces any() check in flush

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
            nonlocal quote_last, has_renderable, dbl_underline_pending

            if not has_renderable:
                quote_last = False
                dbl_underline_pending = False
                return

            indent = current_indent if indent_current else 0

            line_y = y

            if quote or quote_last:
                bar_bottom = line_y + (font_size * 0.8 if quote_last else line_height)
                cmd_append({'cmd': 'line',
                            'x1': x_orig, 'y1': line_y, 'x2': x_orig, 'y2': bar_bottom,
                            'fill': fill, 'width': 2})
                cmd_append({'cmd': 'line',
                            'x1': x_orig + 10, 'y1': line_y, 'x2': x_orig + 10, 'y2': bar_bottom,
                            'fill': fill, 'width': 2})
                indent = 20

            eff_x, eff_w = eff_bounds(line_y)
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
                cmd_append({
                    'cmd': 'text',
                    'x': merge_x, 'y': line_y,
                    'value': val,
                    'font': merge_font,
                    'line_height': line_height,
                    'fill': fill, 'outline': outline, 'outline_fill': outline_fill,
                })
                if merge_strike:
                    sy = int(line_y + font_size * 0.45)
                    cmd_append({
                        'cmd': 'line',
                        'x1': int(merge_x), 'y1': sy,
                        'x2': int(merge_x + merge_w), 'y2': sy,
                        'fill': fill, 'width': max(1, font_size // 16),
                    })
                if merge_underline:
                    uy = int(line_y + font_size * 0.88)
                    cmd_append({
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
                        icon_y = int(line_y - (item['icon'].height))
                        cmd_append({'cmd': 'image',
                                    'x': int(x_pos), 'y': icon_y,
                                    'icon': item['icon']})
                    x_pos += item['width']
                elif c == 'hr':
                    x_pos += _emit_merged()
                    hr_y = int(line_y + font_size * 0.5)
                    cmd_append({
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
                u_y1 = int(line_y + font_size * 0.12)
                u_y2 = u_y1 + u_thick + max(2, font_size // 10)
                u_x1 = int(line_x_start)
                u_x2 = int(line_x_start + line_w)
                cmd_append({'cmd': 'line', 'x1': u_x1, 'y1': u_y1,
                            'x2': u_x2, 'y2': u_y1, 'fill': fill, 'width': u_thick})
                cmd_append({'cmd': 'line', 'x1': u_x1, 'y1': u_y2,
                            'x2': u_x2, 'y2': u_y2, 'fill': fill, 'width': u_thick})

            quote_last = False

        # Main token loop
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

            elif t == 'underline':
                if token['start']:
                    underline_stack.append(current_underline)
                    current_underline = True
                else:
                    current_underline = underline_stack.pop() if underline_stack else False

            elif t == 'dbl_underline':
                if not token['start']:
                    dbl_underline_pending = True

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
                scaled_size = int(round(int(token['value']) * scale))
                current_fonts = self.load_fonts(scaled_size)
                line_height = scaled_size * 1.30

            elif t == 'size_pop':
                current_fonts = size_stack.pop() if size_stack else fonts
                line_height = int(current_fonts['regular'].size) * 1.30

            elif t == 'newline':
                flush()
                current_indent = 0
                indent_current = False
                quote_last = False
                pending.clear()
                has_renderable = False
                current_line_width = 0
                y += current_fonts['regular'].size if block_indent > 0 else line_height
                overflow_check_pending = True

            elif t == 'break':
                flush()
                current_indent = 0
                indent_current = False
                quote_last = False
                pending.clear()
                has_renderable = False
                current_line_width = 0
                y += current_fonts['regular'].size
                overflow_check_pending = True

            elif t in ('text', 'font_icon', 'image_icon', 'hr'):
                if overflow_check_pending:
                    overflow_check_pending = False
                    if y > region.y + max_height:
                        if not force:
                            return commands, False, i / num_tokens

                if t == 'text':
                    value = token['value']
                    font_obj = current_fonts[current_font]
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
                            pending_append({
                                'cmd': 'text',
                                'value': head,
                                'font': font_obj,
                                'width': wcache.width(head, font_obj),
                                'strikethrough': current_strikethrough,
                                'underline': current_underline,
                            })
                            has_renderable = True
                            value = tail

                        flush()
                        indent_current = current_indent > 0
                        pending.clear()
                        has_renderable = False
                        current_line_width = 0
                        y += current_fonts['regular'].size
                        if y > region.y + max_height:
                            if not force:
                                return commands, False, i / num_tokens

                    item = {
                        'cmd': 'text',
                        'value': value,
                        'font': font_obj,
                        'width': w,
                        'strikethrough': current_strikethrough,
                        'underline': current_underline,
                    }
                elif t == 'font_icon':
                    font_obj = current_fonts['icon']
                    w = wcache.width(token['value'], font_obj)
                    item = {'cmd': 'glyph', 'value': token['value'], 'font': font_obj, 'width': w}
                    if token['value'] == 'b' and not pending:
                        current_indent = wcache.width('b ', font_obj)
                elif t == 'image_icon':
                    icon_img = self._get_icon(token['value'], current_fonts['regular'].size, color=token.get('color'))
                    w = icon_img.width if icon_img else 0
                    item = {'cmd': 'image', 'icon': icon_img, 'width': w}
                else:  # hr
                    w = wrap_width(y)
                    item = {'cmd': 'hr', 'width': w}

                if t != 'text' and current_line_width + w > wrap_width(y):
                    flush()
                    indent_current = current_indent > 0
                    pending.clear()
                    has_renderable = False
                    current_line_width = 0
                    y += current_fonts['regular'].size
                    if y > region.y + max_height:
                        if not force:
                            return commands, False, i / num_tokens

                pending_append(item)
                has_renderable = True
                current_line_width += w

        # Final line
        if pending:
            flush()
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
                    outline_fill=None, fill='#231f20', halign='top', scale=1.0,
                    project=None, valignment='top'):
        if not text:
            return

        tokens = self.parse_text(text, project=project)

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
                force=force, scale=scale,
            )
            if fits or force:
                if valignment == 'center' and commands:
                    ys = [cmd['y'] for cmd in commands if 'y' in cmd]
                    if ys:
                        text_bottom = max(ys) + int(current_size * 1.30)
                        text_height = text_bottom - region.y
                        offset = (region.height - text_height) // 2
                        if offset > 0:
                            for cmd in commands:
                                for key in ('y', 'y1', 'y2'):
                                    if key in cmd:
                                        cmd[key] += offset
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
