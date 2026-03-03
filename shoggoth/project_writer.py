import json


class Writer:
    def __init__(self, project):
        self.project = project

    def save_project(self, project):
        """Save data to file"""
        with open(project.file_path, 'r') as f:
            orig_data = json.load(f)
        for key in project.data:
            if key in ('cards', 'encounter_sets'):
                continue
            orig_data[key] = project.data[key]

        with open(project.file_path, 'w') as f:
            json.dump(project.data, f, indent=4)
        self.dirty = False

    def save_card(self, card):
        print('saving card of project', card.id)
        with open(self.project.file_path, 'r') as f:
            orig_data = json.load(f)
        index = None
        for key, value in enumerate(orig_data['cards']):
            if value['id'] == card.id:
                index = key
                break
        if index:
            orig_data['cards'][index] = card.data
        with open(self.project.file_path, 'w') as f:
            json.dump(orig_data, f, indent=4)
        self.project.set_dirty(card.id, False)

    def save_all(self):
        """Save data to file"""
        with open(self.project.file_path, 'w') as f:
            json.dump(self.project.data, f, indent=4)
        self.project.clear_dirty()

    def save_face(self):
        pass

    def save_encounter(self):
        pass


class TranslationWriter(Writer):
    def __init__(self, translation):
        self.translation = translation

    def save_project(self, project):
        """Save data to file"""
        with open(self.translation.file_path, 'r') as f:
            orig_data = json.load(f)
        orig_data["project_name"] = project.name
        orig_data['guides'] = project.data['guides']

        with open(self.translation.file_path, 'w') as f:
            json.dump(orig_data, f, indent=4)
        project.dirty = False

    def save_encounter_set(self, encounter_set):
        """Save data to file"""
        with open(self.translation.file_path, 'r') as f:
            orig_data = json.load(f)
        if not orig_data.get('encounter_sets'):
            orig_data["encounter_sets"] = {}

        orig_data['encounter_sets'][encounter_set.id] = {}
        orig_data['encounter_sets'][encounter_set.id]['name'] = encounter_set.name

        with open(self.translation.file_path, 'w') as f:
            json.dump(orig_data, f, indent=4)

    def save_card(self, card):
        with open(self.translation.file_path, 'r') as f:
            orig_data = json.load(f)
        if not orig_data.get('cards'):
            orig_data["cards"] = {}

        orig_data['cards'][card.id] = {}
        orig_data['cards'][card.id]['name'] = card.name

        for side in ('front', 'back'):
            orig_data['cards'][card.id][side] = {}
            for field in ('name', 'text', 'flavor_text'):
                if field in card.data[side]:
                    orig_data['cards'][card.id][side][field] = card.data[side][field]

        with open(self.translation.file_path, 'w') as f:
            json.dump(orig_data, f, indent=4)

    def save_all(self):
        """Save data to file"""
        project = self.translation.project
        for encounter_set in project.encounter_sets:
            if encounter_set.dirty:
                self.save_encounter_set(encounter_set)
        for card in project.get_all_cards():
            if card.dirty:
                self.save_card(card)
        self.save_project(project)
