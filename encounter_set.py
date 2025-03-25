from card import Card


class EncounterSet:
    def __init__(self, data):
        self.name = data['name']
        self.icon = data['icon']
        self.data = data
        self.get = data.get
        self.__getitem__ = self.data.__getitem__

    @property
    def cards(self):
        for c in self.data['cards']:
            yield Card(c)

    @staticmethod
    def is_valid(data):
        return 'cards' in data and 'name' in data and 'icon' in data
