import os
import json
from pathlib import Path

from kivy.app import App
from card import Card
from encounter_set import EncounterSet

defaults_root = 'assets/defaults'


class Project:
    """ Class to handle project files

        Projects are ultimately just representations of json files.
    """
    def __init__(self, file_path, data):
        self.file_path = file_path
        self.data = data
        self.icon = data.get('icon', '')

    def __eq__(self, other):
        return self.data == other.data

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def encounter_sets(self):
        for e in self.data['encounter_sets']:
            yield EncounterSet(e, expansion=self)

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
            json.dump(self.data, f)
