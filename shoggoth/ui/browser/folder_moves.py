"""
Moving cards into, and creating cards in, the folder view's folders.

A folder node says where it is (`folder`) and what the path down to it tells
us about its cards (`context`) - see folder_spec.py. A move can fail: it only
goes through when that context is enough to know what the card becomes.

    an encounter set on the path    the card joins that set
    player cards / class /          the card leaves its encounter set (and
      investigator on the path        takes the class / investigator)
    campaign cards, but no set      only for a card already in a set
    nothing at all                  the card stays what it is

Either way the card's folder is then set to the target - unless the target
is on the way to where the card would sit by default (dropping on an
encounter set, on Player Cards, ...), which puts it back in its default folder.
"""
from uuid import uuid4

from shoggoth.card import default_folder, split_folder

PLAYER_CLASSES = ('guardian', 'seeker', 'rogue', 'mystic', 'survivor', 'neutral')


def is_folder(target):
    """Whether a tree item's user data describes a folder view folder"""
    return bool(target) and 'folder' in target and 'context' in target


def _is_player_context(context):
    return bool(context.get('player') or context.get('class') or context.get('investigator'))


def _target_class(card, context):
    """The class a card gets in this context: (known, class to set or None)"""
    cls = context.get('class')
    if not cls:
        return True, None
    if cls in PLAYER_CLASSES:
        return True, cls
    # 'Other' collects everything without a single known class: there is no
    # class to give a card to make it belong there
    current = card.get_class()
    return (not current or current not in PLAYER_CLASSES), None


def can_move(card, target):
    """Whether the target folder tells us enough to move the card into it"""
    if not is_folder(target) or card.project.is_modification:
        return False
    context = target['context']
    if context.get('unknown_set'):
        return False
    if context.get('encounter_set'):
        return True
    if _is_player_context(context):
        return _target_class(card, context)[0]
    if context.get('campaign'):
        return bool(card.data.get('encounter_set'))
    return True


def move_card(card, target):
    """Move a card into a folder. Returns whether it could be moved."""
    if not can_move(card, target):
        return False
    context = target['context']

    if encounter_set := context.get('encounter_set'):
        card.set('encounter_set', encounter_set.id)
    elif _is_player_context(context):
        card.set('encounter_set', None)
        if card.back.get('type') == 'encounter':
            card.back.set('type', 'player')
        cls = _target_class(card, context)[1]
        if context.get('investigator'):
            card.set('investigator', context['investigator'])
        elif cls:
            card.set('investigator', None)
        if cls:
            card.front.set('classes', [cls])

    path = split_folder(target['folder'])
    if split_folder(default_folder(card))[:len(path)] == path:
        card.folder = None
    else:
        card.folder = target['folder']
    return True


def new_card_data(target, template=None, source=None):
    """Data for a new card that sits in a folder: `source` (a copied card's
    data) or a blank card, with `template`'s faces applied, plus whatever the
    folder's context says its cards are."""
    context = target['context']
    data = dict(source or {})
    data['id'] = str(uuid4())
    data.setdefault('name', 'New Card')
    template = template or {}
    for side, fallback in (('front', 'asset'), ('back', 'player')):
        face = dict(data.get(side) or {})
        face.update(template.get(side) or {})
        face.setdefault('type', fallback)
        data[side] = face

    if encounter_set := context.get('encounter_set'):
        data['encounter_set'] = encounter_set.id
    elif _is_player_context(context):
        data.pop('encounter_set', None)
        if context.get('investigator'):
            data['investigator'] = context['investigator']
        if context.get('class') in PLAYER_CLASSES:
            data['front']['classes'] = [context['class']]

    data['meta'] = dict(data.get('meta') or {})
    data['meta']['folder'] = target['folder']
    return data
