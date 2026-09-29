"""
Modification projects: a file of changes layered on top of another project.

A modification (a translation, an art swap, a template conversion, ...) never
touches the project it modifies -- its *parent*. Its file holds only what
differs from the parent:

    {
        "type": "modification",
        "id": "<this modification's own id>",
        "parent": "<path to the parent project, relative to this file>",
        "project": {<changes to the project's own fields, e.g. name, meta>},
        "cards": {"<card id>": {<changes>}, ...},
        "encounter_sets": {"<set id>": {<changes>}, ...},
        "guides": {"<guide id>": {<changes>}, ...}
    }

Changes are nested dicts mirroring the element's own data: dicts merge key by
key, anything else (strings, numbers, lists) replaces the parent's value
whole, and `null` removes the key. An element change of `null` removes the
element; an element the parent doesn't have is stored whole, marked with
`"$added": true`.

In memory, ModificationProject is an ordinary Project whose `data` is the
parent's data with the changes applied, so every editor, the renderer and the
exporters work on it unchanged. Saving diffs that data against the parent and
writes the difference to the modification's own file -- whatever the author
changed is recorded, whatever they didn't isn't. The parent is loaded
separately, and its writer refuses to write.

The older translation sidecar files ({"language", "project": "<parent>",
"project_name", "cards": {...}, "encounter_sets": {...}, "guides": [...]})
load as modifications too; they're written in the format above on the next
save.
"""
import copy
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from shoggoth.card import Card
from shoggoth.project import Project, _fingerprint
from shoggoth.project_writer import Writer


ELEMENT_KINDS = ('cards', 'encounter_sets', 'guides')
ADDED = '$added'

# Keys of the modification file that belong to the file itself rather than
# describing a change to the parent
_FILE_KEYS = {'type', 'id', 'parent', 'project', *ELEMENT_KINDS}


def is_modification_data(data):
    """Whether a project file's raw JSON is a modification (including the
    older translation sidecar format) rather than a plain project."""
    if not isinstance(data, dict):
        return False
    if data.get('type') == 'modification':
        return True
    # legacy translation sidecar: "project" names the parent file
    return isinstance(data.get('project'), str) and not isinstance(data.get('cards'), list)


# ── Diffing ───────────────────────────────────────────────────────────────

def diff(base, new):
    """The changes that turn dict `base` into dict `new` (see module docstring)."""
    changes = {}
    for key, value in new.items():
        if key not in base:
            changes[key] = copy.deepcopy(value)
        elif value != base[key]:
            if isinstance(value, dict) and isinstance(base[key], dict):
                changes[key] = diff(base[key], value)
            else:
                changes[key] = copy.deepcopy(value)
    for key in base:
        if key not in new:
            changes[key] = None
    return changes


def apply(base, changes):
    """Applies `changes` (as made by `diff`) to dict `base`, in place."""
    for key, value in changes.items():
        if value is None:
            base.pop(key, None)
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            apply(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def element_change(base_element, element):
    """The change to store for one element: its diff, the whole element when
    the parent doesn't have it, `None` when it was removed. Returns the
    sentinel `...` when nothing changed."""
    if element is None:
        return None if base_element is not None else ...
    if base_element is None:
        return {**copy.deepcopy(element), ADDED: True}
    changes = diff(base_element, element)
    return changes if changes else ...


def _project_fields(data):
    """The project's own fields (everything but its elements and id), minus
    unsaved-edit bookkeeping."""
    fields = {key: value for key, value in data.items() if key not in ELEMENT_KINDS and key != 'id'}
    if isinstance(fields.get('meta'), dict):
        fields['meta'] = {key: value for key, value in fields['meta'].items() if key != 'dirty'}
    return fields


def _by_id(elements):
    return {element['id']: element for element in elements or [] if element.get('id')}


# ── Legacy translation sidecars ───────────────────────────────────────────

def _upgrade_legacy(raw):
    """Converts an old translation sidecar to the modification format. Its
    guides (a full list, replacing the parent's) can only be converted once
    the parent is loaded, so they're passed on as '_legacy_guides'."""
    if raw.get('type') == 'modification':
        return raw
    project = {}
    if raw.get('project_name'):
        project['name'] = raw['project_name']
    meta = dict(raw.get('meta') or {})  # the sidecar's own meta (cloud_translation_id)
    if raw.get('language'):
        meta['language'] = raw['language']
    if meta:
        project['meta'] = meta
    upgraded = {
        'type': 'modification',
        'parent': raw['project'],
        'project': project,
        'cards': raw.get('cards') or {},
        'encounter_sets': raw.get('encounter_sets') or {},
        'guides': {},
    }
    if isinstance(raw.get('guides'), list):
        upgraded['_legacy_guides'] = raw['guides']
    return upgraded


class ReadOnlyWriter(Writer):
    """Writer of a modification's parent: it's never written from here."""

    def _refuse(self, *args, **kwargs):
        raise PermissionError(
            f'{self.project.file_path} is the parent of an open modification and is read-only here')

    save_project = save_card = save_all = _write = _refuse


class ModificationWriter(Writer):
    """Writes a modification's changes (never the merged data) to its own file."""

    def save_all(self):
        self.project.clear_dirty()
        self._write(self.project.build_file_data())

    def save_project(self, project):
        self.save_all()

    def save_card(self, card):
        """Saves one card's changes, leaving everything else in the file as it
        was last saved."""
        data = copy.deepcopy(self.project.saved_file_data())
        cards = data.setdefault('cards', {})
        change = self.project.change_for('cards', card.id)
        if change is ...:
            cards.pop(card.id, None)
        else:
            cards[card.id] = change
        self.project.set_dirty(card.id, False)
        self._write(data)

    def _write(self, data):
        super()._write(data)
        self.project._saved_file_data = copy.deepcopy(data)


class ModificationProject(Project):
    """A modification, opened: the parent's data with the changes applied.
    See the module docstring."""

    is_modification = True

    def __init__(self, file_path, raw):
        # Deliberately not Project.__init__: the writer and data come from
        # the parent + changes, not from the file's content directly
        self.file_path = str(file_path)
        self._disk_fingerprint = None
        self._build(raw)
        self.writer = ModificationWriter(self)

    @staticmethod
    def load(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        project = ModificationProject(file_path, raw)
        project._disk_fingerprint = _fingerprint(raw)
        return project

    @staticmethod
    def create(file_path, parent_path, name=None, language=None):
        """Writes a new, empty modification of `parent_path` to `file_path`
        and returns it opened."""
        project_changes = {}
        if name:
            project_changes['name'] = name
        if language:
            project_changes['meta'] = {'language': language}
        raw = {
            'type': 'modification',
            'id': str(uuid4()),
            'parent': _relative_path(parent_path, Path(file_path).parent),
            'project': project_changes,
            'cards': {}, 'encounter_sets': {}, 'guides': {},
        }
        project = ModificationProject(file_path, raw)
        project.save_all()
        return project

    # ── Building the merged data ──────────────────────────────────────────

    def _build(self, raw):
        raw = _upgrade_legacy(raw)
        self.parent_path = os.path.normpath(Path(self.file_path).parent / raw['parent'])
        self._load_parent()

        legacy_guides = raw.pop('_legacy_guides', None)
        if legacy_guides is not None:
            raw['guides'] = self._convert_legacy_guides(legacy_guides)

        self._saved_file_data = copy.deepcopy(raw)
        self._extra = {key: value for key, value in raw.items() if key not in _FILE_KEYS}
        self.id = raw.get('id') or str(uuid4())
        self.data = self._merge(raw)

    def _load_parent(self):
        self.parent = Project.load(self.parent_path)
        self.parent.writer = ReadOnlyWriter(self.parent)
        self._ensure_parent_ids()
        base = copy.deepcopy(self.parent.data)
        base.get('meta', {}).pop('dirty', None)
        self._base = base

    def _ensure_parent_ids(self):
        """Changes are keyed by element id. An element without one (older
        projects' encounter sets) gets an id derived from its name, so it's
        the same on every load -- the parent itself is never saved from here."""
        seed = Path(self.parent_path).name
        for kind in ELEMENT_KINDS:
            seen = {}
            for element in self.parent.data.get(kind, []):
                if element.get('id'):
                    continue
                name = str(element.get('name', ''))
                seen[name] = seen.get(name, 0) + 1
                element['id'] = str(uuid5(NAMESPACE_URL, f'shoggoth:{seed}:{kind}:{name}:{seen[name]}'))

    def _convert_legacy_guides(self, guides):
        """Old translations replaced the parent's guide list outright (guides
        they didn't list were hidden)."""
        base = _by_id(self._base.get('guides'))
        new = _by_id(guides)
        changes = {}
        for guide_id in base.keys() | new.keys():
            change = element_change(base.get(guide_id), new.get(guide_id))
            if change is not ...:
                changes[guide_id] = change
        return changes

    def _merge(self, raw):
        data = copy.deepcopy(self._base)
        apply(data, _project_fields(raw.get('project') or {}))
        data['id'] = self.id
        self._orphans = {}
        for kind in ELEMENT_KINDS:
            changes = raw.get(kind) or {}
            if not changes and kind not in data:
                continue
            elements = data.setdefault(kind, [])
            index = {element.get('id'): i for i, element in enumerate(elements)}
            removed = set()
            for element_id, change in changes.items():
                if change is None:
                    removed.add(element_id)
                elif change.get(ADDED):
                    element = {k: copy.deepcopy(v) for k, v in change.items() if k != ADDED}
                    element['id'] = element_id
                    if element_id in index:
                        elements[index[element_id]] = element
                    else:
                        elements.append(element)
                elif element_id in index:
                    apply(elements[index[element_id]], change)
                else:
                    # The parent no longer has this element: keep the change
                    # (written back untouched) in case it comes back
                    self._orphans.setdefault(kind, {})[element_id] = change
            if removed:
                elements[:] = [element for element in elements if element.get('id') not in removed]
        return data

    # ── Computing what to save ────────────────────────────────────────────

    def change_for(self, kind, element_id):
        """The change to store for one element, or `...` when there is none."""
        base = next((e for e in self._base.get(kind, []) if e.get('id') == element_id), None)
        element = next((e for e in self.data.get(kind, []) if e.get('id') == element_id), None)
        return element_change(base, element)

    def build_file_data(self):
        """The modification file's content for the current in-memory state."""
        data = {
            'type': 'modification',
            'id': self.id,
            'parent': _relative_path(self.parent_path, Path(self.file_path).parent),
            'project': diff(_project_fields(self._base), _project_fields(self.data)),
        }
        for kind in ELEMENT_KINDS:
            base = _by_id(self._base.get(kind))
            new = _by_id(self.data.get(kind))
            changes = dict(self._orphans.get(kind, {}))
            for element_id in [*base, *(i for i in new if i not in base)]:
                change = element_change(base.get(element_id), new.get(element_id))
                if change is not ...:
                    changes[element_id] = change
            data[kind] = changes
        data.update(copy.deepcopy(self._extra))
        return data

    def saved_file_data(self):
        """The file's content as last read or written."""
        return self._saved_file_data

    # ── Project overrides ─────────────────────────────────────────────────

    @property
    def is_cloud_project(self):
        # The parent's cloud ids are in the merged meta, but a modification
        # isn't synced through the cloud folder
        return False

    @property
    def translations(self):
        return {}

    def find_file(self, path):
        """Files next to the modification win (e.g. replacement art), then
        the parent's own resolution."""
        path = Path(path)
        if not path.is_absolute() and (self.folder / path).exists():
            return (self.folder / path).resolve()
        return self.parent.find_file(path)

    def reload(self):
        with open(self.file_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        self._build(raw)
        self._disk_fingerprint = _fingerprint(raw)

    def refresh_parent(self):
        """Re-reads the parent (changed on disk) and reapplies the current
        changes, unsaved ones included."""
        changes = self.build_file_data()
        dirty = list(self.data.get('meta', {}).get('dirty', []))
        self._load_parent()
        self.data = self._merge(changes)
        if dirty:
            self.data.setdefault('meta', {})['dirty'] = dirty

    # ── The originals ─────────────────────────────────────────────────────

    def original_element(self, kind, element_id):
        """The parent's unmodified data for an element (a copy), or None."""
        for element in self._base.get(kind, []):
            if element.get('id') == element_id:
                return copy.deepcopy(element)
        return None

    def original_card(self, card_id):
        """The parent's version of a card, as a detached copy: editing it
        can't reach the parent's data, and the parent can't be saved anyway."""
        data = self.original_element('cards', card_id)
        return Card(data, project=self.parent) if data else None

    @property
    def parent_name(self):
        return self._base.get('name', '')


def _relative_path(path, start):
    try:
        return Path(os.path.relpath(path, start)).as_posix()
    except ValueError:  # different drives on Windows
        return str(Path(path).resolve())
