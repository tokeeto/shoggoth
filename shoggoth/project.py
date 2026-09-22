import hashlib
import json
import re
import time
from uuid import uuid4
from pathlib import Path
from itertools import combinations

import shoggoth
from shoggoth.card import TEMPLATES, Card
from shoggoth.encounter_set import EncounterSet, parse_number_span
from shoggoth.export_profile import ExportProfile
from shoggoth.guide import Guide
from shoggoth.i18n import tr
from shoggoth.project_writer import CloudWriter, Writer, TranslationWriter


type_order = {
    "scenario": 0,
    "chaos": 1,
    "agenda": 2,
    "act": 3,
    "location": 4,
    "story": 5,
    "key": 6,
    "treachery": 7,
    "enemy": 8,
    # "story": 9,
    "investigator": 10,
    "other": 11
}

class_order = {
    "guardian": 0,
    "seeker": 1,
    "rogue": 2,
    "mystic": 3,
    "survivor": 4,
    "multi": 5,
    "neutral": 6,
    "basic weakness": 7
}
multi_class_order = {
    frozenset(combo): i
    for i, combo in enumerate(
        combo for r in (2, 3) for combo in combinations(['guardian', 'seeker', 'rogue', 'mystic', 'survivor'], r)
    )
    # This generates the 20 combinations of two-class and three-class cards, and sorts them as normal for classes
    # The three-class sorting in EotE is a bit weird, and I don't know what to make of it
}

def class_sort_key(card):
    cls = card.get_class()
    if cls == 'multi':
        classes = frozenset(card.front.get('classes', []))
        return f'5_{multi_class_order.get(classes, 99):02d}'
    return str(class_order.get(cls, 15))

player_type_order = {
    "asset": 0,
    "event": 1,
    "skill": 2,
}


def sort_cards(cards):
    # Separate the linked and bonded cards
    linked, bonded, rest = [], [], []
    for card in cards:
        if card.get('meta', {}).get('investigator', card.get('investigator')):
            #TODO ^ This can be cleaned up once meta tags are implemented (assuming the linking will be a part of the meta tags)
            linked.append(card)
        elif card.get('meta', {}).get('bonded', card.get('bonded')):
            bonded.append(card)
        else:
            rest.append(card)

    # Sort cards normally
    rest.sort(key=lambda card: (
        not card.get('meta', {}).get('sorting', card.get('sorting', True)), # check if the card has sorting disabled, if it does - skip it. It will be placed at the end of the list
        #TODO ^ This can be cleaned up once meta tags are implemented
        type_order.get(card.front['type'], 15),
        str(card.front.get('index', 15)),
        class_sort_key(card), # helper to sort the cards within the multi-colored segment if there are any, otherwise defaults to what was here before
        str(card.front.get('level', 15)),
        str(player_type_order.get(card.front['type'], 15)), 
        str(card.name),
    ))

    # Group the linked cards
    linked_groups = {}
    for card in linked:
        key = card.get('investigator')
        linked_groups.setdefault(key, []).append(card)

    # Sort within the group in case of an investigator with multiple signatures
    for group in linked_groups.values():
        group.sort(key=lambda card: (
            0 if card.front.get('type') == 'investigator' else
            2 if card.get_class() == 'weakness' else 1,
            player_type_order.get(card.front.get('type', ''), 15),
            card.name,
        ))

    # Sort groups by class (checking the class of the investigator)
    def group_key(group):
        inv = next((c for c in group if c.front.get('type') == 'investigator'), group[0])
        return class_order.get(inv.get_class(), 15)
    
    sorted_linked_groups = sorted(linked_groups.values(), key=group_key)

    # Group bonded cards together by the first ID of their parent
    bonded_groups = {}
    for card in bonded:
        bonded_val = card.get('meta', {}).get('bonded', card.get('bonded'))
        first_id = bonded_val[0] if isinstance(bonded_val, list) else bonded_val
        bonded_groups.setdefault(first_id, []).append(card)

    for group in bonded_groups.values():
        group.sort(key=lambda c: c.name)

    # Reassemble the linked cards and the rest
    sorted_main = [c for group in sorted_linked_groups for c in group] + rest

    # Add bonded cards after their first indicated parent
    result = []
    for card in sorted_main:
        result.append(card)
        if card.get('id') in bonded_groups:
            result.extend(bonded_groups[card.get('id')])

    cards[:] = result


# Beta-era, one-shot data fixup: old projects stored the collection footer as
# a single free-text field (an optional "<n>/<n>" set-total, whitespace, then
# icon markup and card number joined by triple-space padding). Newer defaults
# render those as three independent fields, so on load we offer to split any
# leftover legacy "collection" strings into them.
_LEGACY_COLLECTION_TOTAL_RE = re.compile(r'^(\d+/\d+)\s+')


def parse_legacy_collection(value):
    """ Split a legacy 'collection' string into collection_total (optional),
        collection_icon and collection_number.
    """
    result = {}
    remainder = value
    total_match = _LEGACY_COLLECTION_TOTAL_RE.match(remainder)
    if total_match:
        result['collection_total'] = total_match.group(1)
        remainder = remainder[total_match.end():]
    icon, _, number = remainder.strip().partition('   ')
    result['collection_icon'] = icon.strip()
    result['collection_number'] = number.strip()
    return result


def _dicts_with_legacy_collection(node):
    """ Recursively yield every dict within *node* that has a legacy string 'collection' field. """
    if isinstance(node, dict):
        if isinstance(node.get('collection'), str):
            yield node
        for value in node.values():
            yield from _dicts_with_legacy_collection(value)
    elif isinstance(node, list):
        for item in node:
            yield from _dicts_with_legacy_collection(item)


def has_legacy_collection_fields(data):
    """ Whether a project's raw JSON *data* still has any legacy 'collection' fields. """
    return any(True for _ in _dicts_with_legacy_collection(data))


def migrate_legacy_collection_fields(data):
    """ Split every legacy 'collection' field in a project's raw JSON *data*
        into collection_total/collection_icon/collection_number, in place.
        Returns the number of fields migrated.
    """
    targets = list(_dicts_with_legacy_collection(data))
    for node in targets:
        value = node.pop('collection')
        node.update(parse_legacy_collection(value))
    return len(targets)


def _fingerprint(data):
    """ Hash of the parts of a project's raw JSON *data* that matter to the
        user. Comparing parsed data (rather than file bytes or mtimes) makes
        formatting, key order and a plain `touch` irrelevant, and `meta.dirty`
        is bookkeeping of unsaved edits, not content of the file.
    """
    content = {key: value for key, value in data.items() if key != 'meta'}
    meta = {key: value for key, value in (data.get('meta') or {}).items() if key != 'dirty'}
    if meta:
        content['meta'] = meta
    text = json.dumps(content, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class Project:
    """ Class to handle project files

        Projects are ultimately just representations of json files.
    """

    # Observers of element changes -- see add_change_listener. Class-level
    # (not per-instance) so the UI registers once and hears about every open
    # project, instead of being wired up project by project.
    _change_listeners = []

    def __init__(self, file_path, data):
        self.file_path = file_path
        self.data = data
        if 'id' not in self.data:
            self.data['id'] = str(uuid4())
        self.id = data['id']
        self.writer = CloudWriter(self) if self.is_cloud_project else Writer(self)
        # Fingerprint of what the file on disk held when we last read or wrote
        # it (None: unknown, e.g. a project that hasn't been saved yet).
        self._disk_fingerprint = None

    @classmethod
    def add_change_listener(cls, callback):
        """ Registers `callback(project, kind, element_id, changed)`, called
            whenever an element's dirty state is set: `changed` is True for an
            edit, False once it's saved. `kind` is 'project', 'cards',
            'encounter_sets' or 'guides'. This is how the model tells the UI
            (preview, tree) and the cloud sync that something changed, without
            model code ever reaching into `shoggoth.app` itself.
        """
        cls._change_listeners.append(callback)

    def _locate(self, element_id):
        """ Returns (kind, element dict) for an id, or (None, None). The
            project itself is ('project', self.data). """
        if element_id == self.id:
            return 'project', self.data
        for kind in ('cards', 'encounter_sets', 'guides'):
            for entry in self.data.get(kind, []):
                if entry.get('id') == element_id:
                    return kind, entry
        return None, None

    @property
    def is_cloud_project(self):
        return bool(self.data.get('meta', {}).get('celaeno_id'))

    def stamp(self, element):
        """ Records "last edited now" in an element's meta -- the timestamp
            cloud sync compares to decide which side changed (see
            shoggoth.cloud.merge). Only cloud projects carry timestamps, so
            ordinary local project files aren't touched. """
        if self.is_cloud_project:
            element.setdefault('meta', {})['modified'] = time.time()

    def note_deleted(self, kind, element_id):
        """ Remembers that an element was removed, so cloud sync can tell
            "deleted here" from "never existed here". No-op for local projects. """
        if self.is_cloud_project:
            deleted = self.data['meta'].setdefault('celaeno_deleted', {})
            deleted[element_id] = {'kind': kind, 'at': time.time()}
            for listener in self._change_listeners:
                listener(self, kind, element_id, True)

    @property
    def dirty(self):
        return bool(self.data.get('meta', {}).get('dirty', []))

    @dirty.setter
    def dirty(self, value):
        self.set_dirty(self.id, value)

    @property
    def icon(self):
        return self.data.get('icon', '')

    @icon.setter
    def icon(self, value):
        self.dirty = value != self.data['icon']
        self.data['icon'] = value

    @property
    def auto_hyphenate(self):
        return self.data.get('meta', {}).get('auto_hyphenate', False)

    @auto_hyphenate.setter
    def auto_hyphenate(self, value):
        if 'meta' not in self.data:
            self.data['meta'] = {}
        self.data['meta']['auto_hyphenate'] = value
        self.dirty = True

    @property
    def french_punctuation(self):
        return self.data.get('meta', {}).get('french_punctuation', False)

    @french_punctuation.setter
    def french_punctuation(self, value):
        if 'meta' not in self.data:
            self.data['meta'] = {}
        self.data['meta']['french_punctuation'] = value
        self.dirty = True

    @property
    def language(self):
        """ Card rendering language override for this project.
        """
        return self.data.get('meta', {}).get('language', '')

    @language.setter
    def language(self, value):
        if 'meta' not in self.data:
            self.data['meta'] = {}
        self.data['meta']['language'] = value
        self.dirty = True

    def get_meta(self, key, default=None):
        """ Reads a designer-facing metadata field (author/banner_url/website_url/
            tags/status/description/...), stored under data['meta'] rather than
            as a top-level key.
        """
        return self.data.get('meta', {}).get(key, default)

    def set_meta(self, key, value):
        meta = self.data.setdefault('meta', {})
        if meta.get(key) != value:
            self.dirty = True
        if value is None:
            meta.pop(key, None)
        else:
            meta[key] = value

    @property
    def folder(self):
        return Path(self.file_path).parent

    def find_file(self, path):
        path = Path(path)
        if path.exists():
            return path.resolve()
        if (self.folder / path).exists():
            return (self.folder / path).resolve()
        return None

    def __eq__(self, other):
        if not isinstance(other, Project):
            return NotImplemented  # e.g. `window.active_project == project` with no active project
        return self.data == other.data

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def is_translation(self):
        """Whether this project is a translation for another project."""
        return bool(getattr(self, '_translation', None) or self.data.get('project'))

    @property
    def translations(self):
        """Return a dict of {language: Translation} for all registered translations."""
        result = {}
        for lang, rel_path in self.data.get('translations', {}).items():
            full_path = self.folder / rel_path
            result[lang] = full_path
        return result

    def add_translation(self, language, file_path):
        """Register a translation file. *file_path* may be absolute or relative."""
        rel = Path(file_path).relative_to(self.folder) if Path(file_path).is_absolute() else Path(file_path)
        if 'translations' not in self.data:
            self.data['translations'] = {}
        self.data['translations'][language] = str(rel)
        self.dirty = True

    def save_all(self):
        self.writer.save_all()

    def save(self):
        # self.writer.save_project(self)
        self.writer.save_all()

    def get_card(self, id):
        for entry in self.data.get('cards', []):
            if entry.get('id') == id:
                return Card(entry, project=self)

    @property
    def guides(self):
        result = []
        for entry in self.data.get('guides', []):
            result.append(Guide(entry, self))
        return result

    @property
    def export_profiles(self):
        """ExportProfile wrappers for this project's saved export setups.

        Note: these wrap the *live* dicts in self.data, so callers that want
        to edit-without-persisting (see ProjectExportDialog) must deep-copy
        `.data` themselves rather than mutate through these wrappers.
        """
        return [ExportProfile(entry, self) for entry in self.data.get('export_profiles', [])]

    @property
    def name(self):
        return self.data['name']

    @property
    def cards(self):
        c = [Card(card, project=self) for card in self.data.get('cards', [])]
        sort_cards(c)
        return c

    @property
    def player_cards(self):
        c = [Card(card, project=self) for card in self.data.get('cards', []) if not card.get('encounter_set')]
        sort_cards(c)
        return c

    @property
    def encounter_sets(self):
        # order sets to always come out right
        self.data['encounter_sets'].sort(key=lambda x: (
            x.get('order', 999),
            x.get('name'),
        ))

        for e in self.data['encounter_sets']:
            yield EncounterSet(e, project=self)

    def get_encounter_set(self, id):
        for es in self.encounter_sets:
            if es.id == id:
                return es
        return None

    @property
    def scenario_names(self):
        """ Property for guide creation.
            Scenarios are encounter sets with ordering.
        """
        scenarios = [n for n in self.encounter_sets if n.get('order') != None]
        names = [f'"{n.name}"' for n in scenarios]
        if not names:
            return ''
        if len(names) < 2:
            return names[0]
        return ', '.join(names[:-1]) + ' and ' + names[-1]

    @property
    def number_of_scenarios(self):
        """ Property for guide creation.
            Scenarios are encounter sets with ordering.
        """
        scenarios = [n for n in self.encounter_sets if n.get('order') != None]
        return len(scenarios)

    def get_guide(self, id):
        for guide in self.guides:
            if guide.id == id:
                return guide
        return None

    def get_by_id(self, id):
        if self.id == id:
            return self
        return self.get_guide(id) or self.get_encounter_set(id) or self.get_card(id)

    def assign_card_numbers(self):
        encounter_sets = list(self.encounter_sets)
        player_cards = list(self.player_cards)

        manual_numbers = set()
        for encounter_set in encounter_sets:
            for card in encounter_set.cards:
                if card.get('enumerated') == 'manual':
                    manual_numbers |= parse_number_span(card.project_number)
        for card in player_cards:
            if card.get('enumerated') == 'manual':
                manual_numbers |= parse_number_span(card.project_number)

        current_number = 1
        for encounter_set in encounter_sets:
            encounter_set.assign_card_numbers()
            for card in encounter_set.cards:
                enumerated = card.get('enumerated')
                if enumerated in ('ignored', 'manual'):
                    continue
                while current_number in manual_numbers:
                    current_number += 1
                card.project_number = current_number
                current_number += 1
        for card in player_cards:
            enumerated = card.get('enumerated')
            if enumerated in ('ignored', 'manual'):
                continue
            while current_number in manual_numbers:
                current_number += 1
            card.project_number = current_number
            current_number += 1

    def add_card(self, card):
        if 'cards' not in self.data:
            self.data['cards'] = []
        if isinstance(card, Card):
            self.data['cards'].append(card.data)
        else:
            self.data['cards'].append(card)

        if not card.get('copyright') and 'default_copyright' in self.data:
            if isinstance(card, Card):
                card.set('copyright', self.data['default_copyright'])
            else:
                card['copyright'] = self.data['default_copyright']
        self.dirty = True
        card_id = card.id if isinstance(card, Card) else card.get('id')
        if card_id:
            self.set_dirty(card_id)

    def get_all_cards(self):
        return self.cards

    def has_unsaved_changes(self):
        """Check whether any card (or card face) or encounter set has unsaved edits"""
        for card in self.get_all_cards():
            if getattr(card, 'dirty', False):
                return True
            for face in (getattr(card, 'front', None), getattr(card, 'back', None)):
                if face is not None and getattr(face, 'dirty', False):
                    return True
        for encounter_set in self.encounter_sets:
            if encounter_set.dirty:
                return True
        return False

    def set_dirty(self, id, value=True):
        if 'meta' not in self.data:
            self.data['meta'] = {}
        if 'dirty' not in self.data['meta']:
            self.data['meta']['dirty'] = []
        if value and id not in self.data['meta']['dirty']:
            self.data['meta']['dirty'].append(id)
        elif not value and id in self.data['meta']['dirty']:
            self.data['meta']['dirty'].remove(id)

        kind, element = self._locate(id)
        if kind is None:
            return  # e.g. a card whose fresh id isn't in the project yet
        if value:
            self.stamp(element)
        for listener in self._change_listeners:
            listener(self, kind, id, bool(value))

    def clear_dirty(self):
        if 'meta' not in self.data:
            self.data['meta'] = {}
        self.data['meta']['dirty'] = []

    def is_dirty(self, id):
        return id in self.data.get('meta', {}).get('dirty', [])

    @staticmethod
    def _read(file_path):
        """Reads and validates a project file, returning its raw data."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(e)
            raise

        for entry in data["encounter_sets"]:
            try:
                assert EncounterSet.is_valid(entry)
            except AssertionError:
                print('Entry failed assertion, project is invalid: ', entry)
                raise Exception('Invalid project file.')
        return data

    @staticmethod
    def load(file_path):
        """Load card data from JSON file"""
        data = Project._read(file_path)
        fingerprint = _fingerprint(data)  # before __init__ adds a missing id
        project = Project(file_path, data)
        project._disk_fingerprint = fingerprint
        return project

    # ── The project file on disk ──────────────────────────────────────────

    @property
    def is_file_backed(self):
        """Whether this project is a plain .shoggoth file that is ours to
        watch and to move. Translations persist to a sidecar file instead, and
        cloud projects live in (and are synced through) the cloud folder."""
        return not self.is_translation and not self.is_cloud_project

    def remember_saved(self, data):
        """Records that the file now holds *data* (what the writer just wrote),
        so our own saves are never mistaken for outside changes."""
        self._disk_fingerprint = _fingerprint(data)

    def has_external_changes(self):
        """Whether the file's content has changed since we last read or wrote
        it -- i.e. someone else edited it. Formatting and metadata-only
        changes don't count (see `_fingerprint`).

        Compared against the last-known state of the file rather than against
        the in-memory data: with unsaved edits the two always differ, which
        would flag every project that is merely being worked on. A missing or
        half-written (unparseable) file isn't reported either: another change
        event follows once the writer is done, and saving recreates the file.
        """
        if self._disk_fingerprint is None:
            return False
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return False
        return isinstance(data, dict) and _fingerprint(data) != self._disk_fingerprint

    def acknowledge_external_changes(self):
        """Accepts the file's current content as the baseline, so it stops
        being reported until it changes again (the user chose to keep their
        version; their next save overwrites the file)."""
        with open(self.file_path, 'r', encoding='utf-8') as f:
            self._disk_fingerprint = _fingerprint(json.load(f))

    def reload(self):
        """Replaces the in-memory project with the file's content, discarding
        unsaved changes. The Project object stays the same (the UI holds on to
        it); anything holding cards/faces from before must be rebuilt."""
        data = self._read(self.file_path)
        fingerprint = _fingerprint(data)
        if 'id' not in data:
            data['id'] = self.id
        self.data = data
        self.id = data['id']
        self._disk_fingerprint = fingerprint

    def save_as(self, file_path):
        """Points the project at a new file and writes it there; the old file
        is left as it is."""
        old_path = self.file_path
        self.file_path = str(file_path)
        try:
            self.save_all()
        except Exception:
            self.file_path = old_path
            raise

    def add_encounter_set(self, name):
        if 'encounter_sets' not in self.data:
            self.data['encounter_sets'] = []
        for enc in self.data['encounter_sets']:
            if enc['name'] == name:
                raise Exception('duplicate encounter set name')

        encounter_data = {
            'name': name,
            'icon': '',
            'cards': [],
        }
        self.data['encounter_sets'].append(encounter_data)
        shoggoth.app.refresh_tree()
        self.dirty = True
        encounter_set = EncounterSet(encounter_data, project=self)
        self.set_dirty(encounter_set.id)
        return encounter_set

    def remove_encounter_set(self, index):
        removed = self.data['encounter_sets'].pop(index)
        self.note_deleted('encounter_sets', removed.get('id'))

    def gather_images(self, update=False):
        """ Walks through the project and copies to all relevant images to a nearby folder for easier distribution.
            Also updates all used paths to point to the new images using a relative path.
        """
        import shutil
        import os

        image_paths = {}  # old path string -> new relative path string
        output_folder = self.folder / f'{self.name} images'
        output_folder.mkdir(exist_ok=True)

        def copy_image(path_str):
            if not path_str:
                return path_str
            if path_str in image_paths:
                return image_paths[path_str]

            resolved = self.find_file(path_str)
            if not resolved:
                return path_str

            try:
                resolved.relative_to(output_folder)
                image_paths[path_str] = str(resolved.relative_to(self.folder))
                return image_paths[path_str]
            except ValueError:
                pass

            dest_path = output_folder / resolved.name
            counter = 1
            while dest_path.exists() and dest_path.resolve() != resolved:
                dest_path = output_folder / f'{resolved.stem}_{counter}{resolved.suffix}'
                counter += 1

            if not dest_path.exists():
                shutil.copy2(resolved, dest_path)

            image_paths[path_str] = str(dest_path.relative_to(self.folder))
            return image_paths[path_str]

        if self.icon:
            if update:
                self.data['icon'] = copy_image(self.icon)
            else:
                copy_image(self.icon)

        for encounter_set in self.encounter_sets:
            if encounter_set.icon:
                if update:
                    encounter_set.data['icon'] = copy_image(encounter_set.icon)
                else:
                    copy_image(encounter_set.icon)

        for card in self.cards:
            for side in (card.front, card.back):
                for key in ('illustration', 'image1', 'image2', 'image3', 'image4', 'image5'):
                    image = side.data.get(key)
                    if image:
                        # check for things already in the subfolder
                        path = os.path.realpath(image)
                        relative = os.path.relpath(path, output_folder)

                        if relative.startswith(os.pardir):
                            # already inside the folder
                            continue

                        if update:
                            side.data[key] = copy_image(image)
                        else:
                            copy_image(image)

    @staticmethod
    def new(name, code, icon):
        """ Returns the base data for a new Project """
        return {
            'name': name,
            'code': code,
            'icon': icon,
            'encounter_sets': [],
            'cards': [],
        }

    def add_guide(self, name='Guide', file_location=None):
        if 'guides' not in self.data:
            self.data['guides'] = []
        guide_id = str(uuid4())
        self.data['guides'].append({
            'id': guide_id,
            'name': name,
            'sections': [],
        })
        self.set_dirty(guide_id)
        shoggoth.app.refresh_tree()

    def add_investigator_set(self, name):
        """ Creates a few cards usually needed for an investigator """
        investigator = TEMPLATES.INVESTIGATOR()
        investigator['name'] = name
        investigator['investigator'] = name
        signature = TEMPLATES.ASSET()
        signature['name'] = 'Signature'
        signature['front']['text'] = f'<:{investigator["id"]} name> deck only.'
        signature['investigator'] = name
        weakness = TEMPLATES.TREACHERY_WEAKNESS()
        weakness['name'] = 'Weakness'
        weakness['back']['type'] = 'player'
        weakness['investigator'] = name
        mini = TEMPLATES.MINI_INVESTIGATOR()
        mini['name'] = f'mini {name}'
        mini['investigator'] = name
        mini['investigator_id'] = investigator["id"]

        investigator['back']['entries'][3][1] = f"<:{signature['id']} name>, <:{weakness['id']} name>, 1 random basic weakness."

        self.add_card(investigator)
        self.add_card(signature)
        self.add_card(weakness)
        self.add_card(mini)
        shoggoth.app.refresh_tree()
        shoggoth.app.goto_card(investigator['id'])

    def create_scenario(self, name, order=None):
        """ Creates an encounter set
            including acts, agendas, and other
            placeholder cards.
        """
        cards = []
        for x in range(1, 4):
            act = TEMPLATES.ACT()
            act['front']['index'] = f'{x}a'
            act['back']['index'] = f'{x}b'
            act['name'] = f'Act {x}'
            cards.append(act)

            agenda = TEMPLATES.AGENDA()
            agenda['front']['index'] = f'{x}a'
            agenda['back']['index'] = f'{x}b'
            agenda['name'] = f'Agenda {x}'
            cards.append(agenda)

        for x in range(0,3):
            enemy = TEMPLATES.ENEMY()
            enemy['name'] = f'Enemy {x+1}'
            enemy['amount'] = 3
            cards.append(enemy)

        for x in range(0, 7):
            treachery = TEMPLATES.TREACHERY()
            treachery['name'] = f'Treachery {x+1}'
            treachery['amount'] = 3
            cards.append(treachery)

        for x in range(0, 8):
            location = TEMPLATES.LOCATION()
            location['name'] = f'Location {x+1} - minimum size'
            location['amount'] = 1
            cards.append(location)

        for x in range(0, 4):
            location = TEMPLATES.LOCATION()
            location['name'] = f'Location {x+9} - medium size'
            location['amount'] = 1
            cards.append(location)

        for x in range(0, 4):
            location = TEMPLATES.LOCATION()
            location['name'] = f'Location {x+13} - large size'
            location['amount'] = 1
            cards.append(location)

        encounter_set = self.add_encounter_set(name)
        if order:
            encounter_set.data['order'] = order
        for card in cards:
            card['encounter_set'] = encounter_set.id
            self.add_card(card)
        shoggoth.app.refresh_tree()

    def create_campaign(self):
        """ Creates 8 placeholder scenarios. """
        scenario_names = [
            'Introduction',
            'The Call',
            'Learning',
            'Threshold',
            'Acceptance',
            'The Test',
            'Revelation',
            'Climax'
        ]
        for index, name in enumerate(scenario_names):
            self.create_scenario(name, order=index+1)

    def create_player_project(self):
        """ Creates a set of placeholder cards
            aligning with the usual distribution of cards
            in an investigator project.

            An investigator project usually has around:
                ~130 unique cards in an project.
                5 investigators
                50 level 0
                50 level 1-5
                25 bound/other (10-15 signature cards for instance)

            This method creates, for each class + neutral:
                9 level 0 cards
                9 level 1-5 cards
                3 investigator related cards
            for a total of 126 cards.
        """

        cards = []
        for class_name in ('guardian', 'rogue', 'seeker', 'mystic', 'survivor', 'neutral'):
            if class_name != 'neutral':
                self.add_investigator_set(f'The {class_name.capitalize()}')
            # Level 0 cards
            for n in range(4):
                asset = TEMPLATES.ASSET()
                asset['front']['classes'] = [class_name]
                asset['front']['level'] = 0
                asset['name'] = f'{class_name} asset {n+1}'
                cards.append(asset)
            for n in range(3):
                event = TEMPLATES.EVENT()
                event['front']['classes'] = [class_name]
                event['front']['level'] = 0
                event['name'] = f'{class_name} event {n+1}'
                cards.append(event)
            for n in range(2):
                skill = TEMPLATES.SKILL()
                skill['front']['classes'] = [class_name]
                skill['front']['level'] = 0
                skill['name'] = f'{class_name} skill {n+1}'
                cards.append(skill)

            # Level 1-5 cards
            for n in range(4):
                asset = TEMPLATES.ASSET()
                asset['front']['classes'] = [class_name]
                asset['front']['level'] = n+2
                asset['name'] = f'{class_name} xp asset {n+1}'
                cards.append(asset)
            for n in range(3):
                event = TEMPLATES.EVENT()
                event['front']['classes'] = [class_name]
                event['front']['level'] = n+2
                event['name'] = f'{class_name} xp event {n+1}'
                cards.append(event)
            for n in range(2):
                skill = TEMPLATES.SKILL()
                skill['front']['classes'] = [class_name]
                skill['front']['level'] = n+1
                skill['name'] = f'{class_name} xp skill {n+1}'
                cards.append(skill)

        for card in cards:
            self.add_card(card)
        shoggoth.app.refresh_tree()


def update(d, u):
    import collections.abc
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


class Translation:
    """ A translated version of a project.
        Only really supports work and changes to the translation of
        the project. Any changes to cards should happen in the Project
        itself.
    """

    def __init__(self, file_path, data):
        self.file_path = str(file_path)
        self.data = data
        if 'language' not in self.data:
            raise Exception(tr("ERROR_TRANSLATION_MISSING_LANGUAGE"))
        self.language = data['language']
        if 'project' not in self.data:
            raise Exception(tr("ERROR_TRANSLATION_MISSING_PROJECT"))
        self.project_path = Path(self.file_path).parent / Path(data['project'])
        self.project = Project.load(self.project_path)
        self.apply()

    @classmethod
    def load(cls, file_path):
        """Load data from JSON file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(file_path, data)

    def get_meta(self, key, default=None):
        """Designer-facing metadata for this translation itself (currently
        just `cloud_translation_id`) -- stored under the sidecar's own
        data['meta'], separate from the overlaid project's own meta, and
        persisted by TranslationWriter.save_project."""
        return self.data.get('meta', {}).get(key, default)

    def set_meta(self, key, value):
        meta = self.data.setdefault('meta', {})
        if value is None:
            meta.pop(key, None)
        else:
            meta[key] = value

    def save_all(self):
        self.project.writer.save_all()

    def apply(self):
        """ Translates the project and overwrites the Writer of the project """
        self.project.writer = TranslationWriter(self)

        # project
        self.project.data['name'] = self.data.get('project_name', self.project.name)

        # Card language: default a translation project to the language it's
        # translated into, so e.g. a German translation renders "GEGNER"
        # instead of "ENEMY" without a manual UI-language switch. Editable
        # afterwards via the project editor like any other project setting.
        self.project.data.setdefault('meta', {})['language'] = self.language

        # encounter sets
        for encounter_id in self.data.get('encounter_sets', {}):
            encounter = self.project.get_encounter_set(encounter_id)
            if not encounter:
                continue
            encounter.data['name'] = self.data['encounter_sets'][encounter_id]['name']

        # cards
        for card_id, card_data in self.data.get('cards', {}).items():
            card = self.project.get_card(card_id)
            if not card:
                continue
            card.data['name'] = card_data.get('name', card.name)
            if 'language' in card_data:
                card.data['language'] = card_data['language']
            for field, value in card_data.get('front', {}).items():
                card.data['front'][field] = value
            for field, value in card_data.get('back', {}).items():
                card.data['back'][field] = value

        # guides
        # overwrites the guides to hide non-translated guides
        self.project.data['guides'] = self.data.get('guides', [])
