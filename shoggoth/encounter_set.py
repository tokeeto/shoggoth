from uuid import uuid4
from shoggoth.card import Card


def parse_number_span(value):
    """Parse a manually-entered number field ('5' or '5-6') into the set of
    integers it claims, so the automatic process can skip them. Returns an
    empty set for missing/unparseable values.
    """
    if not value:
        return set()
    text = str(value)
    if '-' in text:
        lo, _, hi = text.partition('-')
        try:
            return set(range(int(lo), int(hi) + 1))
        except ValueError:
            return set()
    try:
        return {int(text)}
    except ValueError:
        return set()


class EncounterSet:
    def __init__(self, data, project):
        self.data = data
        self.project = project
        if 'id' not in self.data:
            self.data['id'] = str(uuid4())
        self.get = self.data.get
        self.__getitem__ = self.data.__getitem__

    @property
    def name(self):
        return self.data['name']

    @name.setter
    def name(self, value):
        self.data['name'] = value

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

        from shoggoth.project import sort_cards
        sort_cards(result)
        return result

    @staticmethod
    def is_valid(data):
        return 'name' in data and 'icon' in data

    @property
    def dirty(self):
        return self.project.is_dirty(self.id)

    @dirty.setter
    def dirty(self, value):
        self.project.set_dirty(self.id, value)

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
        cards = self.cards
        manual_numbers = set()
        for card in cards:
            if card.get('enumerated') == 'manual':
                manual_numbers |= parse_number_span(card.data.get('encounter_number'))

        current_number = 1
        for card in cards:
            enumerated = card.get('enumerated')
            if enumerated in ('ignored', 'manual'):
                continue
            amount = card.amount
            while any((current_number + i) in manual_numbers for i in range(amount)):
                current_number += 1
            if amount > 1:
                card.data['encounter_number'] = f'{current_number}-{current_number+amount-1}'
            else:
                card.data['encounter_number'] = f'{current_number}'
            current_number += amount
        self.data['card_amount'] = max(current_number - 1, max(manual_numbers, default=0))

    def set(self, key, value):
        print('encounter set, setting', key, value)
        self.data[key] = value
        self.dirty = True
        print('is dirty', self.dirty)

