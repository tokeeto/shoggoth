"""Shoggoth card preview for Sublime Text 4.

Provides the `shoggoth_preview_card` command: place the cursor anywhere inside
a card's JSON block in a Shoggoth project file, run the command, and the card
is rendered via the Shoggoth CLI and shown (front and back) in a scratch tab.

The Shoggoth invocation is configured in Shoggoth.sublime-settings.
"""

import os
import shlex
import shutil
import struct
import subprocess
import tempfile
import threading
from pathlib import Path

import sublime
import sublime_plugin

SETTINGS_FILE = 'Shoggoth.sublime-settings'
STATUS_KEY = 'shoggoth_preview'
PANEL_NAME = 'shoggoth_preview'

# Per-window preview state: window.id() -> {
#   'view_id': int, 'phantoms': PhantomSet, 'temp_dir': str, 'version': int }
_previews = {}


def plugin_unloaded():
    for state in _previews.values():
        _remove_temp_dir(state.get('temp_dir'))
    _previews.clear()


def _remove_temp_dir(path):
    if path and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


# --------------------------------------------------------------------------
# Locating the card at the cursor
#
# A .shoggoth project file is plain JSON. `json.loads` gives no source
# offsets, so a single-pass scanner collects the span and top-level keys of
# every object; the innermost object around the cursor that looks like a card
# (string "id" plus a "front"/"back" key) wins.
# --------------------------------------------------------------------------

_CONTAINER = object()  # marker for keys whose value is an object/array/scalar


def _read_string(text, i):
    """text[i] is an opening quote; return (value, index_after_closing_quote)."""
    n = len(text)
    j = i + 1
    out = []
    while j < n:
        ch = text[j]
        if ch == '\\':
            j += 2
            out.append('')  # escapes never occur in ids; content irrelevant
            continue
        if ch == '"':
            return ''.join(out), j + 1
        out.append(ch)
        j += 1
    return ''.join(out), n


def _scan_objects(text):
    """Yield (start, end, keys) for every JSON object literal in text.

    `keys` maps the object's own top-level keys to their value: the string
    itself for string values, _CONTAINER for anything else.
    """
    results = []
    stack = []  # frames: ['obj'|'arr', start, pending_key, keys_dict]
    i, n = 0, len(text)

    def assign(value):
        if stack and stack[-1][0] == 'obj' and stack[-1][2] is not None:
            stack[-1][3][stack[-1][2]] = value
            stack[-1][2] = None

    while i < n:
        ch = text[i]
        if ch == '"':
            value, i = _read_string(text, i)
            j = i
            while j < n and text[j] in ' \t\r\n':
                j += 1
            if j < n and text[j] == ':' and stack and stack[-1][0] == 'obj':
                stack[-1][2] = value  # this string was a key
                i = j + 1
            else:
                assign(value)
        elif ch == '{':
            assign(_CONTAINER)
            stack.append(['obj', i, None, {}])
            i += 1
        elif ch == '}':
            if stack and stack[-1][0] == 'obj':
                _, start, _, keys = stack.pop()
                results.append((start, i, keys))
            i += 1
        elif ch == '[':
            assign(_CONTAINER)
            stack.append(['arr', i, None, None])
            i += 1
        elif ch == ']':
            if stack and stack[-1][0] == 'arr':
                stack.pop()
            i += 1
        else:
            if ch not in ' \t\r\n,:':
                assign(_CONTAINER)  # number / true / false / null
            i += 1
    return results


def find_card_id(text, pos):
    """Return the id of the innermost card object containing offset `pos`."""
    enclosing = [(s, e, k) for s, e, k in _scan_objects(text) if s <= pos <= e]
    enclosing.sort(key=lambda t: t[1] - t[0])
    for _, _, keys in enclosing:
        if ('front' in keys or 'back' in keys) and isinstance(keys.get('id'), str):
            return keys['id']
    # Fallback for cards missing faces; project root and encounter sets both
    # carry a "cards" key, so this can't accidentally pick them.
    for _, _, keys in enclosing:
        if isinstance(keys.get('id'), str) and 'cards' not in keys \
                and 'encounter_sets' not in keys:
            return keys['id']
    return None


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _build_command(settings, project_file, card_id, out_dir):
    base = settings.get('command', ['uv', 'run', 'shoggoth'])
    if isinstance(base, str):
        base = shlex.split(base)
    cmd = list(base)
    cmd += settings.get('extra_args', [])
    cmd += ['-r', project_file, '-id', card_id, '-o', out_dir,
            '-f', 'png', '-s', str(settings.get('render_size', 1))]
    if settings.get('bleed', False):
        cmd += ['-b', '1']
    return cmd


def _png_size(path):
    try:
        with open(path, 'rb') as f:
            head = f.read(24)
        if head[:8] == b'\x89PNG\r\n\x1a\n' and head[12:16] == b'IHDR':
            return struct.unpack('>II', head[16:24])
    except OSError:
        pass
    return None


def _face_sort_key(path):
    name = os.path.basename(path)
    return (0 if '_front_' in name else 1, name)


class ShoggothPreviewCardCommand(sublime_plugin.TextCommand):
    """Render the card under the cursor and show it in a preview tab."""

    def is_enabled(self):
        name = self.view.file_name() or ''
        return name.endswith(('.json', '.shoggoth'))

    def run(self, edit):
        view = self.view
        window = view.window()
        project_file = view.file_name()
        if not project_file:
            sublime.status_message('Shoggoth: save the project file first')
            return

        settings = sublime.load_settings(SETTINGS_FILE)
        if view.is_dirty() and settings.get('save_on_render', True):
            view.run_command('save')

        pos = view.sel()[0].begin() if view.sel() else 0
        card_id = find_card_id(view.substr(sublime.Region(0, view.size())), pos)
        if not card_id:
            sublime.status_message('Shoggoth: no card found at cursor')
            return

        state = _previews.setdefault(window.id(), {'version': 0})
        state['version'] += 1
        version = state['version']

        view.set_status(STATUS_KEY, 'Shoggoth: rendering {}…'.format(card_id[:8]))
        threading.Thread(
            target=self._render,
            args=(window, view, settings, project_file, card_id, version),
            daemon=True,
        ).start()

    # -- background thread ------------------------------------------------

    def _render(self, window, view, settings, project_file, card_id, version):
        out_dir = tempfile.mkdtemp(prefix='shoggoth-preview-')
        cmd = _build_command(settings, project_file, card_id, out_dir)

        cwd = settings.get('working_dir') or os.path.dirname(project_file)
        cwd = os.path.expanduser(cwd)
        env = os.environ.copy()
        env.update({k: str(v) for k, v in (settings.get('env') or {}).items()})

        try:
            proc = subprocess.run(
                cmd, cwd=cwd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=settings.get('timeout', 120),
            )
            error = None
        except (OSError, subprocess.TimeoutExpired) as exc:
            proc, error = None, str(exc)

        images = sorted(
            (os.path.join(out_dir, f) for f in os.listdir(out_dir)
             if f.lower().endswith('.png')),
            key=_face_sort_key,
        ) if os.path.isdir(out_dir) else []

        def finish():
            view.erase_status(STATUS_KEY)
            state = _previews.get(window.id())
            if state is None or state['version'] != version:
                _remove_temp_dir(out_dir)  # a newer render superseded this one
                return
            if error or not images:
                _remove_temp_dir(out_dir)
                self._show_error(window, cmd, proc, error)
                return
            old_dir = state.get('temp_dir')
            state['temp_dir'] = out_dir
            self._show_images(window, state, card_id, images,
                              sublime.load_settings(SETTINGS_FILE))
            _remove_temp_dir(old_dir)

        sublime.set_timeout(finish, 0)

    # -- main thread -------------------------------------------------------

    def _show_error(self, window, cmd, proc, error):
        lines = ['Shoggoth render failed.', '', '$ ' + ' '.join(cmd), '']
        if error:
            lines.append(error)
        elif proc is not None:
            lines.append('exit code: {}'.format(proc.returncode))
            for label, data in (('stdout', proc.stdout), ('stderr', proc.stderr)):
                text = (data or b'').decode('utf-8', 'replace').strip()
                if text:
                    lines += ['', '--- {} ---'.format(label), text]
            if proc.returncode == 0:
                lines += ['', 'No images were produced — check that the card id '
                                'exists in the project file.']
        panel = window.create_output_panel(PANEL_NAME)
        panel.run_command('append', {'characters': '\n'.join(lines) + '\n'})
        window.run_command('show_panel', {'panel': 'output.' + PANEL_NAME})
        sublime.status_message('Shoggoth: render failed')

    def _get_preview_view(self, window, state):
        view_id = state.get('view_id')
        for v in window.views():
            if v.id() == view_id:
                return v
        # (Re)create the preview tab, ideally in another group, and hand
        # focus straight back to the editor.
        active = window.active_view()
        if window.num_groups() > 1:
            window.focus_group((window.active_group() + 1) % window.num_groups())
        preview = window.new_file()
        preview.set_name('Shoggoth Card')
        preview.set_scratch(True)
        preview.settings().set('word_wrap', False)
        state['view_id'] = preview.id()
        state['phantoms'] = sublime.PhantomSet(preview, 'shoggoth_preview')
        if active is not None:
            window.focus_view(active)
        return preview

    def _show_images(self, window, state, card_id, images, settings):
        preview = self._get_preview_view(window, state)
        width = int(settings.get('image_width', 420))

        parts = ['<body id="shoggoth-card-preview">']
        for path in images:
            dims = _png_size(path)
            if dims and dims[0]:
                w = min(width, dims[0])
                h = round(dims[1] * w / dims[0])
                size_attr = ' width="{}" height="{}"'.format(w, h)
            else:
                size_attr = ' width="{}"'.format(width)
            parts.append('<div><img src="{}"{}></div>'.format(
                Path(path).as_uri(), size_attr))
        parts.append('</body>')

        phantoms = state.get('phantoms')
        if phantoms is None or phantoms.view.id() != preview.id():
            phantoms = sublime.PhantomSet(preview, 'shoggoth_preview')
            state['phantoms'] = phantoms
        phantoms.update([sublime.Phantom(
            sublime.Region(0, 0), ''.join(parts), sublime.LAYOUT_INLINE)])
        preview.set_name('Shoggoth Card')
        sublime.status_message('Shoggoth: rendered {} face(s)'.format(len(images)))
