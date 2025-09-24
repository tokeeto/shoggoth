import json
import os
import shoggoth
from shoggoth import files
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
    "ObjectStates": []
}

card_template = {
    "CardID": 552100,
    "CustomDeck": {
        "5521": {
            "BackIsHidden": True,
            "BackURL": "https://steamusercontent-a.akamaihd.net/ugc/2342503777940352139/A2D42E7E5C43D045D72CE5CFC907E4F886C8C690/",
            "FaceURL": "",
            "NumHeight": 1,
            "NumWidth": 1,
            "Type": 0,
            "UniqueBack": True
        }
    },
    "Description": "Card 1",
    "GMNotes_path": None,
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

def get_image_path(card):
    export = Path(shoggoth.app.current_project.file_path).parent / f'export_of_{shoggoth.app.current_project.name}' / f'{card.name}_front.png'
    return export


def card_to_tts(card):
    data = deepcopy(card_template)
    data['CustomDeck']['5521']['FaceURL'] = f'file:///{get_image_path(card)}'
    data['Description'] = card.name
    data['GUID'] = card.id
    data['Tags'] = ["Asset", "PlayerCard"]
    return data


def export_card(card):
    wrapper = deepcopy(wrapper_template)
    data = card_to_tts(card)
    wrapper['ObjectStates'].append(data)

    if files.tts_dir:
        output_path = files.tts_dir / f"{card.name}.json"
    else:
        output_path = Path(shoggoth.app.current_project.file_path).parent / f"{card.name}.json"

    with open(output_path, 'w') as file:
        json.dump(wrapper, file, indent=4)


def export_campaign(expansion):
    wrapper = deepcopy(wrapper_template)
    for encounter in expansion.encounter_sets:
        encounter_wrapper = deepcopy(wrapper_template)
        for card in encounter.cards:
            encounter_wrapper['ObjectStates'].append(card_to_tts(card))
        wrapper['ObjectStates'].append(encounter_wrapper)

    if files.tts_dir:
        output_path = files.tts_dir / f"{shoggoth.app.current_project.name} campaign.json"
    else:
        output_path = Path(shoggoth.app.current_project.file_path).parent / f"{shoggoth.app.current_project.name} campaign.json"

    with open(output_path, 'w') as file:
        json.dump(wrapper, file, indent=4)


def export_player_cards(cards):
    wrapper = deepcopy(wrapper_template)
    for card in cards:
        wrapper['ObjectStates'].append(card_to_tts(card))

    if files.tts_dir:
        output_path = files.tts_dir / f"{shoggoth.app.current_project.name} player cards.json"
    else:
        output_path = Path(shoggoth.app.current_project.file_path).parent / f"{shoggoth.app.current_project.name} player cards.json"

    with open(output_path, 'w') as file:
        json.dump(wrapper, file, indent=4)
