from os import makedirs, remove
from uuid import uuid4
import jpype
import jpype.imports
import json
import threading
from pathlib import Path

assert jpype.isJVMStarted

from ca.cgjennings.apps.arkham.project import ProjectUtilities
from ca.cgjennings.apps.arkham.project import Project
from resources import ResourceKit
from java.io import File
import java
from javax.imageio import ImageIO


front_types = {
    "Act.js": "act",
    "ActAssetStory.js": "act",
    "ActEnemy.js": "act",
    "ActLocation.js": "act",
    "ActPortrait.js": "act",
    "Agenda.js": "agenda",
    "AgendaAssetStory.js": "agenda",
    "AgendaEnemy.js": "agenda",
    "AgendaFrontPortrait.js": "agenda",
    "AgendaLocation.js": "agenda",
    "AgendaPortrait.js": "agenda",
    "AgendaTreachery.js": "agenda",
    "Asset.js": "asset",
    "AssetAsset.js": "asset",
    "AssetStory.js": "asset",
    "AssetStoryAsset.js": "asset",
    "AssetStoryEnemy.js": "asset",
    "AssetStoryPortrait.js": "asset",
    "Chaos.js": "chaos",
    "Concealed.js": "concealed",
    "Customizable.js": "customizable",
    "Enemy.js": "enemy",
    "EnemyEnemy.js": "enemy",
    "EnemyLocation.js": "enemy_location",
    "EnemyPortrait.js": "enemy",
    "Event.js": "event",
    "Investigator.js": "investigator",
    "InvestigatorStory.js": "investigator",
    "Key.js": "key",
    "Location.js": "location",
    "LocationLocation.js": "location",
    "Scenario.js": "scenario",
    "Skill.js": "skill",
    "StoryAsset.js": "story",
    "StoryChaos.js": "story",
    "StoryEnemy.js": "story",
    "StoryLocation.js": "story",
    "StoryStory.js": "story",
    "StoryTreachery.js": "story",
    "Treachery.js": "treachery",
    "TreacheryLocation.js": "treachery",
    "TreacheryPortrait.js": "treachery",
    "TreacheryStory.js": "treachery",
    "Ultimatum.js": "ultimatum",
    "WeaknessEnemy.js": "enemy",
    "WeaknessTreachery.js": "treachery",
    "MiniInvestigator.js": "mini",
}

back_types = {
    "Act.js": "act_back",
    "ActAssetStory.js": "asset",
    "ActEnemy.js": "enemy",
    "ActLocation.js": "location",
    "ActPortrait.js": "act_back",
    "Agenda.js": "agenda_back",
    "AgendaAssetStory.js": "asset",
    "AgendaEnemy.js": "enemy",
    "AgendaFrontPortrait.js": "agenda_back",
    "AgendaLocation.js": "location",
    "AgendaPortrait.js": "agenda_back",
    "AgendaTreachery.js": "treachery",
    "Asset.js": "player",
    "AssetAsset.js": "asset",
    "AssetStory.js": "story",
    "AssetStoryAsset.js": "asset",
    "AssetStoryEnemy.js": "enemy",
    "AssetStoryPortrait.js": "story",
    "Chaos.js": "chaos_back",
    "Concealed.js": "concealed_back",
    "Customizable.js": "customizable_back",
    "Enemy.js": "encounter",
    "EnemyEnemy.js": "enemy",
    "EnemyLocation.js": "location_back",
    "EnemyPortrait.js": "encounter",
    "Event.js": "player",
    "Investigator.js": "investigator_back",
    "InvestigatorStory.js": "investigator_back",
    "Key.js": "key_back",
    "Location.js": "location_back",
    "LocationLocation.js": "location",
    "Scenario.js": "scenario_back",
    "Skill.js": "player",
    "StoryAsset.js": "asset",
    "StoryChaos.js": "chaos",
    "StoryEnemy.js": "enemy",
    "StoryLocation.js": "location",
    "StoryStory.js": "story",
    "StoryTreachery.js": "treachery",
    "Treachery.js": "encounter",
    "TreacheryLocation.js": "location",
    "TreacheryPortrait.js": "encounter",
    "TreacheryStory.js": "story",
    "Ultimatum.js": "ultimatum_back",
    "WeaknessEnemy.js": "player",
    "WeaknessTreachery.js": "player",
    "MiniInvestigator.js": "mini_back",
}

PORTRAITS = {
    'Act.js': [ 'Portrait-Front', 'Collection-Both', 'Encounter-Both' ],
    'ActAssetStory.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'ActEnemy.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'ActLocation.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'ActPortrait.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Front', 'Encounter-Front' ],
    'AgendaEnemy.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'AgendaAssetStory.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'AgendaFrontPortrait.js': [ 'Portrait-Front', 'Collection-Both', 'Encounter-Both' ],
    'AgendaLocation.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'AgendaTreachery.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'Asset.js': [ 'Portrait-Front', 'Collection-Front' ],
    'AssetAsset.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Front' ],
    'AssetStoryAsset.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Front', 'Encounter-Front' ],
    'Chaos.js': [ 'Collection-Both', 'Encounter-Both' ],
    'Concealed.js': [ 'Portrait-Front' ],
    'AssetStoryPortrait.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Front', 'Encounter-Front' ],
    'Customizable.js': [ 'Collection-Front' ],
    'AssetStory.js': [ 'Portrait-Front', 'Collection-Front', 'Encounter-Front' ],
    'EnemyEnemy.js': [ 'Portrait-Both', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'MiniInvestigator.js': [ 'Portrait-Both' ],
    'Investigator.js': [ 'TransparentPortrait-Both', 'Portrait-Back', 'Collection-Front' ],
    'Enemy.js': [ 'Portrait-Front', 'Collection-Front', 'Encounter-Front' ],
    'GuideLetter.js': [ 'Portrait1-Front', 'Portrait2-Front' ],
    'EnemyLocation.js': [ 'Portrait-Both', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'EnemyPortrait.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Front', 'Encounter-Front' ],
    'StoryStory.js': [ 'Collection-Both', 'Encounter-Both' ],
    'InvestigatorStory.js': [ 'TransparentPortrait-Both', 'Portrait-Back', 'Collection-Front', 'Encounter-Both' ],
    'TreacheryStory.js': [ 'Portrait-Front', 'Collection-Both', 'Encounter-Both' ],
    'Guide75.js': [ 'Portrait1-Front', 'Portrait2-Front' ],
    'Key.js': [ 'Portrait-Both', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'LocationLocation.js': [ 'Portrait-Both', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'Scenario.js': [ 'Portrait', 'BackPortrait', 'Collection-Both', 'Encounter-Both' ],
    'Agenda.js': [ 'Portrait-Front', 'Collection-Both', 'Encounter-Both' ],
    'AgendaPortrait.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Front', 'Encounter-Front' ],
    'Divider.js': [ 'Encounter-Both' ],
    'TreacheryPortrait.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Front', 'Encounter-Front' ],
    'StoryLocation.js': [ 'BackPortrait-Back', 'Collection-Back', 'Encounter-Both' ],
    'Treachery.js': [ 'Portrait-Front', 'Collection-Front', 'Encounter-Front' ],
    'AssetStoryEnemy.js': [ 'Portrait-Front', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'StoryChaos.js': [ 'Collection-Back', 'Encounter-Both' ],
    'StoryTreachery.js': [ 'BackPortrait-Back', 'Collection-Back', 'Encounter-Both' ],
    'BoxCover.js': [ 'Portrait-Front', 'PortraitBottom-Front' ],
    'Ultimatum.js': [ 'Portrait', 'Collection', 'Encounter' ],
    'StoryAsset.js': [ 'BackPortrait-Back', 'Collection-Back', 'Encounter-Both' ],
    'TreacheryLocation.js': [ 'Portrait-Front', 'Collection-Front', 'Encounter-Front' ],
    'WeaknessTreachery.js': [ 'Portrait-Front', 'Collection-Front', 'Encounter-Front' ],
    'GuideA4.js': [ 'Portrait1-Front', 'Portrait2-Front' ],
    'Event.js': [ 'Portrait-Front', 'Collection-Front', 'Encounter-Both' ],
    'WeaknessEnemy.js': [ 'Portrait-Front', 'Collection-Front', 'Encounter-Front' ],
    'Skill.js': [ 'Portrait-Front', 'Collection-Front', 'Encounter-Both' ],
    'StoryEnemy.js': [ 'BackPortrait-Back', 'Collection-Back', 'Encounter-Both' ],
    'Location.js': [ 'Portrait-Both', 'BackPortrait-Back', 'Collection-Both', 'Encounter-Both' ],
    'PackCover.js': [ 'Portrait-Front' ],
}

def translate_text(value):
    # make sure javastrings are pystrings
    value = str(value)

    value = value.replace('<fullname>', '<name>')
    value = value.replace('<act>', '<action>')
    value = value.replace('<fre>', '<free>')
    value = value.replace('<rea>', '<reaction>')
    value = value.replace('<wil>', '<willpower>')
    value = value.replace('<int>', '<intellect>')
    value = value.replace('<agi>', '<agility>')
    value = value.replace('<com>', '<combat>')
    value = value.replace('<rog>', '<rogue>')
    value = value.replace('<see>', '<seeker>')
    value = value.replace('<sur>', '<survivor>')
    value = value.replace('<gua>', '<guardian>')
    value = value.replace('<mys>', '<mystic>')
    value = value.replace('<sku>', '<skull>')
    value = value.replace('<cul>', '<cultist>')
    value = value.replace('<tab>', '<tablet>')
    value = value.replace('<mon>', '<elder_thing>')
    value = value.replace('<eld>', '<elder_sign>')
    value = value.replace('<ten>', '<fail>')
    value = value.replace('<ble>', '<bless>')
    value = value.replace('<cur>', '<curse>')
    value = value.replace('<spa>', '<spawn>')
    value = value.replace('<vs>\n', '')
    value = value.replace('\n\n', '\n')

    return value

def get_portaits(card):
    script_name = card.getClassName().split("/")[-1]
    bindings = PORTRAITS.get(script_name)
    if not bindings:
        return None
    output = {}
    for index, name in enumerate(bindings):
        output[str(name)] = card.getPortrait(index)
    return output

def extract_images(card, collection, image_folder):
    print(f'extracting images from {card.getName()}')
    script_name = card.getClassName().split("/")[-1]
    bindings = PORTRAITS.get(script_name)
    if not bindings:
        return
    for index, name in enumerate(bindings):
        portrait = card.getPortrait(index)
        source = str(portrait.getSource())
        if source in collection['images']:
            continue
        collection['images'][source] = ''
        portrait_name = source.split('\\')[-1]
        if not portrait_name:
            portrait_name = source.split('/')[-1]
        portrait_format = portrait_name.split('.')[-1]
        new_path = image_folder / portrait_name
        i = 0
        while new_path.exists():
            new_path = image_folder / f'{i}_{portrait_name}'
            i += 1
            if i > 35:
                print(f'{card.getName()} failed to find suitable name for image {portrait_name}')
                continue
        collection['images'][source] = str(new_path)
        outputfile = File(str(new_path))
        ImageIO.write(portrait.getImage(), portrait_format, outputfile)

def determine_encounter_set(card) -> tuple[str|None, str|None]:
    portraits = get_portaits(card)
    if not portraits:
        return None, None
    for title in ('Encounter-Both', 'Encounter-Front', 'Encounter-Back'):
        if title not in portraits:
            continue
        encounter_set_path = str(portraits[title].getSource())
        path = encounter_set_path.split('/')[-1]
        # check for windows path
        if encounter_set_path == path:
            path = path.split('\\')[-1]
        return path, encounter_set_path
    return None, None


class JavaWriter(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, java.lang.String):
            return str(o)
        return super(o)


def run_import(project_path, output_path):
    PROJECT_FOLDER = Path(project_path)
    OUTPUT_FOLDER = Path(output_path)
    OUTPUT_FILE = OUTPUT_FOLDER / 'cards.json'
    IMAGE_FOLDER = OUTPUT_FOLDER / 'images'

    if not OUTPUT_FOLDER.exists():
        makedirs(OUTPUT_FOLDER)
    if not IMAGE_FOLDER.exists():
        makedirs(IMAGE_FOLDER)
    if OUTPUT_FILE.exists():
        remove(OUTPUT_FILE)

    card_files = []
    for root, dir, files in PROJECT_FOLDER.walk():
        card_files += [root/f for f in files if f.split('.')[-1] == 'eon' and f != 'deck.eon']
    print(f'Processing {len(card_files)} cards')

    collection = {
        "name": PROJECT_FOLDER.name,
        "encounter_sets": {},
        "cards": [],
        "images": {},
    }

    step = 0
    while step < len(card_files):
        threads = []
        for file in card_files[step:step+25]:
            thread = threading.Thread(target=parse_card, args=(file, collection, IMAGE_FOLDER))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()
        step += 25

    print(f'Done processing cards. Post processing begins...')

    collection['encounter_sets'] = list(collection['encounter_sets'].values())
    for es in collection['encounter_sets']:
        try:
            es['icon'] = collection['images'][es['icon']]
        except KeyError:
            pass
    del collection['images']

    with open(OUTPUT_FILE, 'w') as file:
        json.dump(collection, file, cls=JavaWriter, indent=4)
    print(f'Done saving.')

def parse_card(file:Path, results:dict, image_folder:Path):
    card = ResourceKit.getGameComponentFromFile(File(str(file)), False)
    if not card:
        print(f'ERROR: {file} appears to have issues loading.')
        return
    script_name = card.getClassName().split("/")[-1]
    if script_name not in front_types and script_name not in back_types:
        return
    settings = card.getSettings()
    out = {}

    extract_images(card, results, image_folder)

    if card.getFullName() != "":
        out["name"] = card.getFullName()
    else:
        out["name"] = file.name


    out["front"] = {
        "type": front_types[script_name],
    }
    out["back"] = {
        "type": back_types[script_name],
    }

    if settings.get('Unique'):
        out["front"]['title'] = "<unique><name>"

    if subtitle := settings.get('Subtitle'):
        out["front"]['subtitle'] = str(subtitle)


    if traits := settings.get("Traits"):
        out['front']['traits'] = traits

    if settings.get("Rules") and settings.get("Keywords"):
        out["front"]["text"] = str(settings.get("Keywords")) + '\n' + str(settings.get("Rules"))
    elif settings.get("Rules") or settings.get("Keywords"):
        out["front"]["text"] = settings.get("Keywords") or settings.get("Rules")


    if health := settings.get("Health") or settings.get('Stamina'):
        out['front']['health'] = str(health)
    if sanity := settings.get('Sanity'):
        out['front']['sanity'] = str(sanity)
    if evade := settings.get('Evade'):
        out['front']['evade'] = str(evade)
    if combat := settings.get('Attack'):
        out['front']['combat'] = str(combat)

    if damage := settings.get("damage"):
        out["front"]["damage"] = int(damage)
    if horror := settings.get("horror"):
        out["front"]["horror"] = int(horror)

    flavor = (
        settings.get("AgendaStory") or
        settings.get("ActStory") or
        settings.get("Flavor")
    )
    if flavor:
        out["front"]["flavor_text"] = flavor

    if vp := settings.get("Victory"):
        out["front"]["victory"] = vp

    if settings.get("CardClass"):
        out["front"]["classes"] = []
        for c in ('CardClass', 'CardClass2', 'CardClass3'):
            if cl := settings.get(c):
                out['front']['classes'].append(str(cl).lower())

    illustrations = get_portaits(card)
    if illustrations:
        for name, portrait in illustrations.items():
            if name in ('Portrait-Front', 'Portrait-Both', 'TransparentPortrait-Both'):
                out['front']['illustration'] = results['images'][portrait.getSource()]
                out['front']['illustration_pan_x'] = 0
                out['front']['illustration_pan_y'] = 0
                out['front']['illustration_scale'] = portrait.getScale() * 2
            if name in ('Portrait-Back', 'Portrait-Both', 'BackPortrait-Back', 'TransparentPortrait-Both'):
                out['back']['illustration'] = results['images'][portrait.getSource()]
                out['back']['illustration_pan_x'] = 0
                out['back']['illustration_pan_y'] = 0
                out['back']['illustration_scale'] = portrait.getScale() * 2

    if clues := settings.get("Clues"):
        out['front']['clues'] = clues + ("<per>" if settings.get("PerInvestigator") else '')

    if shroud := settings.get("Shroud"):
        out['front']['shroud'] = shroud + ("<per>" if settings.get("ShroudPerInvestigator") else '')

    if doom := settings.get("Doom"):
        out['front']['doom'] = doom + ("<per>" if settings.get("PerInvestigator") else '')

    if index := settings.get("ScenarioIndex"):
        out['front']['index'] = index + settings.get("ScenarioDeckID")

    if icon := settings.get("LocationIcon"):
        out['front']['connection'] = str(icon).lower()

    if 'Connection1Icon' in settings.getKeySet():
        connections = [
            settings.get("Connection1Icon"),
            settings.get("Connection2Icon"),
            settings.get("Connection3Icon"),
            settings.get("Connection4Icon"),
            settings.get("Connection5Icon"),
            settings.get("Connection6Icon"),
        ]
        out['front']['connections'] = [(str(n).lower() if n else None) for n in connections]

    if number := settings.get("EncounterNumber"):
        out["encounter_number"] = number

    if number := settings.get("CollectionNumber"):
        out["expansion_number"] = number

    if artist := settings.get("Artist"):
        out['front']['illustrator'] = str(artist)
    if artist := settings.get("ArtistBack"):
        out['back']['illustrator'] = str(artist)

    # add encounter set if needed
    encounter_set, icon = determine_encounter_set(card)
    if encounter_set:
        results['encounter_sets'][encounter_set] = results['encounter_sets'].get(encounter_set, {
            'name': encounter_set,
            'icon': icon,
            'id': str(uuid4()),
            'card_amount': 0,
        })
        out['encounter_set'] = results['encounter_sets'][encounter_set]['id']
        results['encounter_sets'][encounter_set]['card_amount'] += 1

    # field translation
    for field in ('text', 'flavor'):
        for side in (out['front'], out['back']):
            if field in side:
               side[field] = translate_text(side[field])

    # add to result list
    results['cards'].append(out)
