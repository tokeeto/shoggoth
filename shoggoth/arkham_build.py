"""
arkham.build export - exports a Shoggoth project to arkham.build format

Schema reference: https://github.com/arkham-build/fan-made-content/blob/main/schemas/project.schema.json
"""
import datetime
from shoggoth.export_helpers import (
    get_card_export_type, get_skill_icons, parse_slot,
    is_player_card, is_investigator_card
)


def export_project(project):
    """
    Export a full Shoggoth project to arkham.build format.

    Returns a dict matching the arkham.build project schema.
    """
    # TODO: These fields should be editable in a project settings UI
    # - author: Currently uses project author field
    # - banner_url: Image URL for project banner
    # - external_link: Link to project website/documentation
    # - status: Project status (draft/alpha/beta/complete/final)
    # - tags: Comma-separated tags for searchability
    # - types: What content types the project includes
    # - url: URL where the project JSON is hosted

    data = {
        "meta": {
            # Required fields
            "author": project.data.get('author', 'Unknown'),  # TODO: Add author field to project editor
            "code": project.data.get('code', project.id),
            "language": project.data.get('language', 'en'),  # TODO: Add language field to project editor
            "name": project.name,

            # Optional fields
            "description": project.data.get('description', ''),
            "date_updated": datetime.date.today().isoformat(),
            "banner_url": project.data.get('banner_url'),  # TODO: Add to project editor
            "external_link": project.data.get('website_url'),  # TODO: Add to project editor
            "generator": "Shoggoth",
            "status": project.data.get('status', 'draft'),  # TODO: Add status dropdown to project editor
            "tags": project.data.get('tags', ''),  # TODO: Add tags field to project editor
            "types": _determine_project_types(project),
            "url": project.data.get('hosting_url'),  # TODO: Add to project editor
        },
        "data": {
            "cards": [],
            "encounter_sets": [],
            "packs": [],  # TODO: Determine if packs are needed
        }
    }

    # Export encounter sets
    for encounter_set in project.encounter_sets:
        data["data"]["encounter_sets"].append({
            "code": encounter_set.data.get('code', encounter_set.id),
            "name": encounter_set.name,
            # TODO: Add icon_url field to encounter set editor (hosted icon image)
            "icon_url": encounter_set.data.get('icon_url'),
        })

    # Export all cards
    position = 1
    for card in project.cards:
        card_data = _export_card(card, project, position)
        if card_data:
            data["data"]["cards"].append(card_data)
            position += 1

    return data


def _determine_project_types(project):
    """Determine what content types the project contains"""
    types = []

    has_investigators = False
    has_player_cards = False
    has_encounter = False

    for card in project.cards:
        if is_investigator_card(card):
            has_investigators = True
        elif is_player_card(card):
            has_player_cards = True
        else:
            has_encounter = True

    if has_investigators:
        types.append("investigators")
    if has_player_cards:
        types.append("player_cards")
    if has_encounter or project.encounter_sets:
        types.append("campaign")
        types.append("scenario")

    return types if types else ["campaign"]


def _export_card(card, project, position):
    """Export a single card to arkham.build format"""
    front = card.front
    back = card.back

    export_info = get_card_export_type(card)
    skill_icons = get_skill_icons(front)

    # Determine pack code
    # TODO: Add pack_code field to project or use project code
    pack_code = project.data.get('code', project.id)

    # Determine encounter code if applicable
    encounter_code = None
    if card.encounter:
        encounter_code = card.encounter.data.get('code', card.encounter.id)

    card_data = {
        # Required fields
        "code": card.data.get('code', card.id),
        "faction_code": export_info['faction_code'],
        "name": card.name,
        "pack_code": pack_code,
        "position": position,
        "quantity": card.data.get('amount', 1),
        "type_code": export_info['type_code'],

        # Optional faction fields
        "faction2_code": export_info['faction2_code'],
        "faction3_code": export_info['faction3_code'],

        # Card properties
        "double_sided": export_info['double_sided'],
        "subname": front.get('subtitle', ''),
        "traits": front.get('traits', ''),
        "text": _convert_text(front.get('text', '')),
        "flavor": front.get('flavor_text', ''),
        "illustrator": front.get('illustrator', ''),
        "is_unique": '<unique>' in front.get('title', '') or '<unique>' in back.get('title', ''),

        # Skill icons
        **skill_icons,

        # Cost and XP
        "cost": _safe_int(front.get('cost')),
        "xp": _safe_int(front.get('level')),

        # Slot
        "slot": parse_slot(front),

        # Encounter card fields
        "encounter_code": encounter_code,
        "encounter_position": _safe_int(card.data.get('encounter_number', '').split('-')[0] if card.data.get('encounter_number') else None),

        # Health/Sanity (for investigators and some assets)
        "health": _safe_int(front.get('health')),
        "sanity": _safe_int(front.get('sanity')),

        # Enemy stats
        "enemy_fight": _safe_int(front.get('attack')),
        "enemy_evade": _safe_int(front.get('evade')),
        "enemy_damage": _safe_int(front.get('damage')),
        "enemy_horror": _safe_int(front.get('horror')),

        # Location stats
        "shroud": _safe_int(front.get('shroud')),
        "clues": _safe_int(front.get('clues')),
        "clues_fixed": front.get('clues_fixed', False),

        # Act/Agenda stats
        "doom": _safe_int(front.get('doom')),
        "stage": _safe_int(front.get('stage')),

        # Victory/Vengeance
        "victory": _safe_int(front.get('victory')),
        "vengeance": _safe_int(front.get('victory')),

        # Keywords
        "permanent": 'Permanent.' in front.get('text', ''),
        "exceptional": 'Exceptional.' in front.get('text', ''),
        "myriad": 'Myriad.' in front.get('text', ''),
        "hidden": 'Hidden.' in front.get('text', ''),

        # Deck building
        "deck_limit": front.get('amount'),

        # TODO: These need UI support in the card editor
        # "deck_options": back.get('deck_options'),  # JSON string for investigator deck building
        # "deck_requirements": front.get('deck_requirements'),  # JSON string
        # "restrictions": front.get('restrictions'),  # Investigator restrictions
        # "bonded_to": front.get('bonded_to'),  # Bonded card code
        # "tags": front.get('tags', ''),  # Card tags for search

        # TODO: Image URLs need to be generated/hosted elsewhere
        "image_url": card.data.get('image_url'),
        "thumbnail_url": card.data.get('thumbnail_url'),
    }

    # Add back side info for double-sided cards
    if export_info['double_sided']:
        card_data.update({
            "back_name": back.get('name', ''),
            "back_text": _convert_text(back.get('text', '')),
            "back_flavor": back.get('flavor_text', ''),
            "back_traits": back.get('traits', ''),
            "back_illustrator": back.get('illustrator', ''),
            # TODO: Back image URLs
            "back_image_url": card.data.get('back_image_url'),
            "back_thumbnail_url": card.data.get('back_thumbnail_url'),
        })

        # For locations, include back-specific stats
        if export_info['type_code'] == 'location':
            card_data["back_link"] = back.get('connection', '')

    # Add customization options if present
    if front.get('type') == 'customizable':
        entries = front.get('entries', [])
        if entries:
            card_data["customization_options"] = _format_customization_options(entries)
            card_data["customization_text"] = _format_customization_text(entries)

    # Clean up None values
    card_data = {k: v for k, v in card_data.items() if v is not None and v != ''}

    return card_data


def _convert_text(text):
    """
    Convert Shoggoth text formatting to arkham.build format.

    TODO: This may need more comprehensive conversion of tags.
    """
    if not text:
        return ''

    return text


def _format_customization_options(entries):
    """
    Format customization entries for arkham.build.

    entries is a list of [xp_cost, name, text]
    """
    # TODO: arkham.build may expect a specific JSON format
    options = []
    for i, entry in enumerate(entries):
        if len(entry) >= 3:
            options.append({
                "xp": entry[0],
                "text_change": "append",  # TODO: Determine actual text_change type
            })
    return options if options else None


def _format_customization_text(entries):
    """Format customization text for display"""
    lines = []
    for entry in entries:
        if len(entry) >= 3:
            xp, name, text = entry[0], entry[1], entry[2]
            lines.append(f"{'☐' * xp} {name}. {text}")
    return '\n'.join(lines) if lines else None


def _safe_int(value):
    """Safely convert a value to int, returning None if not possible"""
    if value is None or value == '' or value == 'None':
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
