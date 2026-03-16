"""
Export helpers - shared utilities for exporting cards to various formats
"""
import json

# Mapping from Shoggoth face types to expected front/back pairs
# Format: front_type -> (export_type, expected_back_type)
CARD_TYPE_INFO = {
    # Player cards - have "player" backs
    'asset': {
        'export_type': 'asset',
        'expected_back': 'player',
        'faction': 'from_classes',  # Derive from card's classes
    },
    'event': {
        'export_type': 'event',
        'expected_back': 'player',
        'faction': 'from_classes',
    },
    'skill': {
        'export_type': 'skill',
        'expected_back': 'player',
        'faction': 'from_classes',
    },

    # Customizable cards - have "customizable_back" backs
    'customizable': {
        'export_type': 'asset',  # Most customizables are assets
        'expected_back': 'customizable_back',
        'faction': 'from_classes',
    },

    # Investigator cards - have specific front/back
    'investigator': {
        'export_type': 'investigator',
        'expected_back': 'investigator_back',
        'faction': 'from_classes',
        'double_sided': True,
    },

    # Encounter cards - have "encounter" backs
    'enemy': {
        'export_type': 'enemy',
        'expected_back': 'encounter',
        'faction': 'mythos',
    },
    'treachery': {
        'export_type': 'treachery',
        'expected_back': 'encounter',
        'faction': 'mythos',
    },

    # Location cards - have specific front/back
    'location': {
        'export_type': 'location',
        'expected_back': 'location_back',
        'faction': 'mythos',
        'double_sided': True,
    },

    # Act cards - have specific front/back
    'act': {
        'export_type': 'act',
        'expected_back': 'act_back',
        'faction': 'mythos',
        'double_sided': True,
    },

    # Agenda cards - have specific front/back
    'agenda': {
        'export_type': 'agenda',
        'expected_back': 'agenda_back',
        'faction': 'mythos',
        'double_sided': True,
    },

    # Scenario/Chaos reference cards - same type on both sides
    'chaos': {
        'export_type': 'scenario',
        'expected_back': 'chaos',
        'faction': 'mythos',
        'double_sided': True,
    },

    # Story cards
    'story': {
        'export_type': 'story',
        'expected_back': 'story',  # Or could be encounter
        'faction': 'mythos',
    },
}

# Mapping from Shoggoth class names to arkham.build faction codes
CLASS_TO_FACTION = {
    'guardian': 'guardian',
    'seeker': 'seeker',
    'rogue': 'rogue',
    'mystic': 'mystic',
    'survivor': 'survivor',
    'neutral': 'neutral',
}


def get_card_export_type(card):
    """
    Determine the export type for a card based on its front face type.

    Returns a dict with:
        - type_code: The export type code (e.g., 'asset', 'enemy', 'location')
        - faction_code: The primary faction code
        - faction2_code: Secondary faction (for multi-class)
        - faction3_code: Tertiary faction (for multi-class)
        - double_sided: Whether the card has meaningful content on both sides
        - is_encounter: Whether this is an encounter card (vs player card)
    """
    front_type = card.front.get('type')

    if front_type not in CARD_TYPE_INFO:
        return {
            'type_code': 'unknown',
            'faction_code': 'neutral',
            'faction2_code': None,
            'faction3_code': None,
            'double_sided': False,
            'is_encounter': False,
        }

    info = CARD_TYPE_INFO[front_type]

    # Determine faction(s)
    faction_code = 'neutral'
    faction2_code = None
    faction3_code = None

    if info['faction'] == 'from_classes':
        classes = card.front.get('classes', [])
        if classes:
            if len(classes) >= 1:
                faction_code = CLASS_TO_FACTION.get(classes[0], 'neutral')
            if len(classes) >= 2:
                faction2_code = CLASS_TO_FACTION.get(classes[1], None)
            if len(classes) >= 3:
                faction3_code = CLASS_TO_FACTION.get(classes[2], None)
    else:
        faction_code = info['faction']

    return {
        'type_code': info['export_type'],
        'faction_code': faction_code,
        'faction2_code': faction2_code,
        'faction3_code': faction3_code,
        'double_sided': info.get('double_sided', False),
        'is_encounter': info['faction'] == 'mythos',
    }


def is_player_card(card):
    """Check if a card is a player card (has player back)"""
    front_type = card.front.get('type')
    if front_type in CARD_TYPE_INFO:
        info = CARD_TYPE_INFO[front_type]
        return info['expected_back'] in ('player', 'customizable_back')
    return False


def is_investigator_card(card):
    """Check if a card is an investigator card"""
    return card.front.get('type') == 'investigator'


def is_encounter_card(card):
    """Check if a card is an encounter card"""
    front_type = card.front.get('type')
    if front_type in CARD_TYPE_INFO:
        return CARD_TYPE_INFO[front_type]['faction'] == 'mythos'
    return False


def parse_slot(face):
    """
    Parse slot information from a face.

    Returns the slot string for arkham.build format.
    """
    slots = face.get('slots', [])
    slot = face.get('slot')

    if slots:
        return ', '.join(slots)
    elif slot:
        return slot
    return None


# ---------------------------------------------------------------------------
# SCED GMNotes metadata builder
# ---------------------------------------------------------------------------

# Shoggoth type → SCED type string
_TYPE_TO_SCED = {
    'asset': 'Asset',
    'event': 'Event',
    'skill': 'Skill',
    'customizable': 'Asset',
    'investigator': 'Investigator',
    'enemy': 'Enemy',
    'treachery': 'Treachery',
    'location': 'Location',
    'act': 'Act',
    'agenda': 'Agenda',
    'chaos': 'ScenarioReference',
    'story': 'Story',
}

# Card types that belong to the Mythos faction
_ENCOUNTER_TYPES = {'enemy', 'treachery', 'location', 'act', 'agenda', 'chaos', 'story'}

# Shoggoth class name → SCED class name
_CLASS_TO_SCED = {
    'guardian': 'Guardian',
    'seeker': 'Seeker',
    'rogue': 'Rogue',
    'mystic': 'Mystic',
    'survivor': 'Survivor',
    'neutral': 'Neutral',
}

# Shoggoth slot name → SCED slot name
_SLOT_TO_SCED = {
    'hand': 'Hand',
    'hands': 'Hand x2',
    'arcane': 'Arcane',
    'arcanes': 'Arcane x2',
    'ally': 'Ally',
    'body': 'Body',
    'accessory': 'Accessory',
    'tarot': 'Tarot',
}

# Shoggoth icon key → SCED icon count field
_ICON_KEY_TO_SCED = {
    'W': 'willpowerIcons',
    'I': 'intellectIcons',
    'C': 'combatIcons',
    'A': 'agilityIcons',
    'Q': 'wildIcons',
}


def _sced_icon_counts(face):
    """Return dict of non-zero SCED icon count fields from a face."""
    icons = face.get('icons', '')
    counts = {}
    for icon in icons:
        key = _ICON_KEY_TO_SCED.get(icon)
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _sced_slot(face):
    """Return SCED slot string (pipe-separated, title case), or None."""
    slots = face.get('slots', [face.get('slot')])
    sced = [_SLOT_TO_SCED.get(s.lower()) for s in slots if s]
    return '|'.join(sced) if sced else None


def _sced_location_data(face):
    """Build the locationFront/locationBack sub-dict for a location face."""
    data = {}

    data['icons'] = face.get('connection', '')
    connections = [c.replace('_a', 'A') for c in face.get('connections', [])]
    try:
        data['connections'] = '|'.join(connections)
    except Exception:
        pass

    victory = face.get('victory', '')
    if victory:
        try:
            data['victory'] = _try_int(victory)
        except (ValueError, TypeError):
            pass

    if face.get('clues', ''):
        data['uses'] = [{
            "type": "Clue",
            "token": "clue"
        }]
        if '<per>' in face.get('clues', ''):
            data['uses'][0]['countPerInvestigator'] = _try_int(face.get('clues').split('<')[0])
        else:
            data['uses'][0]['count'] = _try_int(face.get('clues'))

    return data or None


def _try_int(value):
    """Convert value to int if possible, else return None."""
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def build_gm_notes(card):
    """
    Build the SCED GMNotes metadata dict for a card.

    Returns a dict suitable for JSON-serialising into the TTS GMNotes field.
    """
    front_type = card.front.get('type', '')
    notes = {}

    notes['id'] = card.id
    notes['type'] = _TYPE_TO_SCED.get(front_type, 'Asset')

    # class / faction
    if front_type in _ENCOUNTER_TYPES:
        notes['class'] = 'Mythos'
    else:
        classes = card.front.get('classes', [])
        if isinstance(classes, str):
            classes = [c.strip() for c in classes.split(',') if c.strip()]
        if classes:
            sced_classes = [_CLASS_TO_SCED.get(c.lower(), c.title()) for c in classes if c]
            notes['class'] = '|'.join(sced_classes)

    # traits (stored as "Trait. Trait." string)
    traits = card.front.get('traits', '')
    if traits:
        notes['traits'] = traits

    # --- type-specific fields ---
    if card.front.get('cost'):
        notes['cost'] = _try_int(card.front.get('cost'))
    notes.update(_sced_icon_counts(card.front))

    if 'Permanent.' in card.front.get('text'):
        notes['permanent'] = True

    # weakness detection via class field
    classes = card.front.get('classes', [])
    if isinstance(classes, str):
        classes = [c.strip().lower() for c in classes.split(',')]
    if any(c.lower() == 'weakness' for c in classes if c):
        notes['weakness'] = True
    if front_type in ('asset', 'event', 'skill', 'customizable'):
        level_raw = card.front.get('level', '')
        if level_raw not in ('', None, 'None', 'Custom'):
            level = _try_int(level_raw)
            if level is not None:
                notes['level'] = level

    slot = _sced_slot(card.front)
    if slot:
        notes['slot'] = slot

    for stat, sced_key in [
        ('willpower', 'willpowerIcons'),
        ('intellect', 'intellectIcons'),
        ('combat', 'combatIcons'),
        ('agility', 'agilityIcons'),
    ]:
        val = _try_int(card.front.get(stat, ''))
        if val is not None:
            notes[sced_key] = val

    health = _try_int(card.front.get('health'))
    if health is not None:
        notes['health'] = health

    sanity = _try_int(card.front.get('sanity'))
    if sanity is not None:
        notes['sanity'] = sanity

    victory = _try_int(card.front.get('victory', ''))
    if victory is not None:
        notes['victory'] = victory

    if 'Hidden.' in card.front.get('text'):
        notes['hidden'] = True

    loc_front = _sced_location_data(card.front)
    if loc_front:
        notes['locationBack'] = loc_front

    loc_back = _sced_location_data(card.back)
    if loc_back:
        notes['locationFront'] = loc_back

    return notes


def build_gm_notes_string(card):
    """Return build_gm_notes(card) serialised as a compact JSON string."""
    return json.dumps(build_gm_notes(card))
