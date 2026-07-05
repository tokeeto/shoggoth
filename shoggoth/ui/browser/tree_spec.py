"""
Builders for the file browser's tree specification.

A "spec" is a plain dict describing one desired tree node: node_id, text,
type, data, icon, and children. FileBrowser builds specs for the desired
tree state and TreeSync diffs them against the live QTreeWidget.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImage, QPixmap

from shoggoth.files import overlay_dir
from shoggoth.i18n import tr


def make_inverted_icon(icon_path, project_file_path, size=16):
    """Load an icon; invert RGB on dark backgrounds, use as-is on light backgrounds."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPalette
    path = Path(icon_path)
    if not path.is_absolute():
        path = Path(project_file_path).parent / path
    if not path.exists():
        return None
    image = QImage(str(path))
    if image.isNull():
        return None
    image = image.convertToFormat(QImage.Format_ARGB32)
    app = QApplication.instance()
    if app and app.palette().color(QPalette.ColorRole.Window).lightness() < 128:
        image.invertPixels(QImage.InvertRgb)
    pixmap = QPixmap.fromImage(image).scaled(
        size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )
    return QIcon(pixmap)


def card_display_name(card, include_level=False):
    """Return the display name for a card node (without dirty indicator)."""
    if include_level and str(card.front.get('level', '0')) != '0':
        name = f'{card.name} ({card.front.get("level")})'
    else:
        name = card.name
    index = card.front.get('index')
    if index:
        name = f'{index} {name}'
    return name


def build_card_spec(card, include_level=False):
    """Build a specification for a card node"""
    display_name = card_display_name(card, include_level)

    # Add dirty indicator
    if card.dirty:
        display_name = '● ' + display_name

    return {
        'node_id': f'card:{card.id}',
        'text': display_name,
        'type': 'card',
        'data': card,
        'icon': None,
        'children': []
    }


def build_tree_spec(project):
    """Build a specification of the desired tree state for one project"""
    if not project:
        return None

    # Root node — translation projects get a distinct node_id and label
    node_id_path = getattr(project, '_node_id_path', project.file_path)
    translation = getattr(project, '_translation', None)
    label = (f"{translation.language} translation of {project['name']}"
             if translation else project['name'])

    root_spec = {
        'node_id': f'project:{node_id_path}',
        'text': label,
        'type': 'project',
        'data': project,
        'icon': None,
        'children': []
    }

    # Determine if we need campaign/player split
    has_encounters = bool(project.encounter_sets)
    has_player_cards = any(c for c in project.cards if not c.encounter)

    if has_encounters and has_player_cards:
        campaign_spec = {
            'node_id': f'category:campaign_cards:{project.file_path}',
            'text': tr('TREE_CAMPAIGN_CARDS'),
            'type': 'campaign_cards',
            'data': project,
            'icon': None,
            'children': []
        }
        player_spec = {
            'node_id': f'category:player_cards:{project.file_path}',
            'text': tr('TREE_PLAYER_CARDS'),
            'type': 'player_cards',
            'data': project,
            'icon': None,
            'children': []
        }
        root_spec['children'].append(campaign_spec)
        root_spec['children'].append(player_spec)
    else:
        campaign_spec = player_spec = root_spec

    # Add encounter sets
    for encounter_set in project.encounter_sets:
        e_icon = None
        if encounter_set.icon:
            e_icon = make_inverted_icon(encounter_set.icon, project.file_path)
        e_spec = {
            'node_id': f'encounter:{encounter_set.name}',
            'text': encounter_set.name,
            'type': 'encounter',
            'data': encounter_set,
            'icon': e_icon,
            'children': []
        }

        story_spec = {
            'node_id': f'category:{encounter_set.name}:story',
            'text': tr('TREE_STORY'),
            'type': 'category',
            'data': encounter_set,
            'icon': None,
            'children': []
        }
        location_spec = {
            'node_id': f'locations:{encounter_set.name}',
            'text': tr('TREE_LOCATIONS'),
            'type': 'locations',
            'data': encounter_set,
            'icon': None,
            'children': []
        }
        encounter_cat_spec = {
            'node_id': f'category:{encounter_set.name}:encounter',
            'text': tr('TREE_ENCOUNTER'),
            'type': 'category',
            'data': encounter_set,
            'icon': None,
            'children': []
        }
        # Add cards to appropriate categories
        for card in encounter_set.cards:
            card_spec = build_card_spec(card)

            if card.grouping == 'location':
                location_spec['children'].append(card_spec)
            elif card.grouping in ('treachery', 'enemy'):
                encounter_cat_spec['children'].append(card_spec)
            else:
                story_spec['children'].append(card_spec)

        story_spec['children'].sort(key=lambda s: s['text'].lower())
        location_spec['children'].sort(key=lambda s: s['text'].lower())
        encounter_cat_spec['children'].sort(key=lambda s: s['text'].lower())

        # If only encounter cards exist (no story or location), show cards directly
        if not story_spec['children'] and not location_spec['children']:
            e_spec['children'] = encounter_cat_spec['children']
        else:
            e_spec['children'] = [story_spec, location_spec, encounter_cat_spec]

        campaign_spec['children'].append(e_spec)

    # Add player cards
    class_labels = {
        'investigators': tr('TREE_INVESTIGATORS'),
        'seeker': tr('CLASS_SEEKER'),
        'rogue': tr('CLASS_ROGUE'),
        'guardian': tr('CLASS_GUARDIAN'),
        'mystic': tr('CLASS_MYSTIC'),
        'survivor': tr('CLASS_SURVIVOR'),
        'neutral': tr('CLASS_NEUTRAL'),
        'other': tr('CLASS_OTHER'),
    }
    classes_with_icons = {'guardian', 'seeker', 'rogue', 'mystic', 'survivor'}

    class_specs = {}
    for cls in ['investigators', 'seeker', 'rogue', 'guardian', 'mystic', 'survivor', 'neutral', 'other']:
        icon_path = None
        if cls in classes_with_icons:
            path = overlay_dir / f"class_symbol_{cls}.png"
            if path.exists():
                icon_path = str(path)

        class_spec = {
            'node_id': f'class:{cls}:{project.file_path}',
            'text': class_labels[cls],
            'type': 'category',
            'data': project,
            'class': cls,
            'icon': icon_path,
            'children': []
        }
        class_specs[cls] = class_spec

    investigator_specs = {}

    for card in project.player_cards:
        if group := card.data.get('investigator', False):
            if group not in investigator_specs:
                inv_spec = {
                    'node_id': f'investigator:{group}:{project.file_path}',
                    'text': group,
                    'type': 'category',
                    'data': project,
                    'investigator': group,
                    'icon': None,
                    'children': []
                }
                investigator_specs[group] = inv_spec
                class_specs['investigators']['children'].append(inv_spec)
            target_spec = investigator_specs[group]
        else:
            card_class = card.get_class() or 'other'
            target_spec = class_specs.get(card_class, class_specs['other'])

        card_spec = build_card_spec(card, include_level=True)
        target_spec['children'].append(card_spec)

    # Sort cards within each group
    for spec in list(investigator_specs.values()) + list(class_specs.values()):
        spec['children'].sort(key=lambda s: s['text'].lower())

    # Only add class nodes that have cards
    for cls in ['investigators', 'seeker', 'rogue', 'guardian', 'mystic', 'survivor', 'neutral', 'other']:
        if class_specs[cls]['children']:
            player_spec['children'].append(class_specs[cls])

    # Add guides
    if project.guides:
        guide_parent = {
            'node_id': f'category:guides:{project.file_path}',
            'text': tr('TREE_GUIDES'),
            'type': 'category',
            'data': project,
            'icon': None,
            'children': []
        }
        for guide in project.guides:
            guide_spec = {
                'node_id': f'guide:{guide.id}',
                'text': guide.name,
                'type': 'guide',
                'data': guide,
                'icon': None,
                'children': []
            }
            guide_parent['children'].append(guide_spec)
        root_spec['children'].append(guide_parent)

    return root_spec
