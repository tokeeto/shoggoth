import json
import re
from uuid import uuid4
from pathlib import Path
from typing import Any

from shoggoth.files import defaults_dir

_NUMBER_CHUNK_RE = re.compile(r'\d+|\D+')
FOLDER_SEPARATOR = '/'
FACE_NAMES = ('front', 'back')


def natural_sort_key(value):
    """ Split a value like a project_number ('12', '128a') into chunks so
        sorting compares numeric chunks numerically and text chunks as
        strings, instead of comparing the whole thing as one string.

        Each chunk is tagged (0, int) or (1, str) so chunks of different
        kinds never get compared directly (which would raise TypeError).
    """
    return [(1, chunk) if not chunk.isdigit() else (0, int(chunk))
            for chunk in _NUMBER_CHUNK_RE.findall(str(value))]


def matches(when, tags):
    """ Evaluates a variant block condition against a set of tags.

        `when` is a clause string or a list of clause strings (any clause
        may match). A clause is one or more '&'-separated tags that must
        all be present; a tag prefixed with '!' must be absent.
        A missing/empty condition always matches.
    """
    if not when:
        return True
    clauses = [when] if isinstance(when, str) else when
    for clause in clauses:
        for term in clause.split('&'):
            term = term.strip()
            if term.startswith('!'):
                if term[1:].strip() in tags:
                    break
            elif term not in tags:
                break
        else:
            return True
    return False


class Face:
    def __init__(self, data, card):
        self.data = data
        self.card = card
        self._fallback = None
        self._fallback_files = []

    def __eq__(self, other):
        return self.data == other.data

    def __build_fallback(self, name):
        """ Builds the fallback recursively """
        fallback = {}
        if path := self.card.project.find_file(name):
            defaults_path = path
            self._fallback_files.append(path)
        else:
            defaults_path = defaults_dir / f'{name}.json'

        try:
            with defaults_path.open('r', encoding='utf-8') as f:
                fallback = json.load(f)
                if fallback.get('parent'):
                    parent = self.__build_fallback(fallback['parent'])
                    # variant blocks accumulate along the parent chain
                    # (child blocks last, so they win), while plain keys
                    # merge with the child overriding the parent
                    variants = (parent.get('variants') or []) + (fallback.get('variants') or [])
                    fallback = parent | fallback
                    if variants:
                        fallback['variants'] = variants
        except Exception as e:
            print('exception when loading fallback:', e)
            return {}

        return fallback

    @property
    def fallback(self):
        if self._fallback is None:
            self._fallback_files = []
            self._fallback = self.__build_fallback(self.data['type'])
        return self._fallback

    @property
    def inherit(self):
        """ The face this one inherits from, as {'card': id, 'face': 'front'|'back'},
            or None.
        """
        link = self.data.get('inherit')
        if isinstance(link, dict) and link.get('card') and link.get('face') in FACE_NAMES:
            return link
        return None

    @property
    def inherited_face(self):
        """ The Face this one inherits from, or None (no inherit, or the card
            is gone). Looked up fresh on every call: the source can change or
            be deleted at any time, and nothing would tell us to invalidate a
            cached copy.
        """
        link = self.inherit
        if not link:
            return None
        card = self.card.project.get_card(link['card'])
        return card.get_face(link['face']) if card else None

    def _stored(self, key, _seen=None):
        """ The value stored for key on this face, or on the face it
            inherits from (recursively). Defaults files are not consulted.
            Raises KeyError when no face in the chain stores the key.
            Inheritance cycles are cut where they loop.

            'type' is never inherited in practice: every face stores its own.
        """
        if key in self.data:
            return self.data[key]
        _seen = _seen or set()
        _seen.add(id(self.data))
        source = self.inherited_face
        if source is None or id(source.data) in _seen:
            raise KeyError(key)
        return source._stored(key, _seen)

    def _stored_keys(self):
        """ Every key _stored can answer for """
        keys, seen, face = set(), set(), self
        while face is not None and id(face.data) not in seen:
            seen.add(id(face.data))
            keys |= set(face.data)
            face = face.inherited_face
        return keys - {'inherit'}

    @property
    def fallback_files(self):
        """Project-local defaults files this face's fallback chain was loaded
        from (the asset pack's own defaults are not listed)."""
        self.fallback  # noqa: B018 -- loading the fallback is what fills _fallback_files
        return tuple(self._fallback_files)

    def tags(self):
        """ The set of tags variant blocks can match against:
            the card's class (or multi patterns when it has several classes),
            plus pseudo-tags derived from card state ('encounter' when the
            card belongs to an encounter set).
        """
        tags = set()
        classes = self.get('classes', [])
        if len(classes) == 1:
            tags.add(classes[0])
        elif len(classes) > 1:
            tags.add('multi')
            tags.add(f'multi{len(classes)}')
            for n in range(1, len(classes) + 1):
                tags.add(f'multi{n}+')
        # raw data check instead of card.encounter, which scans the project
        # per call — too slow for something evaluated on every field lookup
        if self.card.data.get('encounter_set'):
            tags.add('encounter')
        return tags

    def __getitem__(self, key):
        """ The face's value for key, fully resolved: stored on this face,
            else inherited (see inherit), else from the defaults chain; a
            '<copy>' is then replaced by the other side's value.
            Raises KeyError when nothing provides one.

            face.data[key] is the value this face itself holds (which may be
            '<copy>', or missing because it's inherited).
        """
        value = self._resolve(key)
        if value == '<copy>':
            value = self.other_side._resolve(key)
            if value == '<copy>':  # both sides copying each other
                raise KeyError(key)
        return value

    def _resolve(self, key):
        """ __getitem__ without the '<copy>' step """
        try:
            return self._stored(key)
        except KeyError:
            pass

        # classes decide which variant/suffixed keys apply (tags() reads them),
        # so they can't come from those themselves - that would recurse
        if key == 'classes':
            return self.fallback[key]

        # variant blocks: later blocks override earlier ones
        variants = self.fallback.get('variants')
        if variants:
            tags = self.tags()
            for variant in reversed(variants):
                values = variant.get('set', {})
                if key in values and matches(variant.get('when'), tags):
                    return values[key]

        # legacy flat '<key>_<class>' lookup for old-format defaults files
        cls = self.get_class()
        if cls == 'multi':
            for pattern in self.get_multi_patterns():
                if f'{key}_{pattern}' in self.fallback:
                    return self.fallback[f'{key}_{pattern}']
        if f'{key}_{cls}' in self.fallback:
            return self.fallback[f'{key}_{cls}']
        return self.fallback[key]

    def visible_keys(self):
        """ All keys resolvable on this face: card data, active variant
            blocks, and the base fallback.
        """
        keys = (self._stored_keys() | set(self.fallback)) - {'variants', 'parent'}
        tags = self.tags()
        for variant in self.fallback.get('variants') or []:
            if matches(variant.get('when'), tags):
                keys |= set(variant.get('set', {}))
        return keys

    def get(self, key, default:Any=''):
        try:
            result = self[key]
        except KeyError:
            return default
        return default if result is None else result

    def get_path(self, key, default=''):
        res = self.get(key, default)
        if res:
            return self.card.project.find_file(Path(res))

    def set(self, key, value):
        if key == 'type':
            if not value:
                raise ValueError('a face must have a type')
            self._fallback = None

        changed = self.data.get(key) != value

        self.data[key] = value
        if value is None:
            del self.data[key]

        # Marking dirty (after the data is in place) notifies the project's
        # change listeners -- that's how the UI learns it should re-render/
        # refresh the tree, rather than this model code calling into the app.
        if changed:
            self.card.dirty = True

    def get_class(self):
        cls = self.get('classes', [])
        if not cls:
            return None
        if len(cls) == 1:
            return cls[0]
        return 'multi'

    def get_multi_patterns(self):
        """ Returns a number of patterns to match for multi class cards """
        cls_count = len(self.get('classes', []))
        # 1st - straight count: multi3
        yield f'multi{cls_count}'
        # 2nd - plus, ranging from highest to lowest: multi4+
        for n in range(cls_count, 0, -1):
            yield f'multi{n}+'

    @property
    def card_types(self):
        """ Every game role this face fills, most significant first.

            Usually a single role, taken from the type's "card_type". Types
            blending several roles list them all in "card_types" (e.g.
            enemy_location is ["location", "enemy"]). A type without either
            (old project-local defaults files) falls back to its own name,
            minus any "_back".
        """
        card_type = self.get('card_type', None)
        card_types = self.get('card_types', None) or []
        if isinstance(card_types, str):
            card_types = [card_types]
        if not card_type:
            if card_types:
                return list(card_types)
            type_name = self.data.get('type')
            if not type_name:
                return []
            card_type = Path(type_name).stem.removesuffix('_back')
        return [card_type] + [t for t in card_types if t != card_type]

    @property
    def card_type(self):
        """ The primary game role of this face (see card_types) """
        card_types = self.card_types
        return card_types[0] if card_types else ''

    def editor_candidates(self):
        """ Editor names to try for this face, best match first: an explicit
            "editor", the type itself, then the editor of its card_type.
        """
        card_type = self.card_type
        type_name = self.get('type')
        candidates = [self.get('editor', None), type_name]
        if card_type:
            if str(type_name).endswith('_back'):
                candidates.append(f'{card_type}_back')
            candidates.append(card_type)
        return [c for c in dict.fromkeys(candidates) if c]

    def get_editor(self):
        """ Returns the expected editor type for this face
            This will usually be the same as a the type, but
            some types might be using a parent editor instead.
        """
        return self.get('editor', self.get('type'))

    @property
    def other_side(self):
        if self == self.card.front:
            return self.card.back
        return self.card.front


def split_folder(folder):
    """ The segments of a folder string, outermost first """
    return [part.strip() for part in str(folder or '').split(FOLDER_SEPARATOR) if part.strip()]


def default_folder(card):
    """ Where a card sits in the project's folder view unless it says
        otherwise (see Card.folder), as a FOLDER_SEPARATOR-joined path.

        Segments in {braces} stand for the built-in groups and are resolved
        per card when the tree is built (ui/browser/folder_spec.py), so a
        card follows its encounter set, class or investigator around.
    """
    if card.data.get('encounter_set'):
        card_type = card.card_type
        if card_type == 'location':
            group = '{locations}'
        elif card_type in ('treachery', 'enemy'):
            group = '{encounter}'
        else:
            group = '{story}'
        return FOLDER_SEPARATOR.join(('{campaign_cards}', '{encounter_set}', group))
    if card.data.get('investigator'):
        return FOLDER_SEPARATOR.join(('{player_cards}', '{investigators}', '{investigator}'))
    return FOLDER_SEPARATOR.join(('{player_cards}', '{class}'))


class Card:
    """Class to represent the card object and file structure"""

    def __init__(
        self,
        data: dict[str, Any],
        project,
        encounter=None,
    ):
        self.data = data
        if encounter:
            self.data['encounter_set'] = encounter.id
        self.project = project
        if 'id' not in data:
            data['id'] = str(uuid4())
            # See EncounterSet.__init__: a freshly-generated id only exists in
            # memory until the project is saved - mark it dirty so it's not
            # silently regenerated (mismatching a saved session selection) next load.
            self.dirty = True

        self.front = Face(self.data['front'], card=self)
        self.back = Face(self.data['back'], card=self)

    def __hash__(self):
        return hash(self.id)

    def __str__(self):
        return f'<Card "{self.name}">'

    @property
    def dirty(self):
        return self.project.is_dirty(self.id)

    @dirty.setter
    def dirty(self, value):
        self.project.set_dirty(self.id, value)

    @property
    def encounter(self):
        if 'encounter_set' not in self.data or not self.data['encounter_set']:
            return None
        return self.project.get_encounter_set(self.data['encounter_set'])

    def reload_fallback(self):
        """ Invalidates the fallback cache, forcing a reload of the file """
        self.front._fallback = None
        self.back._fallback = None

    @property
    def name(self):
        return self.data.get('name', 'Unnamed card')

    @property
    def language(self):
        """ Per-card card-rendering language override."""
        return self.data.get('language', '')

    @language.setter
    def language(self, value):
        if value:
            self.data['language'] = value
        else:
            self.data.pop('language', None)
        self.dirty = True

    @property
    def effective_language(self):
        """ The language this card actually renders in """
        return self.language or self.project.language

    @property
    def amount(self):
        return self.data.get('amount', 1)

    @property
    def id(self):
        return self.data['id']

    @property
    def project_number(self):
        return self.data.get('project_number', 0)

    @project_number.setter
    def project_number(self, value):
        if self.data.get('project_number') != value:
            self.data['project_number'] = value
            self.dirty = True

    @property
    def encounter_number(self) -> None | str:
        if not self.encounter:
            return None
        return self.data.get('encounter_number', -1)

    @encounter_number.setter
    def encounter_number(self, value):
        if not self.encounter:
            raise Exception("No encounter, can't set number.")
        if self.data.get('encounter_number') != value:
            self.data['encounter_number'] = value
            self.dirty = True

    @property
    def card_types(self):
        """ Every role this card has in the game, most significant first.
            Based on the front face, or the back face if the front has none.
        """
        return self.front.card_types or self.back.card_types

    @property
    def card_type(self):
        """ The single role this card has in the game (see card_types) """
        card_types = self.card_types
        return card_types[0] if card_types else ''

    @property
    def folder(self):
        """ The folder this card appears in: the user's own choice
            (meta 'folder') or the default for its kind of card.
        """
        return self.get_meta('folder') or default_folder(self)

    @folder.setter
    def folder(self, value):
        """ Stores a folder choice; the default (or nothing) clears it, so
            the card keeps following its default folder.
        """
        value = FOLDER_SEPARATOR.join(split_folder(value))
        if not value or value == default_folder(self):
            value = None
        self.set_meta('folder', value)

    @property
    def has_versions(self):
        return isinstance(self.encounter_number, str) and '-' in self.encounter_number

    @property
    def versions(self):
        if not self.has_versions:
            return [self]
        assert isinstance(self.encounter_number, str)

        versions = []
        r = self.encounter_number.split('-')
        for n in range(int(r[0]), int(r[1]) + 1):
            cp = Card(self.data.copy(), self.project, self.encounter)
            cp.data['encounter_number'] = n  # detached copy: don't dirty the real card
            versions.append(cp)
        return versions

    @property
    def code(self):
        if self.encounter:
            return f'{self.project.code}_{self.encounter.code}_{self.name}'
        return f'{self.project.code}_{self.project_number}_{self.name}'

    def __eq__(self, other):
        return other is not None and self.data == other.data

    def get_class(self):
        back_classes = self.data['back'].get('classes')
        classes = self.data['front'].get('classes', back_classes)
        if not classes:
            return None

        if len(classes) > 1:
            return 'multi'
        else:
            return classes[0]

    def set(self, key, value):
        changed = self.data.get(key) != value

        self.data[key] = value
        if key in self.data and value is None:
            del self.data[key]

        if changed:
            self.dirty = True

    def get(self, key, default=None):
        if key == 'copyright' and 'copyright' not in self.data:
            return self.project.get('default_copyright', default)
        return self.data.get(key, default)

    def get_face(self, name) -> Face:
        """ The face called name ('front' or 'back') """
        return self.front if name == 'front' else self.back

    def face_name(self, face) -> str:
        """ 'front' or 'back': the inverse of get_face """
        return 'front' if face is self.front else 'back'

    def get_meta(self, key, default=None):
        """ Reads a designer-facing metadata field (bonded/set_aside/description/
            notes/tags/...), stored under data['meta'] rather than as a top-level key.
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

    @staticmethod
    def is_valid(data):
        return 'front' in data and 'back' in data

    @staticmethod
    def new(name) -> dict[str, Any]:
        return {
            'name': name,
            'id': str(uuid4()),
            'front': {
                'type': 'asset'
            },
            'back': {
                'type': 'player'
            }
        }

    def save(self):
        self.project.writer.save_card(self)
        self.dirty = False


# templates
class TEMPLATES:
    @classmethod
    def get(cls, name):
        return {
            'investigator': cls.INVESTIGATOR(),
            'mini_investigator': cls.MINI_INVESTIGATOR(),
            'asset': cls.ASSET(),
            'event': cls.EVENT(),
            'skill': cls.SKILL(),
            'story': cls.STORY(),
            'treachery': cls.TREACHERY(),
            'enemy': cls.ENEMY(),
            'location': cls.LOCATION(),
            'act': cls.ACT(),
            'agenda': cls.AGENDA(),
            'scenario': cls.SCENARIO(),
            'enemy_weakness': cls.ENEMY_WEAKNESS(),
            'treachery_weakness': cls.TREACHERY_WEAKNESS(),
        }.get(name, cls.BASE())

    @classmethod
    def BASE(cls):
        return {
            'name': '',
            'id': str(uuid4()),
            'amount': 1,
            'front': {
                'type': ''
            },
            'back': {
                'type': ''
            }
        }

    @classmethod
    def ASSET(cls):
        card = cls.BASE()
        card['amount'] = 2
        card['front']['type'] = 'asset'
        card['back']['type'] = 'player'
        return card

    @classmethod
    def INVESTIGATOR(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'investigator'
        card['back']['type'] = 'investigator_back'
        card['back']['entries'] = [
            ["<b>Deck Size:</b>", "30"],
            ["<b>Secondary Class Choice:</b>", ""],
            ["<b>Deckbuilding Options:</b>", ""],
            ["<b>Deckbuilding Requirements</b> (do not count toward deck size):", ""],
            ["<b>Deckbuilding Restrictions:</b>", ""],
        ]
        return card

    @classmethod
    def MINI_INVESTIGATOR(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['enumerated'] = 'ignored'
        card['front']['type'] = 'mini_investigator'
        card['back']['type'] = 'mini_investigator_back'
        return card

    @classmethod
    def EVENT(cls):
        card = cls.BASE()
        card['amount'] = 2
        card['front']['type'] = 'event'
        card['back']['type'] = 'player'
        return card

    @classmethod
    def SKILL(cls):
        card = cls.BASE()
        card['amount'] = 2
        card['front']['type'] = 'skill'
        card['back']['type'] = 'player'
        return card

    @classmethod
    def ENEMY(cls):
        card = cls.BASE()
        card['amount'] = 3
        card['front']['type'] = 'enemy'
        card['back']['type'] = 'encounter'
        return card

    @classmethod
    def TREACHERY(cls):
        card = cls.BASE()
        card['amount'] = 3
        card['front']['type'] = 'treachery'
        card['back']['type'] = 'encounter'
        return card

    @classmethod
    def LOCATION(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'location'
        card['back']['type'] = 'location_back'
        return card

    @classmethod
    def ACT(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'act'
        card['back']['type'] = 'act_back'
        return card

    @classmethod
    def AGENDA(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'agenda'
        card['back']['type'] = 'agenda_back'
        return card

    @classmethod
    def SCENARIO(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'chaos'
        card['front']['difficulty'] = 'EASY/STANDARD'
        card['back']['type'] = 'chaos'
        card['back']['difficulty'] = 'HARD/EXPERT'
        return card

    @classmethod
    def STORY(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'story'
        card['back']['type'] = 'story'
        return card

    @classmethod
    def ENEMY_WEAKNESS(cls):
        card = cls.ENEMY()
        card['amount'] = 1
        card['front']['type'] = 'enemy'
        card['front']['classes'] = ['weakness']
        card['back']['type'] = 'player'
        return card

    @classmethod
    def TREACHERY_WEAKNESS(cls):
        card = cls.TREACHERY()
        card['amount'] = 1
        card['front']['type'] = 'treachery'
        card['front']['classes'] = ['weakness']
        card['back']['type'] = 'player'
        return card
