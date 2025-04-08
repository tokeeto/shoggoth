from card import Card


class EncounterSet:
    def __init__(self, data, expansion=None):
        self.name = data['name']
        self.icon = data['icon']
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
