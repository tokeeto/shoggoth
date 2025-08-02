import os
import json
from uuid import uuid4

from kivy.app import App
from shoggoth.card import Card
from shoggoth.encounter_set import EncounterSet

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
    "story": 9,
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
        type_order.get(card.front['type'], type_order["other"]),
        card.front.get('agenda_index', -1),
        card.front.get('act_index', -1),
        class_order.get(card.front.get('class'), -1),
        card.front.get('level', -1),
        card.front.get('type', ''),
        card.name,
    ))

class Project:
    """ Class to handle project files

        Projects are ultimately just representations of json files.
    """
    def __init__(self, file_path, data):
        self.file_path = file_path
        self.data = data
        self.icon = data.get('icon', '')
        self.code = data.get('code', 'xx')
        self.id = data.get('id', uuid4())

    def __eq__(self, other):
        return self.data == other.data

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def name(self):
        return self.data['name']

    @property
    def cards(self):
        for card in self.data.get('cards', []):
            yield Card(card, expansion=self)

    @property
    def encounter_sets(self):
        # order sets to always come out right
        self.data['encounter_sets'].sort(key=lambda x: (
            x.get('order', '999'),
            x.get('name'),
        ))

        for e in self.data['encounter_sets']:
            yield EncounterSet(e, expansion=self)

    def assign_card_numbers(self):
        current_number = 1
        for encounter_set in self.encounter_sets:
            encounter_set.assign_card_numbers()
            for card in encounter_set.cards:
                card.expansion_number = current_number
                current_number += 1
        for card in self.cards:
            card.expansion_number = current_number
            current_number += 1

    def add_card(self, card):
        if not 'cards' in self.data:
            self.data['cards'] = []
        if type(card) == Card:
            self.data['cards'].append(card.data)
        else:
            self.data['cards'].append(card)

    def get_all_cards(self):
        result = []
        for e in self.encounter_sets:
            for c in e.cards:
                result.append(c)
        if 'cards' in self.data:
            for c in self.data['cards']:
                result.append(Card(c, expansion=self))
        return result

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
            except AssertionError as e:
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
        App.get_running_app().refresh_tree()

    def remove_encounter_set(self, index):
        self.data['encounter_sets'].pop(index)

    def save(self):
        """Save data to file"""
        with open(self.file_path, 'w') as f:
            json.dump(self.data, f, indent=4)

    @staticmethod
    def new(name, code, icon):
        """ Returns the base data for a new Project """
        return {
            'name': name,
            'code': code,
            "icon": icon,
            'encounter_sets': [],
            'cards': [],
        }
