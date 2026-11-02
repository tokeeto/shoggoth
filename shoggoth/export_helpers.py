"""
Build SCED metadata for Tabletop Simulator card exports.
"""
import json
import re

from shoggoth.card import base_class

TTS_USES_MAP = {
    "supplies": "Supply",
    "bounties": "Bounty",
}

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
    'mini_investigator': 'Minicard',
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
    'head': 'Head',
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
    slots = face.get('slots', [face.get('slot', '')])
    sced = [_SLOT_TO_SCED.get(s.lower(), s) for s in slots if s]
    return '|'.join(sced) if sced else None


def _sced_location_data(face):
    """Build the locationFront/locationBack sub-dict for a location face."""
    data = {}

    if face.get('connection'):
        data['icons'] = face.get('connection', '').replace('_a', 'A')

    if face.get('connections'):
        connections = [c.replace('_a', 'A') for c in face.get('connections')]
        try:
            data['connections'] = '|'.join(connections)
        except Exception:
            pass

    victory = face.get('victory')
    if victory:
        try:
            # Attempt direct conversion to number
            number = _try_int(victory)

            if number is None:
                # Use regex to find a number after a space
                match = re.search(r" (\d+)", victory)
                number = _try_int(match.group(1)) if match else None

            # Write victory data if number was successfully detected
            if number is not None:
                data['victory'] = number

        except (ValueError, TypeError):
            pass

    clues = face.get('clues')
    if clues:
        count, per = parse_per_value(clues)
        if count is not None:
            data['uses'] = [{
                "type": "Clue",
                "token": "clue",
                "countPerInvestigator" if per else "count": count,
            }]
    return data or None


def _try_int(value):
    """Convert value to int if possible, else return None."""
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def parse_per_value(value):
    """
    Removes <per> from a string, then returns the numeric value of the remainder
    and whether <per> was actually present.
    """
    if not value:
        return None, False

    value = str(value)
    per = '<per>' in value
    value = value.replace('<per>', '')
    return _try_int(value), per


def build_gm_notes(card):
    """
    Build the SCED GMNotes metadata dict for a card.

    Returns a dict suitable for JSON-serialising into the TTS GMNotes field.
    """
    front_type = card.card_type
    notes = {}

    # special handling for ID since the TTS mod uses that to match mini-card and investigator
    if front_type == 'mini_investigator':
        notes['id'] = card.get('investigator_id', "00000") + "-m"
        notes['shoggoth'] = card.id
    else:
        notes['id'] = card.id

    notes['type'] = _TYPE_TO_SCED.get(front_type, front_type)

    # class / faction
    classes = card.front.get('classes', [])
    if isinstance(classes, str):
        classes = {base_class(c.strip().lower()) for c in classes.split(',') if c}
    else:
        classes = {base_class(str(c).strip().lower()) for c in classes if c}

    if front_type in _ENCOUNTER_TYPES:
        notes['class'] = 'Mythos'
    elif classes:
        sced_classes = [_CLASS_TO_SCED.get(c, c.title()) for c in classes if c]
        notes['class'] = '|'.join(sced_classes)

    # weakness detection via class field
    if 'weakness' in classes:
        notes['weakness'] = True
    if 'basic weakness' in classes:
        notes['weakness'] = True
        notes['basicWeaknessCount'] = card.amount

    # traits (stored as "Trait. Trait." string)
    traits = card.front.get('traits', '')
    if traits:
        notes['traits'] = traits

    # text-based properties
    front_text = card.front.get('text', '')
    if 'Permanent.' in front_text:
        notes['permanent'] = True
    if 'Hidden.' in front_text:
        notes['hidden'] = True

    # slots
    slot = _sced_slot(card.front)
    if slot:
        notes['slot'] = slot

    # skill icons
    notes.update(_sced_icon_counts(card.front))

    # investigator stats
    for stat, sced_key in [
        ('willpower', 'willpowerIcons'),
        ('intellect', 'intellectIcons'),
        ('combat', 'combatIcons'),
        ('agility', 'agilityIcons'),
    ]:
        val = _try_int(card.front.get(stat))
        if val is not None:
            notes[sced_key] = val

    # fields that are passed through as int
    for field in ('level', 'cost', 'health', 'sanity', 'victory'):
        value = _try_int(card.front.get(field))
        if value is not None:
            notes[field] = value

    # doom threshold
    if front_type == 'agenda':
        doom, per = parse_per_value(card.front.get('doom'))
        if doom is not None:
            notes['doomThresholdPerInvestigator' if per else 'doomThreshold'] = doom

    # clue threshold
    if front_type == 'act':
        clues, per = parse_per_value(card.front.get('clues'))
        if clues is not None:
            notes['clueThresholdPerInvestigator' if per else 'clueThreshold'] = clues

    # scenario reference card:
    if front_type == 'chaos':
        notes['tokens'] = build_token_data(card)

    # location data
    loc_front = _sced_location_data(card.front)
    if loc_front:
        notes['locationFront'] = loc_front

    loc_back = _sced_location_data(card.back)
    if loc_back:
        notes['locationBack'] = loc_back

    # uses data (Note: this assumes english and does not support multiple uses)
    try:
        match = re.match(r"Uses \((\d+) ([^)]+)\)\.", front_text)
        if match:
            count = int(match.group(1))
            raw_type = match.group(2)

            type_str = TTS_USES_MAP.get(raw_type, raw_type)
            if raw_type not in TTS_USES_MAP and raw_type.endswith("s"):
                type_str = raw_type[:-1]

            notes['uses'] = [{
                "count": count,
                "type": type_str.capitalize(),
                "token": "resource",
            }]
    except Exception:
        pass

    # load manually defined metadata if possible
    manual_metadata = card.get_meta('tts_metadata')
    if isinstance(manual_metadata, dict):
        notes.update(manual_metadata)

    return notes


def get_modifier(text):
    """
    Extract the numeric modifier from the beginning of the text.

    Examples:
        "-2 abc" -> -2
        "-8. If .." -> -8
        "-X. Do something" -> -999
    """
    text = text.strip()

    if text.startswith("-X"):
        return -999

    match = re.match(r"(-?\d+)", text)
    if match:
        return int(match.group(1))

    return 0


def build_token_data(data):
    token_data = {
        "front": {},
        "back": {},
    }

    for side in ("front", "back"):
        for entry in data.get(side, {}).get("entries", []):
            text = entry.get("text", "")
            modifier = get_modifier(text)

            tokens = entry.get("token", [])
            if not isinstance(tokens, list):
                tokens = [tokens]

            for token_id in tokens:
                token_name = token_id.replace("_", " ").title()

                token_data[side][token_name] = {
                    "description": text,
                    "modifier": modifier,
                }

    return token_data


def build_gm_notes_string(card):
    """Return build_gm_notes(card) serialised as a compact JSON string."""
    return json.dumps(build_gm_notes(card))
