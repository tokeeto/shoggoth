import os
import json
from pathlib import Path
from typing import Any, Dict, Optional

from kivy.app import App

from shoggoth.files import defaults_dir


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
        defaults_path = defaults_dir / defaults_file

        try:
            with defaults_path.open('r') as f:
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


class Card:
    """Class to represent the card object and file structure"""

    def __init__(
        self,
        data:Dict[str, Any],
        expansion,
        encounter=None,
    ):
        self.app = None
        self.data = data
        self.name = data['name']
        self.encounter = encounter
        self.expansion = expansion

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

    def save(self):
        """Save card data to JSON file"""
        pass

    @staticmethod
    def new(name) -> Dict[str, Any]:
        return {
            'name': name,
            'front': {
                'type': 'asset'
            },
            'back': {
                'type': 'player'
            }
        }
