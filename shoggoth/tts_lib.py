import json
from logging import currentframe
import os
import shoggoth
from shoggoth import files
from shoggoth.export_helpers import build_gm_notes_string
from copy import deepcopy
from pathlib import Path

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
    "GUID": "e0005d"
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
    "GUID": "427b4e28",
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
  "GUID": "300fcc",
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

def get_image_path(card, side, number, image_folder):
    return image_folder / f'{card.id}_{side}_{number}.webp'


def card_to_tts(card, id, number, image_folder):
    print('1')
    data = deepcopy(card_template)
    data['CustomDeck'][id] = deepcopy(inner_card_template)
    print('2')
    data['Tags'] = []
    if card.front.get('type', '') == 'player':
        data['Tags'].append('PlayerCard')
        data['CustomDeck'][id]['FaceURL'] = 'https://steamusercontent-a.akamaihd.net/ugc/2038486699957628515/8202EA3F06FDDD807A34BD6F62FE2E0A0723B8CD/'
    elif card.front.get('type', '') == 'encounter':
        data['Tags'].append('EncounterCard')
        data['CustomDeck'][id]['FaceURL'] = 'https://steamusercontent-a.akamaihd.net/ugc/2038486699957628515/8202EA3F06FDDD807A34BD6F62FE2E0A0723B8CD/'
    else:
        data['CustomDeck'][id]['FaceURL'] = f'file:///{get_image_path(card, 'front', number, image_folder)}'
    print('3')

    if card.back.get('type', '') == 'player':
        data['Tags'].append('PlayerCard')
        data['CustomDeck'][id]['BackURL'] = 'https://steamusercontent-a.akamaihd.net/ugc/2038486699957628515/8202EA3F06FDDD807A34BD6F62FE2E0A0723B8CD/'
    elif card.back.get('type', '') == 'encounter':
        data['Tags'].append('EncounterCard')
        data['CustomDeck'][id]['BackURL'] = 'https://steamusercontent-a.akamaihd.net/ugc/2038486699957628515/8202EA3F06FDDD807A34BD6F62FE2E0A0723B8CD/'
    else:
        data['CustomDeck'][id]['BackURL'] = f'file:///{get_image_path(card, 'back', number, image_folder)}'
    print('4')

    # type tags
    if 'location' in (card.front.get('type', ''), card.back.get('type', '')):
        data['Tags'].append('Location')
    if 'asset' in (card.front.get('type', ''), card.back.get('type', '')):
        data['Tags'].append('Asset')
    if 'Act' in (card.front.get('type', ''), card.back.get('type', '')):
        data['Tags'].append('Act')
    if 'Agenda' in (card.front.get('type', ''), card.back.get('type', '')):
        data['Tags'].append('Agenda')
    print('5')
    print(card.name, card.id)

    data['Description'] = card.name
    data['Nickname'] = card.name
    data['GUID'] = card.id
    data['CardID'] = id * 100
    print(card.name, card.id)
    data['GMNotes'] = build_gm_notes_string(card)
    print('6')
    return data


def export_all(project, image_folder):
    pass


def export_card(card, image_folder):
    wrapper = deepcopy(wrapper_template)
    data = card_to_tts(card, 8000, 0, image_folder)
    wrapper['ObjectStates'].append(data)

    if files.tts_dir:
        output_path = files.tts_dir / f"{card.name}.json"
    else:
        output_path = Path(shoggoth.app.current_project.file_path).parent / f"{card.name}.json"

    with open(output_path, 'w') as file:
        json.dump(wrapper, file, indent=4)


def export_campaign(project, image_folder):
    print('exporting campaign', project.encounter_sets)
    wrapper = deepcopy(wrapper_template)
    current_id = 6000
    for encounter in project.encounter_sets:
        encounter_wrapper = deepcopy(encounter_template)
        wrapper['ObjectStates'][0]['ContainedObjects'].append(encounter_wrapper)
        encounter_wrapper["DeckIDs"] = []
        encounter_wrapper['Nickname'] = encounter.name
        print('sets', len(encounter.cards))
        for card in encounter.cards:
            print('encounter cards', card.amount, card.name, card.versions)
            for variant in card.versions:
                print('variants')
                encounter_wrapper["ContainedObjects"].append(card_to_tts(card, current_id, variant, image_folder))
                print('variants 2')
                current_id += 1
                encounter_wrapper["DeckIDs"].append(current_id)
                print('variants 3')

    print('still going strong')
    return_status = 0
    if files.tts_dir:
        return_status = 1
        output_path = files.tts_dir / f"{shoggoth.app.current_project.name} campaign.json"
    else:
        output_path = Path(shoggoth.app.current_project.file_path).parent / f"{shoggoth.app.current_project.name} campaign.json"

    print('Writing TTS to:', str(output_path))
    with open(output_path, 'w') as file:
        json.dump(wrapper, file, indent=4)
    print('still going strong')

    return return_status, output_path


def export_player_cards(cards, image_folder):
    wrapper = deepcopy(wrapper_template)
    current_id = 6000
    for card in cards:
        for variant in range(card.amount):
            wrapper['ObjectStates'].append(card_to_tts(card, current_id, variant, image_folder))
            current_id += 1

    return_status = 0
    if files.tts_dir:
        return_status = 1
        output_path = files.tts_dir / f"{shoggoth.app.current_project.name} player cards.json"
    else:
        output_path = Path(shoggoth.app.current_project.file_path).parent / f"{shoggoth.app.current_project.name} player cards.json"

    with open(output_path, 'w') as file:
        json.dump(wrapper, file, indent=4)

    return return_status, output_path
