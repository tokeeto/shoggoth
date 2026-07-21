"""
Loads user-defined Ctrl+Space snippets from a Python file in the user data
directory (root_dir, same folder as shoggoth.json) and merges them into the
built-in snippet tree (ui/text_snippets.py). Loaded after the built-ins, so
user entries win on key-path collisions.

There is no sandboxing: the snippet file is plain Python, exec'd as-is. This
is intentional - see the demo file's docstring.
"""
from pathlib import Path

from shoggoth.files import root_dir
from shoggoth.ui.text_snippets import Branch, CallLeaf

SNIPPET_FILENAME = 'snippets.py'

DEMO_SNIPPET_SOURCE = '''"""
Custom Ctrl+Space snippets for Shoggoth.

Define SNIPPETS as a list of (keys, function) pairs:

  - keys: a tuple of single-character keys, e.g. ("x", "y"). Pressing
    Ctrl+Space then X then Y triggers this entry. If that key path already
    exists in the built-in snippet tree, this overwrites it; unknown paths
    are created as new branches off the root.
  - function: called as function(face, card, project) when the entry is
    reached. face/card/project are the Face/Card/Project currently being
    edited (whichever owns the focused text field) and may be None if that
    can't be determined (e.g. no card is open).

    Return a string to insert it at the cursor, or return None and make
    your own changes to face/card/project directly for snippets that do
    more than insert text.

There is no sandboxing here - these functions run with full Python access,
same as any other code you run. Be as careful with this file as you would
with any other script.

The label shown in the on-screen key reminder comes from the function's
docstring (first line) if it has one, otherwise its name.
"""


def hello_world(face, card, project):
    """Hello world"""
    return "Hello, world! "


SNIPPETS = [
    (("z", "h"), hello_world),
]
'''


def snippet_file_path() -> Path:
    return root_dir / SNIPPET_FILENAME


def ensure_snippet_file() -> Path:
    """Create the snippet file with demo content if it doesn't exist yet."""
    path = snippet_file_path()
    if not path.exists():
        root_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(DEMO_SNIPPET_SOURCE, encoding='utf-8')
    return path


def open_snippet_file():
    """Ensure the snippet file exists, then open it with the OS default handler."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    path = ensure_snippet_file()
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def load_user_snippets():
    """Load (keys, function) pairs from the user snippet file, if present."""
    path = snippet_file_path()
    if not path.exists():
        return []

    source = path.read_text(encoding='utf-8')
    namespace = {}
    try:
        exec(compile(source, str(path), 'exec'), namespace)
    except Exception as exc:
        print(f'Failed to load snippet file {path}: {exc}')
        return []

    result = []
    for entry in namespace.get('SNIPPETS', []):
        try:
            keys, fn = entry
            keys = tuple(k.lower() for k in keys)
            if not keys or not callable(fn):
                raise ValueError('expected (keys, function)')
            result.append((keys, fn))
        except (ValueError, TypeError) as exc:
            print(f'Skipping malformed snippet entry {entry!r}: {exc}')
    return result


def _label_for(fn):
    if fn.__doc__:
        first_line = fn.__doc__.strip().splitlines()[0].strip()
        if first_line:
            return first_line
    name = getattr(fn, '__name__', 'snippet')
    return name.replace('_', ' ').strip().title() or 'Snippet'


def _auto_hint(branch):
    parts = []
    for key, (label, _child) in branch.options.items():
        if label and label[0].lower() == key:
            parts.append(f'[{key.upper()}]{label[1:]}')
        else:
            parts.append(f'[{key.upper()}] {label}')
    return '  '.join(parts)


def merge_snippets(root, snippets):
    """Merge (keys, function) pairs into `root` in place, overwriting any
    existing entries at the same key path and creating branches as needed."""
    touched = {}

    for keys, fn in snippets:
        node = root
        touched.setdefault(id(node), node)
        for key in keys[:-1]:
            existing = node.options.get(key)
            if existing is None or not isinstance(existing[1], Branch):
                child = Branch(title='Custom', hint=None, options={})
                node.options[key] = (key.upper(), child)
            else:
                child = existing[1]
            touched.setdefault(id(child), child)
            node = child

        node.options[keys[-1]] = (_label_for(fn), CallLeaf(fn))

    for branch in touched.values():
        branch.hint = _auto_hint(branch)
