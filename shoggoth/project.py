import json
from uuid import uuid4
from pathlib import Path

import shoggoth
from shoggoth.card import TEMPLATES, Card
from shoggoth.encounter_set import EncounterSet
from shoggoth.guide import Guide
from shoggoth.i18n import tr
from shoggoth.project_writer import Writer, TranslationWriter


type_order = {
    "scenario": 0,
    "chaos": 1,
    "agenda": 2,
    "act": 3,
    "location": 4,
    "story": 5,
    "key": 6,
    "treachery": 7,
    "enemy": 8,
    # "story": 9,
    "investigator": 10,
    "other": 11
}

class_order = {
    "guardian": 0,
    "seeker": 1,
    "rogue": 2,
    "mystic": 3,
    "survivor": 4,
    "neutral": 5,
    "multi": 6  # Multi-class cards are sorted last
}


def sort_cards(cards):
    cards.sort(key=lambda card: (
        str(type_order.get(card.front['type'], 15)),
        str(card.front.get('agenda_index', 15)),
        str(card.front.get('act_index', 15)),
        str(class_order.get(card.get_class(), 15)),
        str(card.front.get('level', 15)),
        str(card.name),
    ))


class Project:
    """ Class to handle project files

        Projects are ultimately just representations of json files.
    """

    def __init__(self, file_path, data):
        self.file_path = file_path
        self.data = data
        if 'id' not in self.data:
            self.data['id'] = str(uuid4())
        self.id = data['id']
        self.writer = Writer(self)

    @property
    def dirty(self):
        return bool(self.data.get('meta', {}).get('dirty', []))

    @dirty.setter
    def dirty(self, value):
        self.set_dirty(self.id, value)

    @property
    def icon(self):
        return self.data.get('icon', '')

    @icon.setter
    def icon(self, value):
        self.dirty = value != self.data['icon']
        self.data['icon'] = value

    @property
    def folder(self):
        return Path(self.file_path).parent

    def find_file(self, path):
        path = Path(path)
        if path.exists():
            return path.resolve()
        if (self.folder / path).exists():
            return (self.folder / path).resolve()
        return None

    def __eq__(self, other):
        return self.data == other.data

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def translations(self):
        """Return a dict of {language: Translation} for all registered translations."""
        result = {}
        for lang, rel_path in self.data.get('translations', {}).items():
            full_path = self.folder / rel_path
            result[lang] = full_path
        return result

    def add_translation(self, language, file_path):
        """Register a translation file. *file_path* may be absolute or relative."""
        rel = Path(file_path).relative_to(self.folder) if Path(file_path).is_absolute() else Path(file_path)
        if 'translations' not in self.data:
            self.data['translations'] = {}
        self.data['translations'][language] = str(rel)
        self.dirty = True

    def save_all(self):
        self.writer.save_all()

    def save(self):
        # self.writer.save_project(self)
        self.writer.save_all()

    def get_card(self, id):
        for entry in self.data.get('cards', []):
            if entry.get('id') == id:
                return Card(entry, project=self)

    @property
    def guides(self):
        result = []
        for entry in self.data.get('guides', []):
            result.append(Guide(entry, self))
        return result

    @property
    def name(self):
        return self.data['name']

    @property
    def cards(self):
        c = [Card(card, project=self) for card in self.data.get('cards', [])]
        sort_cards(c)
        return c

    @property
    def player_cards(self):
        c = [Card(card, project=self) for card in self.data.get('cards', []) if 'encounter_set' not in card]
        sort_cards(c)
        return c

    @property
    def encounter_sets(self):
        # order sets to always come out right
        self.data['encounter_sets'].sort(key=lambda x: (
            x.get('order', 999),
            x.get('name'),
        ))

        for e in self.data['encounter_sets']:
            yield EncounterSet(e, project=self)

    def get_encounter_set(self, id):
        for es in self.encounter_sets:
            if es.id == id:
                return es
        return None

    @property
    def scenario_names(self):
        """ Property for guide creation.
            Scenarios are encounter sets with ordering.
        """
        scenarios = [n for n in self.encounter_sets if n.get('order') != None]
        names = [f'"{n.name}"' for n in scenarios]
        if not names:
            return ''
        if len(names) < 2:
            return names[0]
        return ', '.join(names[:-1]) + ' and ' + names[-1]

    @property
    def number_of_scenarios(self):
        """ Property for guide creation.
            Scenarios are encounter sets with ordering.
        """
        scenarios = [n for n in self.encounter_sets if n.get('order') != None]
        return len(scenarios)

    def get_guide(self, id):
        for guide in self.guides:
            if guide.id == id:
                return guide
        return None

    def assign_card_numbers(self):
        current_number = 1
        for encounter_set in self.encounter_sets:
            encounter_set.assign_card_numbers()
            for card in encounter_set.cards:
                card.project_number = current_number
                current_number += 1
        for card in self.player_cards:
            card.project_number = current_number
            current_number += 1

    def add_card(self, card):
        if 'cards' not in self.data:
            self.data['cards'] = []
        if isinstance(card, Card):
            self.data['cards'].append(card.data)
        else:
            self.data['cards'].append(card)

        if not card.get('copyright') and 'default_copyright' in self.data:
            if isinstance(card, Card):
                card.set('copyright', self.data['default_copyright'])
            else:
                card['copyright'] = self.data['default_copyright']
        self.dirty = True

    def get_all_cards(self):
        return self.cards

    def set_dirty(self, id, value=True):
        if 'meta' not in self.data:
            self.data['meta'] = {}
        if 'dirty' not in self.data['meta']:
            self.data['meta']['dirty'] = []
        if value and id not in self.data['meta']['dirty']:
            self.data['meta']['dirty'].append(id)
        elif not value and id in self.data['meta']['dirty']:
            self.data['meta']['dirty'].remove(id)

    def clear_dirty(self):
        if 'meta' not in self.data:
            self.data['meta'] = {}
        self.data['meta']['dirty'] = []

    def is_dirty(self, id):
        return id in self.data.get('meta', {}).get('dirty', [])

    @staticmethod
    def load(file_path):
        """Load card data from JSON file"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(e)
            raise

        for entry in data["encounter_sets"]:
            try:
                assert EncounterSet.is_valid(entry)
            except AssertionError:
                print('Entry failed assertion, project is invalid: ', entry)
                raise Exception('Invalid project file.')

        return Project(file_path, data)

    def add_encounter_set(self, name):
        if 'encounter_sets' not in self.data:
            self.data['encounter_sets'] = []
        for enc in self.data['encounter_sets']:
            if enc['name'] == name:
                raise Exception('duplicate encounter set name')

        encounter_data = {
            'name': name,
            'icon': '',
            'cards': [],
        }
        self.data['encounter_sets'].append(encounter_data)
        shoggoth.app.refresh_tree()
        self.dirty = True
        return EncounterSet(encounter_data, project=self)

    def remove_encounter_set(self, index):
        self.data['encounter_sets'].pop(index)

    def gather_images(self):
        """ Walks through the project and copies to all relevant images to a nearby folder for easier distribution.
            Also updates all used paths to point to the new images using a relative path.
        """
        import shutil

        image_paths = {}  # old path string -> new relative path string
        output_folder = self.folder / f'{self.name} images'
        output_folder.mkdir(exist_ok=True)

        def copy_image(path_str):
            if not path_str:
                return path_str
            if path_str in image_paths:
                return image_paths[path_str]

            resolved = self.find_file(path_str)
            if not resolved:
                return path_str

            try:
                resolved.relative_to(output_folder)
                image_paths[path_str] = str(resolved.relative_to(self.folder))
                return image_paths[path_str]
            except ValueError:
                pass

            dest_path = output_folder / resolved.name
            counter = 1
            while dest_path.exists() and dest_path.resolve() != resolved:
                dest_path = output_folder / f'{resolved.stem}_{counter}{resolved.suffix}'
                counter += 1

            if not dest_path.exists():
                shutil.copy2(resolved, dest_path)

            image_paths[path_str] = str(dest_path.relative_to(self.folder))
            return image_paths[path_str]

        if self.icon:
            self.data['icon'] = copy_image(self.icon)

        for encounter_set in self.encounter_sets:
            if encounter_set.icon:
                encounter_set.data['icon'] = copy_image(encounter_set.icon)

        for card in self.cards:
            for side in (card.front, card.back):
                for key in ('illustration', 'image1', 'image2', 'image3', 'image4', 'image5'):
                    image = side.data.get(key)
                    if image:
                        side.data[key] = copy_image(image)


    @staticmethod
    def new(name, code, icon):
        """ Returns the base data for a new Project """
        return {
            'name': name,
            'code': code,
            'icon': icon,
            'encounter_sets': [],
            'cards': [],
        }

    def add_guide(self, name='Guide', file_location=None):
        if 'guides' not in self.data:
            self.data['guides'] = []
        self.data['guides'].append({
            'id': str(uuid4()),
            'name': name,
            'sections': [],
        })
        shoggoth.app.refresh_tree()

    def add_investigator_set(self, name):
        """ Creates a few cards usually needed for an investigator """
        investigator = TEMPLATES.INVESTIGATOR()
        investigator['name'] = name
        investigator['investigator'] = name
        signature = TEMPLATES.ASSET()
        signature['name'] = 'signature'
        signature['front']['text'] = f'<:{investigator["id"]} name> deck only.'
        signature['investigator'] = name
        weakness = TEMPLATES.BASE()
        weakness['name'] = 'weakness'
        weakness['front']['type'] = 'treachery'
        weakness['front']['class'] = 'weakness'
        weakness['back']['type'] = 'player'
        weakness['investigator'] = name

        investigator['back']['entries'][3] = f"<:{signature['id']} name>, <:{weakness['id']} name>, 1 random basic weakness."

        self.add_card(investigator)
        self.add_card(signature)
        self.add_card(weakness)
        shoggoth.app.refresh_tree()
        shoggoth.app.goto_card(investigator['id'])

    def create_scenario(self, name, order=None):
        """ Creates an encounter set
            including acts, agendas, and other
            placeholder cards.
        """
        cards = []
        for x in range(1,4):
            act = TEMPLATES.ACT()
            act['front']['index'] = f'{x}a'
            act['back']['index'] = f'{x}b'
            act['name'] = f'Act {x}'
            cards.append(act)

            agenda = TEMPLATES.AGENDA()
            agenda['front']['index'] = f'{x}a'
            agenda['back']['index'] = f'{x}b'
            agenda['name'] = f'Agenda {x}'
            cards.append(agenda)

        for x in range(0,3):
            enemy = TEMPLATES.ENEMY()
            enemy['name'] = f'Enemy {x+1}'
            enemy['amount'] = 3
            cards.append(enemy)

        for x in range(0, 7):
            treachery = TEMPLATES.TREACHERY()
            treachery['name'] = f'Treachery {x+1}'
            treachery['amount'] = 3
            cards.append(treachery)

        for x in range(0, 8):
            location = TEMPLATES.LOCATION()
            location['name'] = f'Location {x+1} - minimum size'
            location['amount'] = 1
            cards.append(location)

        for x in range(0, 4):
            location = TEMPLATES.LOCATION()
            location['name'] = f'Location {x+9} - medium size'
            location['amount'] = 1
            cards.append(location)

        for x in range(0, 4):
            location = TEMPLATES.LOCATION()
            location['name'] = f'Location {x+13} - large size'
            location['amount'] = 1
            cards.append(location)

        encounter_set = self.add_encounter_set(name)
        if order:
            encounter_set.data['order'] = order
        for card in cards:
            card['encounter_set'] = encounter_set.id
            self.add_card(card)
        shoggoth.app.refresh_tree()

    def create_campaign(self):
        """ Creates 8 placeholder scenarios. """
        scenario_names = [
            'Introduction',
            'The Call',
            'Learning',
            'Threshold',
            'Acceptance',
            'The Test',
            'Revelation',
            'Climax'
        ]
        for index, name in enumerate(scenario_names):
            self.create_scenario(name, order=index+1)

    def create_player_project(self):
        """ Creates a set of placeholder cards
            aligning with the usual distribution of cards
            in an investigator project.

            An investigator project usually has around:
                ~130 unique cards in an project.
                5 investigators
                50 level 0
                50 level 1-5
                25 bound/other (10-15 signature cards for instance)

            This method creates, for each class + neutral:
                9 level 0 cards
                9 level 1-5 cards
                3 investigator related cards
            for a total of 126 cards.
        """

        cards = []
        for class_name in ('guardian', 'rogue', 'seeker', 'mystic', 'survivor', 'neutral'):
            if class_name != 'neutral':
                self.add_investigator_set(f'The {class_name.capitalize()}')
            # Level 0 cards
            for n in range(4):
                asset = TEMPLATES.ASSET()
                asset['front']['classes'] = [class_name]
                asset['front']['level'] = 0
                asset['name'] = f'{class_name} asset {n+1}'
                cards.append(asset)
            for n in range(3):
                event = TEMPLATES.EVENT()
                event['front']['classes'] = [class_name]
                event['front']['level'] = 0
                event['name'] = f'{class_name} event {n+1}'
                cards.append(event)
            for n in range(2):
                skill = TEMPLATES.SKILL()
                skill['front']['classes'] = [class_name]
                skill['front']['level'] = 0
                skill['name'] = f'{class_name} skill {n+1}'
                cards.append(skill)

            # Level 1-5 cards
            for n in range(4):
                asset = TEMPLATES.ASSET()
                asset['front']['classes'] = [class_name]
                asset['front']['level'] = n+2
                asset['name'] = f'{class_name} xp asset {n+1}'
                cards.append(asset)
            for n in range(3):
                event = TEMPLATES.EVENT()
                event['front']['classes'] = [class_name]
                event['front']['level'] = n+2
                event['name'] = f'{class_name} xp event {n+1}'
                cards.append(event)
            for n in range(2):
                skill = TEMPLATES.SKILL()
                skill['front']['classes'] = [class_name]
                skill['front']['level'] = n+1
                skill['name'] = f'{class_name} xp skill {n+1}'
                cards.append(skill)

        for card in cards:
            self.add_card(card)
        shoggoth.app.refresh_tree()


def update(d, u):
    import collections.abc
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


class Translation:
    """ A translated version of a project.
        Only really supports work and changes to the translation of
        the project. Any changes to cards should happen in the Project
        itself.
    """

    def __init__(self, file_path, data):
        self.file_path = str(file_path)
        self.data = data
        if 'language' not in self.data:
            raise Exception(tr("ERROR_TRANSLATION_MISSING_LANGUAGE"))
        self.language = data['language']
        if 'project' not in self.data:
            raise Exception(tr("ERROR_TRANSLATION_MISSING_PROJECT"))
        self.project_path = Path(self.file_path).parent / Path(data['project'])
        self.project = Project.load(self.project_path)
        self.apply()

    @classmethod
    def load(cls, file_path):
        """Load data from JSON file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(file_path, data)

    def apply(self):
        """ Translates the project and overwrites the Writer of the project """
        self.project.writer = TranslationWriter(self)

        # project
        self.project.data['name'] = self.data.get('project_name', self.project.name)

        # encounter sets
        for encounter_id in self.data.get('encounter_sets', {}):
            encounter = self.project.get_card(encounter_id)
            if not encounter:
                continue
            encounter.data['name'] = self.data['encounter_sets'][encounter_id]['name']

        # cards
        for card_id, card_data in self.data.get('cards', {}).items():
            card = self.project.get_card(card_id)
            if not card:
                continue
            card.data['name'] = card_data.get('name', card.name)
            for field, value in card_data.get('front', {}).items():
                card.data['front'][field] = value
            for field, value in card_data.get('back', {}).items():
                card.data['back'][field] = value

        # guides
        # overwrites the guides to hide non-translated guides
        self.project.data['guides'] = self.data.get('guides', [])
