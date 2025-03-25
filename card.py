import os
import json
from pathlib import Path

from kivy.app import App
from kivy.properties import DictProperty
from kivy.event import EventDispatcher

defaults_root = 'assets/defaults'

class Face:
    def __init__(self, data):
        self.data = data

    @property
    def fallback(self):
        defaults_file = f'{self.data["type"]}.card'
        defaults_path = os.path.join(defaults_root, defaults_file)

        try:
            with open(defaults_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f'Error in defaults found for face type: {self.data["type"]}\n', e)
            return {}

    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]
        return self.fallback[key]

    def get(self, key, default=''):
        if key in self.data:
            return str(self.data[key])
        if key in self.fallback:
            return str(self.fallback[key])
        else:
            return default

    def set(self, key, value):
        self.data[key] = value
        print('setting', key, value)
        App.get_running_app().update_card_preview()


class Card(EventDispatcher):
    """Class to represent the card object and file structure"""

    def __init__(self, data):
        super().__init__()
        self.app = None
        self.data = data

        front_defaults = self.load_default(self.data['front'])
        back_defaults = self.load_default(self.data['back'])

        self.front = Face(self.data['front'])
        self.back = Face(self.data['back'])
        self.app = App.get_running_app()

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
        print(f'{defaults_path=}')

        try:
            with open(defaults_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(e)
            raise
