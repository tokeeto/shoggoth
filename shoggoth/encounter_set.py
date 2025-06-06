from shoggoth.card import Card


class EncounterSet:
    def __init__(self, data, expansion=None):
        self.name = data['name']
        self.icon = data['icon']
        self.code = data.get('code', 'xx')
        self.data = data
        self.expansion = expansion
        self.get = data.get
        self.__getitem__ = self.data.__getitem__

    def __eq__(self, other):
        return self.data == other.data and self.expansion == other.expansion

    @property
    def cards(self):
        for c in self.data['cards']:
            yield Card(c, encounter=self, expansion=self.expansion)

    @staticmethod
    def is_valid(data):
        return 'cards' in data and 'name' in data and 'icon' in data

    def add_card(self, card):
        self.data['cards'].append(card.data)

    def assign_card_numbers(self):
        current_number = 1
        for card in self.cards:
            amount = card.data.get('amount', 2)
            if amount > 1:
                card.data['encounter_number'] = f'{current_number}-{current_number+amount-1}'
            else:
                card.data['encounter_number'] = f'{current_number}'
            current_number += amount
        self.data['card_amount'] = current_number-1
