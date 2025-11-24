import json
from uuid import uuid4
from pathlib import Path
from typing import Any, Dict

import shoggoth
from shoggoth.files import defaults_dir


class Face:
    def __init__(self, data, card):
        self.data = data
        self.card = card
        self._fallback = None
        self.dirty = False

    def __eq__(self, other):
        return self.data == other.data

    @property
    def fallback(self):
        if self._fallback is not None:
            return self._fallback

        if path := self.card.expansion.find_file(self.data['type']):
            defaults_path = path
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

        cls = self.get_class()
        if f'{key}_{cls}' in self.fallback:
            return self.fallback[f'{key}_{cls}']
        return self.fallback[key]

    def get(self, key, default=''):
        try:
            result = self.__getitem__(key)
            if result == '<copy>':
                return self.other_side[key]
            return result
        except KeyError:
            return default

    def set(self, key, value):
        # invalidate cached fallback if fallback should change
        if key == 'type':
            self._fallback = None

        self.data[key] = value
        if value is None:
            del self.data[key]

        shoggoth.app.update_card_preview()
        if key in ('classes', 'type', 'level'):
            shoggoth.app.current_project.assign_card_numbers()
            shoggoth.app.refresh_tree()
        self.dirty = True

    def get_class(self):
        cls = self.data.get('classes', ['guardian'])
        if not cls:
            return None
        if len(cls) == 1:
            return cls[0]
        return 'multi'

    @property
    def other_side(self):
        if self == self.card.front:
            return self.card.back
        return self.card.front


class Card:
    """Class to represent the card object and file structure"""

    def __init__(
        self,
        data: Dict[str, Any],
        expansion,
        encounter=None,
    ):
        self.data = data
        if encounter:
            self.data['encounter_set'] = encounter.id
        self.expansion = expansion
        if 'id' not in data:
            data['id'] = str(uuid4())

        self.front = Face(self.data['front'], card=self)
        self.back = Face(self.data['back'], card=self)

    def __str__(self):
        return f'<Card "{self.name}">'

    @property
    def encounter(self):
        if not 'encounter_set' in self.data or not self.data['encounter_set']:
           return None
        return self.expansion.get_encounter_set(self.data['encounter_set'])

    def reload_fallback(self):
        """ Invalidates the fallback cache, forcing a reload of the file """
        self.front._fallback = None
        self.back._fallback = None

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
        if key in ('name', 'id', 'investigator', 'encounter_set'):
            shoggoth.app.current_project.assign_card_numbers()
            shoggoth.app.update_card_preview()
            shoggoth.app.refresh_tree()

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

    def save(self):
        print('Saving card', self.id)
        self.expansion.save_card(self)
        self.dirty = False


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
            'enemy_weakness': cls.ENEMY_WEAKNESS(),
            'treachery_weakness': cls.TREACHERY_WEAKNESS(),
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
        card['back']['entries'] = [
            ["<b>Deck Size:</b>", "30"],
            ["<b>Secondary Class Choice:</b>", ""],
            ["<b>Deckbuilding Options:</b>", ""],
            ["<b>Deckbuilding Requirements</b> (do not count toward deck size):",""],
            ["<b>Deckbuilding Restrictions:</b>", ""],
        ]
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
        card['front']['difficulty'] = 'Easy/Standard'
        card['back']['type'] = 'chaos'
        card['back']['difficulty'] = 'Hard/Expert'
        return card

    @classmethod
    def STORY(cls):
        card = cls.BASE()
        card['amount'] = 1
        card['front']['type'] = 'story'
        card['back']['type'] = 'story'
        return card

    @classmethod
    def ENEMY_WEAKNESS(cls):
        card = cls.ENEMY()
        card['amount'] = 1
        card['front']['type'] = 'weakness_enemy'
        card['back']['type'] = 'player'
        return card
    
    @classmethod
    def TREACHERY_WEAKNESS(cls):
        card = cls.TREACHERY()
        card['amount'] = 1
        card['front']['type'] = 'weakness_treachery'
        card['back']['type'] = 'player'
        return card
