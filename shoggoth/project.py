import json
from uuid import uuid4
import shutil
from pathlib import Path

import shoggoth
from shoggoth.card import TEMPLATES, Card
from shoggoth.encounter_set import EncounterSet
from shoggoth.files import asset_dir, guide_dir
from shoggoth.guide import Guide

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
        self.dirty = False

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
        if (self.folder / path).is_file():
            return (self.folder / path).absolute()
        return False

    def __eq__(self, other):
        return self.data == other.data

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def get_card(self, id):
        for entry in self.data.get('cards', []):
            if 'id' in entry and entry['id'] == id:
                return Card(entry, expansion=self)

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
        c = [Card(card, expansion=self) for card in self.data.get('cards', [])]
        sort_cards(c)
        return c

    @property
    def player_cards(self):
        c = [Card(card, expansion=self) for card in self.data['cards'] if 'encounter_set' not in card]
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
            yield EncounterSet(e, expansion=self)

    def get_encounter_set(self, id):
        for es in self.encounter_sets:
            if es.id == id:
                return es
        return None

    def assign_card_numbers(self):
        current_number = 1
        for encounter_set in self.encounter_sets:
            encounter_set.assign_card_numbers()
            for card in encounter_set.cards:
                card.expansion_number = current_number
                current_number += 1
        for card in self.player_cards:
            card.expansion_number = current_number
            current_number += 1

    def add_card(self, card):
        if 'cards' not in self.data:
            self.data['cards'] = []
        if isinstance(card, Card):
            self.data['cards'].append(card.data)
        else:
            self.data['cards'].append(card)
        self.dirty = True

    def get_all_cards(self):
        return self.cards

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
        return EncounterSet(encounter_data, expansion=self)

    def remove_encounter_set(self, index):
        self.data['encounter_sets'].pop(index)

    def save(self):
        """Save data to file"""
        with open(self.file_path, 'r') as f:
            orig_data = json.load(f)
        for key in self.data:
            if key in ('cards', 'encounter_sets', 'guides'):
                continue
            orig_data[key] = self.data[key]

        with open(self.file_path, 'w') as f:
            json.dump(self.data, f, indent=4)
        self.dirty = False

    def save_card(self, card):
        print('saving card of project', card.id)
        with open(self.file_path, 'r') as f:
            orig_data = json.load(f)
        index = None
        for key, value in enumerate(orig_data['cards']):
            if value['id'] == card.id:
                index = key
                break
        if index:
            orig_data['cards'][index] = card.data
        with open(self.file_path, 'w') as f:
            json.dump(orig_data, f, indent=4)

    def save_all(self):
        """Save data to file"""
        with open(self.file_path, 'w') as f:
            json.dump(self.data, f, indent=4)
        self.dirty = False

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

    def add_guide(self):
        default_guide = guide_dir / 'guide_template.html'
        shutil.copyfile(default_guide, self.folder / 'guide.html')
        if 'guides' not in self.data:
            self.data['guides'] = []
        self.data['guides'].append({
            'path': str(self.folder / 'guide.html'),
            'name': 'Guide',
            'id': str(uuid4()),
        })
        shoggoth.app.refresh_tree()

    def add_investigator_set(self, name):
        """ Creates a few cards usually needed for an investigator """
        investigator = TEMPLATES.INVESTIGATOR()
        investigator['name'] = name
        investigator['investigator'] = name
        signature = TEMPLATES.ASSET()
        signature['name'] = 'signature'
        signature['front']['text'] = f'{name} deck only.'
        signature['investigator'] = name
        weakness = TEMPLATES.BASE()
        weakness['name'] = 'weakness'
        weakness['front']['type'] = 'weakness_treachery'
        weakness['back']['type'] = 'player'
        weakness['investigator'] = name
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
            encounter_set.add_card(card)
        shoggoth.app.refresh_tree()
        shoggoth.app.goto_card(cards[0]['id'])

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

    def create_player_expansion(self):
        """ Creates a set of placeholder cards
            aligning with the usual distribution of cards
            in an investigator expansion.

            An investigator expansion usually has around:
                ~130 unique cards in an expansion.
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
