import os
import json
from uuid import uuid4
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

        if Path(self.data['type']).is_file():
            defaults_path = Path(self.data['type'])
        else:
            defaults_file = f'{self.data["type"]}.json'
            defaults_path = defaults_dir / defaults_file

        try:
            with defaults_path.open('r') as f:
                self._fallback = json.load(f)
            return self._fallback
        except Exception as e:
            print('exception when loading fallback:', e)
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
        if key == 'type':
            self._fallback = None
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
        self.data = data
        self.encounter = encounter
        self.expansion = expansion
        if 'id' not in data:
            data['id'] = str(uuid4())

        self.front = Face(self.data['front'], card=self)
        self.back = Face(self.data['back'], card=self)

    @property
    def name(self):
        return self.data['name']

    @property
    def amount(self):
        return self.data.get('amount', 1)

    @property
    def id(self):
        return self.data['id']

    @property
    def expansion_number(self):
        return self.data.get('expansion_number', -1)

    @expansion_number.setter
    def expansion_number(self, value):
        self.data['expansion_number'] = value

    @property
    def encounter_number(self):
        if not self.encounter:
            return None
        return self.data.get('encounter_number', -1)

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

    def get_class(self):
        back_classes = self.data['back'].get('classes')
        classes = self.data['front'].get('classes', back_classes)
        if not classes:
            return None

        if len(classes) > 1:
            return 'multi'
        else:
            return classes[0]

    def set(self, key, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    @staticmethod
    def is_valid(data):
        return 'front' in data and 'back' in data

    @staticmethod
    def new(name) -> Dict[str, Any]:
        return {
            'name': name,
            'id': str(uuid4()),
            'front': {
                'type': 'asset'
            },
            'back': {
                'type': 'player'
            }
        }

# templates
class TEMPLATES:
    @classmethod
    def get(cls, name):
        return {
            'investigator': cls.INVESTIGATOR(),
            'asset': cls.ASSET(),
            'event': cls.EVENT(),
            'skill': cls.SKILL(),
            'story': cls.STORY(),
            'treachery': cls.TREACHERY(),
            'enemy': cls.ENEMY(),
            'location': cls.LOCATION(),
            'act': cls.ACT(),
            'agenda': cls.AGENDA(),
            'scenario': cls.SCENARIO(),
        }.get(name, cls.BASE())

    @classmethod
    def BASE(cls):
        return {
            'name': '',
            'id': str(uuid4()),
            'amount': 1,
            'front': {
                'type': ''
            },
            'back': {
                'type': ''
            }
        }

    @classmethod
    def ASSET(cls):
        card = cls.BASE()
        card['amount'] = 2
        card['front']['type'] = 'asset'
        card['back']['type'] = 'player'
        return card

    @classmethod
    def INVESTIGATOR(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'investigator'
        card['back']['type'] = 'investigator_back'
        return card

    @classmethod
    def EVENT(cls):
        card = cls.BASE()
        card['amount'] = 2
        card['front']['type'] = 'event'
        card['back']['type'] = 'player'
        return card

    @classmethod
    def SKILL(cls):
        card = cls.BASE()
        card['amount'] = 2
        card['front']['type'] = 'skill'
        card['back']['type'] = 'player'
        return card

    @classmethod
    def ENEMY(cls):
        card = cls.BASE()
        card['amount'] = 3
        card['front']['type'] = 'enemy'
        card['back']['type'] = 'encounter'
        return card

    @classmethod
    def TREACHERY(cls):
        card = cls.BASE()
        card['amount'] = 3
        card['front']['type'] = 'treachery'
        card['back']['type'] = 'encounter'
        return card

    @classmethod
    def LOCATION(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'location'
        card['back']['type'] = 'location_back'
        return card

    @classmethod
    def ACT(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'act'
        card['back']['type'] = 'act_back'
        return card

    @classmethod
    def AGENDA(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'agenda'
        card['back']['type'] = 'agenda_back'
        return card

    @classmethod
    def SCENARIO(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'chaos'
        card['back']['type'] = 'chaos_back'
        return card

    @classmethod
    def STORY(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'story'
        card['back']['type'] = 'story_back'
        return card
