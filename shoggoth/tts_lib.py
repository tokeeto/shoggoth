import json
import shoggoth
from shoggoth import files
from shoggoth.export_helpers import build_gm_notes_string
from copy import deepcopy
from pathlib import Path
from shoggoth import renderer
from shoggoth import tts_sync

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
}


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

    data['Description'] = card.name
    data['Nickname'] = card.name
    data['CardID'] = id * 100
    data['GMNotes'] = build_gm_notes_string(card)
    return data


def export_all(project, image_folder, sync=True):
    wrapper = deepcopy(wrapper_template)
    current_id = 6000
    for encounter in project.encounter_sets:
        encounter_wrapper = deepcopy(encounter_template)
        wrapper['ObjectStates'][0]['ContainedObjects'].append(encounter_wrapper)
        encounter_wrapper["DeckIDs"] = []
        encounter_wrapper['Nickname'] = encounter.name
        for card in encounter.cards:
            for index, variant in enumerate(card.versions):
                encounter_wrapper["ContainedObjects"].append(card_to_tts(card, current_id, index, image_folder))
                current_id += 1
                encounter_wrapper["DeckIDs"].append(current_id)
    for card in project.player_cards:
        for variant in range(card.amount):
            wrapper['ObjectStates'][0]['ContainedObjects'].append(card_to_tts(card, current_id, variant, image_folder))
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
        encounter_wrapper["DeckIDs"] = []
        encounter_wrapper['Nickname'] = encounter.name
        for card in encounter.cards:
            for index, variant in enumerate(card.versions):
                encounter_wrapper["ContainedObjects"].append(card_to_tts(card, current_id, index, image_folder))
                current_id += 1
                encounter_wrapper["DeckIDs"].append(current_id)

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
        for variant in range(card.amount):
            wrapper['ObjectStates'][0]['ContainedObjects'].append(card_to_tts(card, current_id, variant, image_folder))
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
