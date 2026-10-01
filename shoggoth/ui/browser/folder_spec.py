"""
Tree specs for the folder view: every card sits in the folder named by
`Card.folder` (its own choice, or `card.default_folder`).

A folder is a FOLDER_SEPARATOR-joined path. Plain segments are generic
folders; segments in {braces} resolve per card to the built-in groups, and
produce the same typed nodes as the classic tree (tree_spec.py), so their
selection, context menus and drop targets keep working:

    {campaign_cards} {player_cards}     the two top-level groups
    {encounter_set}                     the card's encounter set
    {story} {locations} {encounter}     the groups within an encounter set
    {investigators} {investigator}      the investigators group / the card's investigator
    {class}                             the card's class
    {card_type}                         the card's type, as a generic folder

A segment that resolves to nothing (e.g. {encounter_set} on a player card)
is skipped.

Every folder node carries two extra pieces of user data, for dropping cards
into it and creating cards in it (see folder_moves.py):

    folder      the folder string that puts a card in this folder
    context     what the path down to it says about its cards: 'campaign',
                'player', 'encounter_set', 'class', 'investigator'
"""
from shoggoth.card import FOLDER_SEPARATOR, split_folder
from shoggoth.files import overlay_dir
from shoggoth.i18n import tr
from shoggoth.ui.browser.tree_spec import (
    build_card_spec, build_guides_spec, build_root_spec, card_display_name,
    make_inverted_icon, warning_triangle_icon,
)

SET_GROUPS = ('story', 'locations', 'encounter')
CLASS_ORDER = ['seeker', 'rogue', 'guardian', 'mystic', 'survivor', 'neutral', 'other']
CLASSES_WITH_ICONS = {'guardian', 'seeker', 'rogue', 'mystic', 'survivor'}

# Sibling folders are ordered by (group, position): built-in groups first, in
# the classic tree's order, then generic folders alphabetically.
_TOP, _SET_GROUP, _SET, _UNKNOWN_SET, _INVESTIGATORS, _CLASS, _INVESTIGATOR, _GENERIC = range(8)


class _Folder:
    """A folder node under construction"""

    def __init__(self, key, text, rank, type='folder', data=None, icon=None,
                 segment=None, gathers=None, **extra):
        self.key = key
        self.segment = segment or key  # as written in a folder string
        self.gathers = gathers or {}   # what being in this folder says about a card
        self.template = []             # segments from the root down to this folder
        self.context = {}              # everything gathered along that path
        self.text = text
        self.rank = rank
        self.type = type
        self.data = data
        self.icon = icon
        self.extra = extra
        self.folders = {}  # key -> _Folder
        self.cards = []

    def child(self, folder):
        """The subfolder with this key, added if it isn't there yet"""
        if folder.key not in self.folders:
            folder.template = self.template + [folder.segment]
            folder.context = {**self.context, **folder.gathers}
            self.folders[folder.key] = folder
        return self.folders[folder.key]

    def adopt(self, other):
        """Move another folder's contents into this one. They keep their
        own template and context: a card dropped into an adopted folder
        still gets the full path."""
        for folder in other.folders.values():
            self.folders.setdefault(folder.key, folder)
        self.cards.extend(other.cards)

    def children_specs(self, path, project):
        specs = []
        for folder in sorted(self.folders.values(), key=lambda f: f.rank):
            folder_path = f'{path}/{folder.key}'
            specs.append({
                'node_id': f'folder:{folder_path}:{project.file_path}',
                'text': folder.text,
                'type': folder.type,
                'data': folder.data if folder.data is not None else project,
                'icon': folder.icon,
                'children': folder.children_specs(folder_path, project),
                'folder': FOLDER_SEPARATOR.join(folder.template),
                'context': folder.context,
                **folder.extra,
            })
        for card in sorted(self.cards, key=lambda c: card_display_name(c, _show_level(c)).lower()):
            specs.append(build_card_spec(card, include_level=_show_level(card)))
        return specs


def _show_level(card):
    return not card.data.get('encounter_set')


def _generic(text):
    return _Folder(text, text, (_GENERIC, text.lower()))


def _encounter_set_folder(project, encounter_set, position):
    icon = None
    if encounter_set.icon:
        icon = make_inverted_icon(project.find_file(encounter_set.icon) or encounter_set.icon,
                                  project.file_path)
    return _Folder(f'{{encounter_set}}:{encounter_set.id}', encounter_set.name, (_SET, position),
                   type='encounter', data=encounter_set, icon=icon,
                   segment='{encounter_set}', gathers={'encounter_set': encounter_set})


def _class_folder(cls):
    labels = {
        'seeker': 'CLASS_SEEKER', 'rogue': 'CLASS_ROGUE', 'guardian': 'CLASS_GUARDIAN',
        'mystic': 'CLASS_MYSTIC', 'survivor': 'CLASS_SURVIVOR', 'neutral': 'CLASS_NEUTRAL',
        'other': 'CLASS_OTHER',
    }
    icon = None
    if cls in CLASSES_WITH_ICONS:
        path = overlay_dir / f"class_symbol_{cls}.png"
        if path.exists():
            icon = str(path)
    return _Folder(f'{{class}}:{cls}', tr(labels[cls]), (_CLASS, CLASS_ORDER.index(cls)),
                   type='category', icon=icon, segment='{class}',
                   gathers={'player': True, 'class': cls}, **{'class': cls})


def _campaign_cards_folder():
    return _Folder('{campaign_cards}', tr('TREE_CAMPAIGN_CARDS'), (_TOP, 0),
                   type='campaign_cards', gathers={'campaign': True})


def _resolve(segment, card, project, set_positions):
    """The folder a segment stands for on this card, or None to skip it"""
    if not (segment.startswith('{') and segment.endswith('}')):
        return _generic(segment)
    token = segment[1:-1]

    if token == 'campaign_cards':
        return _campaign_cards_folder()
    if token == 'player_cards':
        return _Folder(segment, tr('TREE_PLAYER_CARDS'), (_TOP, 1), type='player_cards',
                       gathers={'player': True})

    if token == 'encounter_set':
        set_id = card.data.get('encounter_set')
        if not set_id:
            return None
        if set_id not in set_positions:
            # the set was deleted, or the id is stale from a copy between
            # projects: keep the card visible rather than dropping it
            return _Folder('{unknown_set}', tr('TREE_UNKNOWN_SET'), (_UNKNOWN_SET, 0),
                           type='category', icon=warning_triangle_icon(),
                           segment='{encounter_set}', gathers={'unknown_set': True})
        return _encounter_set_folder(project, card.encounter, set_positions[set_id])

    if token in SET_GROUPS:
        return _set_group_folder(token, card.encounter)

    if token == 'investigators':
        return _Folder(segment, tr('TREE_INVESTIGATORS'), (_INVESTIGATORS, 0),
                       type='category', gathers={'player': True}, **{'class': 'investigators'})
    if token == 'investigator':
        group = card.data.get('investigator')
        if not group:
            return None
        return _Folder(f'{{investigator}}:{group}', group, (_INVESTIGATOR, group.lower()),
                       type='category', segment='{investigator}',
                       gathers={'player': True, 'investigator': group}, investigator=group)

    if token == 'class':
        cls = card.get_class() or 'other'
        return _class_folder(cls if cls in CLASS_ORDER else 'other')

    if token == 'card_type':
        card_type = card.card_type
        return _generic(card_type.replace('_', ' ').title()) if card_type else None

    return _generic(segment)


def _set_group_folder(token, encounter_set):
    """One of the Story / Locations / Encounter groups. Within an encounter
    set these are the classic tree's typed nodes; elsewhere plain folders."""
    folder = _Folder(f'{{{token}}}', tr(f'TREE_{token.upper()}'), (_SET_GROUP, SET_GROUPS.index(token)))
    if encounter_set:
        folder.type = 'locations' if token == 'locations' else 'category'
        folder.data = encounter_set
    return folder


def _find_all(folder, type):
    for child in folder.folders.values():
        if child.type == type:
            yield child
        yield from _find_all(child, type)


def build_folder_tree_spec(project):
    """Build a specification of the desired folder tree for one project"""
    if not project:
        return None

    root_spec = build_root_spec(project)
    root = _Folder('', '', None)

    encounter_sets = list(project.encounter_sets)
    set_positions = {encounter_set.id: i for i, encounter_set in enumerate(encounter_sets)}

    for card in project.cards:
        folder = root
        for segment in split_folder(card.folder):
            resolved = _resolve(segment, card, project, set_positions)
            if resolved is not None:
                folder = folder.child(resolved)
        folder.cards.append(card)

    # An encounter set is opened through its node, so every set needs one,
    # with or without cards in it.
    shown_sets = {folder.data.id for folder in _find_all(root, 'encounter')}
    for encounter_set in encounter_sets:
        if encounter_set.id not in shown_sets:
            campaign = root.child(_campaign_cards_folder())
            campaign.child(_encounter_set_folder(project, encounter_set, set_positions[encounter_set.id]))

    for set_folder in list(_find_all(root, 'encounter')):
        groups = list(set_folder.folders)
        if groups == ['{encounter}'] and not set_folder.cards:
            # only encounter cards: show them directly in the set
            set_folder.adopt(set_folder.folders.pop('{encounter}'))
        elif groups or set_folder.cards:
            # the groups are also where new cards are added, and Locations
            # is the way into the set's location map: show all three
            for token in SET_GROUPS:
                set_folder.child(_set_group_folder(token, set_folder.data))

    # Only campaign cards, or only player cards: no need for the split
    if list(root.folders) in (['{campaign_cards}'], ['{player_cards}']) and not root.cards:
        root.adopt(root.folders.popitem()[1])

    root_spec['children'] = root.children_specs('', project)
    if guides_spec := build_guides_spec(project):
        root_spec['children'].append(guides_spec)
    return root_spec
