import json
import shoggoth
from shoggoth import files
from shoggoth.export_helpers import build_gm_notes_string
from copy import deepcopy
from pathlib import Path
import re
from shoggoth import renderer
from shoggoth import tts_sync

# TTS requires the untrimmed canvas at an exact multiple of 750x1050, never
# with bleed (trim=None skips the FFG/MTG trim crop entirely -- see
# renderer.TRIM_SIZES). Do NOT reuse the 'mtg' trim here: it crops to
# 1500x2079 at full scale, which is not a valid TTS card image size.
TTS_IMAGE_SIZE = {'width': 750, 'height': 1050, 'bleed': 36, 'trim': None}
TTS_IMAGE_FORMAT = 'webp'
TTS_IMAGE_QUALITY = 95

wrapper_template = {
    "SaveName": "",
    "Date": "",
    "VersionNumber": "",
    "GameMode": "",
    "GameType": "",
    "GameComplexity": "",
    "Tags": [],
    "Gravity": 0.5,
    "PlayArea": 0.5,
    "Table": "",
    "Sky": "",
    "Note": "",
    "TabStates": {},
    "LuaScript": "",
    "LuaScriptState": "",
    "XmlUI": "",
    "ObjectStates": [{
        "Name": "Bag",
        "Nickname": "Shoggoth bag",
        "Transform": {
            "posX": 0.0,
            "posY": 0.0,
            "posZ": 0.0,
            "rotX": 0.0,
            "rotY": 270.0,
            "rotZ": 0.0,
            "scaleX": 1.0,
            "scaleY": 1.0,
            "scaleZ": 1.0
        },
        "Locked": False,
        "Grid": True,
        "Snap": True,
        "IgnoreFoW": False,
        "MeasureMovement": False,
        "DragSelectable": True,
        "Autoraise": True,
        "Sticky": True,
        "Tooltip": True,
        "GridProjection": False,
        "Hands": True,
        "DeckIDs": [],
        "ContainedObjects": []
    }],
}

encounter_template = {
    "Name": "Bag",
    "Nickname": "",
    "Transform": {
        "posX": 0.0,
        "posY": 0.0,
        "posZ": 0.0,
        "rotX": 0.0,
        "rotY": 270.0,
        "rotZ": 0.0,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "scaleZ": 1.0
    },
    "Locked": False,
    "Grid": True,
    "Snap": True,
    "IgnoreFoW": False,
    "MeasureMovement": False,
    "DragSelectable": True,
    "Autoraise": True,
    "Sticky": True,
    "Tooltip": True,
    "GridProjection": False,
    "Hands": True,
    "ContainedObjects": [],
}

inner_card_template = {
    "BackIsHidden": True,
    "BackURL": "https://steamusercontent-a.akamaihd.net/ugc/2342503777940352139/A2D42E7E5C43D045D72CE5CFC907E4F886C8C690/",
    "FaceURL": "",
    "NumHeight": 1,
    "NumWidth": 1,
    "Type": 0,
    "UniqueBack": True
}

card_template = {
    "CardID": 552100,
    "CustomDeck": {},
    "Description": "Card 1",
    "GMNotes": "",
    "Name": "Card",
    "Nickname": "A card",
    "Tags": ["Asset", "PlayerCard"],
    "Transform": {
        "posX": 0,
        "posY": 0,
        "posZ": 0,
        "rotX": 0,
        "rotY": 270,
        "rotZ": 0,
        "scaleX": 1,
        "scaleY": 1,
        "scaleZ": 1
    }
}

campaign_box_template = {
  "AltLookAngle": {
    "x": 0,
    "y": 0,
    "z": 0
  },
  "Autoraise": True,
  "ColorDiffuse": {
    "a": 0.27451,
    "b": 1,
    "g": 1,
    "r": 1
  },
  "CustomMesh": {
    "CastShadows": True,
    "ColliderURL": "",
    "Convex": True,
    "CustomShader": {
      "FresnelStrength": 0,
      "SpecularColor": {
        "b": 1,
        "g": 1,
        "r": 1
      },
      "SpecularIntensity": 0,
      "SpecularSharpness": 2
    },
    "DiffuseURL": "https://steamusercontent-a.akamaihd.net/ugc/2038486699957628515/8202EA3F06FDDD807A34BD6F62FE2E0A0723B8CD/",
    "MaterialIndex": 3,
    "MeshURL": "https://steamusercontent-a.akamaihd.net/ugc/62583916778515295/AFB8F257CE1E4973F4C06160A2E156C147AEE1E3/",
    "NormalURL": "",
    "TypeIndex": 0
  },
  "Description": "",
  "DragSelectable": True,
  "GMNotes": "{\n  \"filename\": \"the_scarlet_keys\"}",
  "Grid": True,
  "GridProjection": False,
  "Hands": False,
  "HideWhenFaceDown": False,
  "IgnoreFoW": False,
  "LayoutGroupSortIndex": 0,
  "Locked": False,
  "LuaScript": "require(\"core/DownloadBox\")",
  "LuaScriptState": "",
  "MeasureMovement": False,
  "Name": "Custom_Model",
  "Nickname": "The Scarlet Keys",
  "Snap": True,
  "Sticky": True,
  "Tags": [
    "CampaignBox"
  ],
  "Tooltip": True,
  "Transform": {
    "posX": 60,
    "posY": 1.481,
    "posZ": -63.33,
    "rotX": 0,
    "rotY": 270,
    "rotZ": 0,
    "scaleX": 1,
    "scaleY": 0.14,
    "scaleZ": 1
  },
  "Value": 0,
  "XmlUI": ""
}

DEFAULT_IMAGES = {
    'player': 'https://steamusercontent-a.akamaihd.net/ugc/2342503777940352139/A2D42E7E5C43D045D72CE5CFC907E4F886C8C690/',
    'encounter': 'https://steamusercontent-a.akamaihd.net/ugc/2342503777940351785/F64D8EFB75A9E15446D24343DA0A6EEF5B3E43DB/',
    'upgradesheet': 'https://steamusercontent-a.akamaihd.net/ugc/1814412497119682452/BD224FCE1980DBA38E5A687FABFD146AA1A30D0E/',
}

TYPE_TAG_MAP = {
    'location': 'Location',
    'asset': 'Asset',
    'act': 'Act',
    'agenda': 'Agenda',
    'chaos': 'ScenarioReference',
    'player': 'PlayerCard',
    'encounter': 'ScenarioCard',
    'investigator': 'Investigator',
    'mini_investigator': 'Minicard',
}


def remove_formatting_tags(text: str) -> str:
    return re.sub(r"</?[^>]+>", "", text)


def card_to_tts(card, id, number, image_folder):
    data = deepcopy(card_template)
    data['CustomDeck'][id] = deepcopy(inner_card_template)
    data['Tags'] = []

    front_type = card.front.get('type', '').lower()
    back_type = card.back.get('type', '').lower()

    expected_front, expected_back = renderer.CardRenderer.expected_export_paths(card, image_folder, separate_versions=False, include_backs=True, format='webp')

    # set the front / back image
    data['CustomDeck'][id]['FaceURL'] = DEFAULT_IMAGES.get(front_type, f'file:///{expected_front}')
    data['CustomDeck'][id]['BackURL'] = DEFAULT_IMAGES.get(back_type, f'file:///{expected_back}')

    # add tags based on type
    for card_type in {front_type, back_type}:
        tag = TYPE_TAG_MAP.get(card_type)
        if tag:
            data['Tags'].append(tag)

    # Handle rotated cards and cards with different orientation
    if card.front.get('orientation', 'vertical') == 'horizontal':
        data['Tags'].append('Sideways')
    if card.front.get('orientation', 'vertical') != card.back.get('orientation', 'vertical'):
        data['Tags'].append('DynamicAltView')

    # handling for horizontal cards (since they get scaled differently by TTS)
    if front_type in ['act', 'agenda', 'investigator']:
        data['Transform']['scaleX'] *= 0.8214 / 1.15
        data['Transform']['scaleZ'] *= 0.8214 / 1.15

    # handling for investigators (since they are larger in TTS for clarity)
    if front_type == 'investigator':
        data['Transform']['scaleX'] *= 1.15
        data['Transform']['scaleZ'] *= 1.15
    elif front_type == 'mini_investigator':
        data['Transform']['scaleX'] *= 0.6
        data['Transform']['scaleZ'] *= 0.6

    data['Description'] = card.get('subtitle')
    data['Nickname'] = remove_formatting_tags(card.name)
    data['CardID'] = id * 100
    data['GMNotes'] = build_gm_notes_string(card)
    return data


def _resolve_included_sets(project, encounter):
    """encounter.data['meta']['tts']['included_sets'] stores other encounter
    sets' *ids* (see ui/encounter_editor.py's "required sets" field), not
    EncounterSet objects -- resolve them, dropping any that no longer exist."""
    ids = encounter.data.get('meta', {}).get('tts', {}).get('included_sets', [])
    resolved = [project.get_encounter_set(i) for i in ids]
    return [es for es in resolved if es is not None]


def export_all(project, image_folder, sync=True):
    wrapper = deepcopy(wrapper_template)
    current_id = 6000
    for encounter in project.encounter_sets:
        encounter_wrapper = deepcopy(encounter_template)
        wrapper['ObjectStates'][0]['ContainedObjects'].append(encounter_wrapper)
        encounter_wrapper['DeckIDs'] = []
        encounter_wrapper['Nickname'] = encounter.name

        other_sets = _resolve_included_sets(project, encounter)
        for enc_set in [encounter] + other_sets:
            for card in enc_set.cards:
                for _ in range(card.amount):
                    encounter_wrapper['ContainedObjects'].append(card_to_tts(card, current_id, 0, image_folder))
                    current_id += 1
                    encounter_wrapper['DeckIDs'].append(current_id)

    for card in project.player_cards:
        wrapper['ObjectStates'][0]['ContainedObjects'].append(card_to_tts(card, current_id, 0, image_folder))
        current_id += 1

    return_status = 0
    if files.tts_dir:
        return_status = 1
        output_path = files.tts_dir / f"{shoggoth.app.current_project.name} combined.json"
    else:
        output_path = Path(shoggoth.app.current_project.file_path).parent / f"{shoggoth.app.current_project.name} combined.json"

    with open(output_path, 'w', encoding='utf-8') as file:
        json.dump(wrapper, file, indent=2)

    if sync:
        tts_sync.push_to_tts(wrapper)
    return return_status, output_path


def export_card(card, image_folder, sync=True):
    wrapper = deepcopy(wrapper_template)
    data = card_to_tts(card, 8000, 0, image_folder)
    wrapper['ObjectStates'].append(data)

    if files.tts_dir:
        output_path = files.tts_dir / f"{card.name}.json"
    else:
        output_path = Path(shoggoth.app.current_project.file_path).parent / f"{card.name}.json"

    with open(output_path, 'w', encoding='utf-8') as file:
        json.dump(wrapper, file, indent=2)
    if sync:
        tts_sync.push_to_tts(wrapper)


def export_campaign(project, image_folder, sync=True):
    wrapper = deepcopy(wrapper_template)
    current_id = 6000
    for encounter in project.encounter_sets:
        encounter_wrapper = deepcopy(encounter_template)
        wrapper['ObjectStates'][0]['ContainedObjects'].append(encounter_wrapper)
        encounter_wrapper['DeckIDs'] = []
        encounter_wrapper['Nickname'] = encounter.name

        other_sets = _resolve_included_sets(project, encounter)
        for enc_set in [encounter] + other_sets:
            for card in enc_set.cards:
                for _ in range(card.amount):
                    encounter_wrapper['ContainedObjects'].append(card_to_tts(card, current_id, 0, image_folder))
                    current_id += 1
                    encounter_wrapper['DeckIDs'].append(current_id)

    return_status = 0
    if files.tts_dir:
        return_status = 1
        output_path = files.tts_dir / f"{shoggoth.app.current_project.name} campaign.json"
    else:
        output_path = Path(shoggoth.app.current_project.file_path).parent / f"{shoggoth.app.current_project.name} campaign.json"

    with open(output_path, 'w', encoding='utf-8') as file:
        json.dump(wrapper, file, indent=2)

    if sync:
        tts_sync.push_to_tts(wrapper)
    return return_status, output_path


def export_player_cards(cards, image_folder, sync=True):
    wrapper = deepcopy(wrapper_template)
    current_id = 6000
    for card in cards:
        for _ in range(card.amount):
            wrapper['ObjectStates'][0]['ContainedObjects'].append(card_to_tts(card, current_id, 0, image_folder))
            current_id += 1

    return_status = 0
    if files.tts_dir:
        return_status = 1
        output_path = files.tts_dir / f"{shoggoth.app.current_project.name} player cards.json"
    else:
        output_path = Path(shoggoth.app.current_project.file_path).parent / f"{shoggoth.app.current_project.name} player cards.json"

    with open(output_path, 'w', encoding='utf-8') as file:
        json.dump(wrapper, file, indent=2)

    if sync:
        tts_sync.push_to_tts(wrapper)
    return return_status, output_path

def update_file(cards, image_folder, file_path_str):
    return_status = 0

    # ------------------------------------------------------------
    # Generate lookup map of cards
    # ------------------------------------------------------------

    id_to_card = {}

    image_id = 1
    for card in cards:
        for _ in range(card.amount):
            # special handling for ID since the TTS mod uses that to match mini-card and investigator
            card_id = card.id
            if card.front.get('type', '') == 'mini_investigator':
                card_id = card.get('investigator_id', "00000") + "-m"

            id_to_card[card_id] = card_to_tts(card, image_id, 0, image_folder)
            image_id += 1

    # ------------------------------------------------------------
    # Load existing file
    # ------------------------------------------------------------

    file_path = Path(file_path_str)
    with open(file_path, "r", encoding="utf-8") as f:
        file_data = json.load(f)

    # ------------------------------------------------------------
    # Recursively update objects
    # ------------------------------------------------------------

    def update_object(obj):
        """
        Recursively search a TTS object tree and replace cards
        whose metadata ID exists in id_to_card.

        Returns the updated object.
        """

        if not isinstance(obj, dict):
            return obj

        # --------------------------------------------------------
        # Check whether this object has a matching ID
        # --------------------------------------------------------

        gmnotes = obj.get("GMNotes")

        if gmnotes:
            try:
                metadata = json.loads(gmnotes)
            except (json.JSONDecodeError, TypeError):
                metadata = None

            if isinstance(metadata, dict):
                card_id = metadata.get("id")

                if card_id in id_to_card:
                    # Replace with newly generated card
                    new_obj = id_to_card[card_id].copy()

                    # Preserve the GUID of the existing object
                    old_guid = obj.get("GUID")
                    if old_guid is not None:
                        new_obj["GUID"] = old_guid

                    # Preserve the Transform (position / rotation / scale) of the existing object
                    old_transform = obj.get("Transform")
                    if old_transform is not None:
                        new_obj["Transform"] = old_transform

                    return new_obj

        # --------------------------------------------------------
        # Recursively process contained objects
        # --------------------------------------------------------

        contained_objects = obj.get("ContainedObjects")

        if isinstance(contained_objects, list):
            obj["ContainedObjects"] = [
                update_object(child)
                for child in contained_objects
            ]

        # --------------------------------------------------------
        # Recursively process states
        # --------------------------------------------------------

        state_objects = obj.get("States")

        if isinstance(state_objects, dict):
            obj["States"] = {
                state_key: update_object(state_object)
                for state_key, state_object in state_objects.items()
            }

        return obj

    # ------------------------------------------------------------
    # Start recursive traversal
    # ------------------------------------------------------------

    file_data = update_object(file_data)

    # ------------------------------------------------------------
    # Save updated file
    # ------------------------------------------------------------

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(file_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return return_status
