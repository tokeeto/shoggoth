from uuid import uuid4
from shoggoth.card import Card


class EncounterSet:
    def __init__(self, data, project):
        self.name = data['name']
        self.data = data
        self.project = project
        if 'id' not in self.data:
            self.data['id'] = str(uuid4())
        self.get = self.data.get
        self.__getitem__ = self.data.__getitem__
        self.dirty = False

    def __eq__(self, other):
        return other is not None and self.id == other.id

    @property
    def order(self):
        return self.data.get('order')

    @property
    def cards(self):
        result = []
        for c in self.project.data['cards']:
            if c.get('encounter_set') == self.id:
                result.append(Card(c, encounter=self, project=self.project))
        result.sort(key=lambda c: c.name)
        return result

    @staticmethod
    def is_valid(data):
        return 'name' in data and 'icon' in data

    @property
    def icon(self):
        return self.data.get('icon', '')

    @icon.setter
    def icon(self, value):
        self.data['icon'] = value

    @property
    def id(self):
        return self.data['id']

    @property
    def number_of_locations(self):
        """ Property used in guide creation mainly """
        return len([c for c in self.cards if c.front.get('type') == 'location'])

    def add_card(self, card):
        if isinstance(card, Card):
            self.data['cards'].append(card.data)
        else:
            self.data['cards'].append(card)

    @property
    def total_cards(self):
        return sum([c.amount for c in self.cards])

    def assign_card_numbers(self):
        current_number = 1
        for card in self.cards:
            amount = card.amount
            if amount > 1:
                card.data['encounter_number'] = f'{current_number}-{current_number+amount-1}'
            else:
                card.data['encounter_number'] = f'{current_number}'
            current_number += amount
        self.data['card_amount'] = current_number-1

    def set(self, key, value):
        self.data[key] = value
        self.dirty = True


class EncounterSetTranslation(EncounterSet):
    def __init__(self, data, translation_data, project):
        self.translation_data = translation_data
        super().__init__(data, project)
        self.name = self.translation_data.get('name', self.name)

    @property
    def cards(self):
        result = []
        for c in self.project.cards:
            if c.get('encounter_set') == self.id:
                result.append(c)
        result.sort(key=lambda c: c.name)
        return result

    def set(self, key, value):
        self.translation_data[key] = value
        self.dirty = True
