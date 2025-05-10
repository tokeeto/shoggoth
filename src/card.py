import os
import json
from pathlib import Path

from kivy.app import App
from kivy.properties import DictProperty
from kivy.event import EventDispatcher

defaults_root = 'assets/defaults'

class Face:
    def __init__(self, data, card=None, encounter=None, expansion=None):
        self.data = data
        self.card = card
        self.encounter = encounter
        self.expansion = expansion
        self._fallback = None

    def __eq__(self, other):
        return self.data == other.data

    @property
    def fallback(self):
        if self._fallback != None:
            return self._fallback

        defaults_file = f'{self.data["type"]}.card'
        defaults_path = os.path.join(defaults_root, defaults_file)

        try:
            with open(defaults_path, 'r') as f:
                self._fallback = json.load(f)
            return self._fallback
        except Exception as e:
            return {}

    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]
        return self.fallback[key]

    def get(self, key, default=''):
        if key in self.data:
            return self.data[key]
        if key in self.fallback:
            return self.fallback[key]
        else:
            return default

    def set(self, key, value):
        self.data[key] = value
        App.get_running_app().update_card_preview()


class Card(EventDispatcher):
    """Class to represent the card object and file structure"""

    def __init__(self, data, encounter=None, expansion=None):
        super().__init__()
        self.app = None
        self.data = data
        self.name = data['name']
        self.encounter = encounter
        self.expansion = expansion

        front_defaults = self.load_default(self.data['front'])
        back_defaults = self.load_default(self.data['back'])

        self.front = Face(self.data['front'], card=self)
        self.back = Face(self.data['back'], card=self)
        self.app = App.get_running_app()

    @property
    def expansion_number(self):
        return self.data['expansion_number']

    @expansion_number.setter
    def expansion_number(self, value):
        self.data['expansion_number'] = value

    @property
    def encounter_number(self):
        if not self.encounter:
            return None
        return self.data['encounter_number']

    @encounter_number.setter
    def encounter_number(self, value):
        if not self.encounter:
            raise Exception("No encounter, can't set number.")
        self.data['encounter_number'] = value

    @property
    def code(self):
        if self.encounter:
            return f'{self.expansion.code}_{self.encounter.code}_{self.name}'
        return f'{self.expansion.code}_{self.expansion_number}_{self.name}'

    def __eq__(self, other):
        return self.data == other.data

    @staticmethod
    def is_valid(data):
        return 'front' in data and 'back' in data

    def load(self):
        """Load card data from JSON file"""
        try:
            with open(self.file_path, 'r') as f:
                self.data = json.load(f)
        except Exception as e:
            print(e)
            raise

        # Ensure required sections exist
        # defaults to an asset
        if 'front' not in self.data:
            self.data['front'] = {}
        if 'type' not in self.data['front']:
            self.data['front']['type'] = 'asset'
        front_defaults = self.load_default(self.data['front'])
        self.front = CardDict(self.data['front'], front_defaults)

        if 'back' not in self.data:
            self.data['back'] = {}
        if 'type' not in self.data['back']:
            self.data['front']['back'] = 'player'
        back_defaults = self.load_default(self.data['back'])
        self.back = CardDict(self.data['back'], back_defaults)

    def save(self):
        """Save card data to JSON file"""
        pass

    def load_default(self, side):
        """Load default values for a card type"""
        defaults_file = f'{side["type"]}.card'
        defaults_path = os.path.join(defaults_root, defaults_file)

        try:
            with open(defaults_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(e)
            return {}

    @staticmethod
    def new(name):
        return Card({
            'name': name,
            'front': {
                'type': 'asset'
            },
            'back': {
                'type': 'player'
            }
        })
