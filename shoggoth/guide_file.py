"""The `.guide.md` file format: a campaign guide stored outside the project file.

A guide entry in a project either holds the whole guide, or points at a file:

    {"id": "...", "file": "guides/night-of-the-zealot.guide.md", "meta": {...}}

The file is plain Markdown, read top to bottom, so it diffs well in git and
can be edited by hand:

    ---
    name: The Night of the Zealot
    format: a4
    chapter: ch1
    ---

    [section cover: Cover]

    # The Night of the Zealot
    ...

    [section scenario: The Gathering | set: 3f2a9c1e-...]

    # Scenario I: The Gathering

* The `---` header holds the guide's own settings, one `key: value` per line.
  A value that reads as JSON (a number, `true`, `{...}`, `"..."`) is that
  JSON value; anything else is the text as written.
* `[section <type>: <name>]` starts a section; everything up to the next
  marker is its Markdown. Further settings follow as `| key: value`, the
  encounter set of a scenario as `| set: <id>`. A content line that would
  look like a marker is written with a backslash in front.
* Section ids aren't stored: sections are identified by position (see
  `Guide.sections`). Text before the first marker becomes an untitled
  section, and a file without a header takes its name from the file name.

Bookkeeping (`id`, `file`, `meta` with cloud timestamps) stays in the
project file, so the guide file only changes when the guide does.

Pure logic, no I/O.
"""
import json
import re

SUFFIX = '.guide.md'

# Keys of a guide entry that stay in the project file
PROJECT_KEYS = ('id', 'file', 'meta')
# Header keys that are always text, so a hand-written `name: 1929` stays one
_TEXT_KEYS = ('name', 'front_page', 'format', 'chapter')

_MARKER = re.compile(r'^\[section ([\w-]+)((?::| *\|).*)?\]$')
_ESCAPED_MARKER = re.compile(r'^(\\*)(\[section )')
# Section keys with their own place in the marker
_SECTION_FIXED = ('id', 'type', 'name', 'markdown')
_SECTION_ALIASES = {'encounter_set_id': 'set'}


# ── Values ───────────────────────────────────────────────────────────────

def _encode(value, special: str = '') -> str:
    """A value as written after `key: `. Plain text stays plain, unless it
    would read back as something else (JSON, surrounding whitespace, a line
    break, or one of the `special` characters)."""
    if isinstance(value, str):
        plain = (
            value
            and value == value.strip()
            and '\n' not in value
            and not any(c in value for c in special)
            and not _reads_as_json(value)
        )
        if plain:
            return value
    return json.dumps(value, ensure_ascii=False)


def _reads_as_json(text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True


def _decode(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        return text


def _split_fields(text: str) -> list:
    """Splits a marker's `name | key: value | ...` on the bars that aren't
    inside a JSON string."""
    parts, current, in_string, escaped = [], [], False, False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == '|':
            parts.append(''.join(current))
            current = []
            continue
        current.append(char)
    parts.append(''.join(current))
    return parts


# ── Writing ──────────────────────────────────────────────────────────────

def _marker(section: dict) -> str:
    line = f"[section {section.get('type') or 'blank'}"
    name = section.get('name') or ''
    if name:
        line += ': ' + _encode(name, '|]')
    for key, value in section.items():
        if key in _SECTION_FIXED or value is None:
            continue
        line += f" | {_SECTION_ALIASES.get(key, key)}: {_encode(value, '|]')}"
    return line + ']'


def _escape_markers(markdown: str) -> str:
    return '\n'.join(_ESCAPED_MARKER.sub(r'\\\1\2', line) for line in markdown.split('\n'))


def serialize(entry: dict) -> str:
    """The file text for a guide entry (its project-file keys left out)."""
    header = [f'{key}: {_encode(value)}' for key, value in entry.items()
              if key not in PROJECT_KEYS and key != 'sections']
    parts = ['---\n' + ''.join(line + '\n' for line in header) + '---\n']
    sections = entry.get('sections') or []
    for section in sections:
        # a blank line around each marker; `_section_text` takes them off again
        parts.append(f'\n{_marker(section)}\n\n{_escape_markers(section.get("markdown") or "")}\n')
    return ''.join(parts)


# ── Reading ──────────────────────────────────────────────────────────────

def _parse_marker(line: str) -> dict | None:
    match = _MARKER.match(line)
    if not match:
        return None
    rest = match.group(2) or ''
    fields = _split_fields(rest[1:] if rest.startswith(':') else rest)
    section = {'type': match.group(1), 'name': _decode(fields[0]) if fields[0].strip() else ''}
    if not isinstance(section['name'], str):
        section['name'] = fields[0].strip()  # e.g. a name like `1929`
    for field in fields[1:]:
        key, sep, value = field.partition(':')
        key = key.strip()
        if not sep or not key:
            continue
        key = next((k for k, alias in _SECTION_ALIASES.items() if alias == key), key)
        section[key] = _decode(value)
    return section


def _section_text(lines: list, last: bool) -> str:
    """A section's Markdown from the lines after its marker: the blank line
    after the marker and the blank line before the next one are layout,
    not content (see `serialize`)."""
    text = '\n'.join(lines)
    if text.startswith('\n'):
        text = text[1:]
    if not last and text.endswith('\n'):
        text = text[:-1]
    return text


def parse(text: str, default_name: str = '') -> dict:
    """The guide entry (without its project-file keys) a file's text holds."""
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    entry = {}
    start = 0
    if lines and lines[0].strip() == '---':
        for index in range(1, len(lines)):
            line = lines[index]
            if line.strip() == '---':
                start = index + 1
                break
            key, sep, value = line.partition(':')
            key = key.strip()
            if sep and key:
                decoded = _decode(value)
                entry[key] = value.strip() if key in _TEXT_KEYS and not isinstance(decoded, str) else decoded
        else:
            start = 0  # no closing line: not a header after all
            entry = {}
    if 'name' not in entry:
        entry = {'name': default_name, **entry}

    sections, current, body = [], None, []
    preamble = []
    for line in lines[start:]:
        marker = _parse_marker(line)
        if marker is not None:
            if current is not None:
                sections.append((current, body))
            current, body = marker, []
            continue
        unescaped = line[1:] if line.startswith('\\') and _ESCAPED_MARKER.match(line) else line
        (body if current is not None else preamble).append(unescaped)
    if current is not None:
        sections.append((current, body))
    if '\n'.join(preamble).strip():
        while preamble and not preamble[0].strip():
            preamble.pop(0)
        sections.insert(0, ({'type': 'blank', 'name': ''}, preamble))

    entry['sections'] = []
    for index, (section, body) in enumerate(sections):
        last = index == len(sections) - 1
        if last and body and body[-1] == '':
            body = body[:-1]  # the file's final line break
        section['markdown'] = _section_text(body, last)
        entry['sections'].append(section)
    return entry
