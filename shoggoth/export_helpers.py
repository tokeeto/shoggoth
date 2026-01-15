"""
Export helpers - shared utilities for exporting cards to various formats
"""

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


def get_skill_icons(face):
    """
    Extract skill icons from a face.

    Returns a dict with:
        - skill_willpower: int
        - skill_intellect: int
        - skill_combat: int
        - skill_agility: int
        - skill_wild: int
    """
    icons = face.get('icons', [])

    counts = {
        'skill_willpower': 0,
        'skill_intellect': 0,
        'skill_combat': 0,
        'skill_agility': 0,
        'skill_wild': 0,
    }

    icon_mapping = {
        'willpower': 'skill_willpower',
        'intellect': 'skill_intellect',
        'combat': 'skill_combat',
        'agility': 'skill_agility',
        'wild': 'skill_wild',
    }

    for icon in icons:
        if icon in icon_mapping:
            counts[icon_mapping[icon]] += 1

    return counts


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
