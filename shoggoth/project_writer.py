import json
import os
from pathlib import Path
import tempfile


class Writer:
    def __init__(self, project):
        self.project = project

    def save_project(self, project):
        """Save data to file"""
        with open(project.file_path, 'r', encoding='utf-8') as f:
            orig_data = json.load(f)
        for key in project.data:
            if key in ('cards', 'encounter_sets'):
                continue
            orig_data[key] = project.data[key]

        self.dirty = False
        atomic_write(project.file_path, json.dumps(project.data, indent=4))

    def save_card(self, card):
        with open(self.project.file_path, 'r', encoding='utf-8') as f:
            orig_data = json.load(f)
        index = None
        for key, value in enumerate(orig_data['cards']):
            if value['id'] == card.id:
                index = key
                break
        if index:
            orig_data['cards'][index] = card.data

        self.project.set_dirty(card.id, False)
        atomic_write(self.project.file_path, json.dumps(orig_data, indent=4))

    def save_all(self):
        """Save data to file"""
        self.project.clear_dirty()
        atomic_write(self.project.file_path, json.dumps(self.project.data, indent=4))

    def save_face(self):
        pass

    def save_encounter(self):
        pass

    def save_encounter_set(self, encounter_set):
        pass


class TranslationWriter(Writer):
    def __init__(self, translation):
        self.translation = translation

    def save_project(self, project):
        """Save data to file"""
        with open(self.translation.file_path, 'r', encoding='utf-8') as f:
            orig_data = json.load(f)
        orig_data["project_name"] = project.name
        orig_data['guides'] = project.data['guides']

        project.dirty = False
        atomic_write(self.translation.file_path, json.dumps(orig_data, indent=4))

    def save_encounter_set(self, encounter_set):
        """Save data to file"""
        print('saving encounter set', encounter_set)
        with open(self.translation.file_path, 'r', encoding='utf-8') as f:
            orig_data = json.load(f)
        if not orig_data.get('encounter_sets'):
            orig_data["encounter_sets"] = {}

        orig_data['encounter_sets'][encounter_set.id] = {}
        orig_data['encounter_sets'][encounter_set.id]['name'] = encounter_set.name

        encounter_set.dirty = False
        atomic_write(self.translation.file_path, json.dumps(orig_data, indent=4))

    def save_card(self, card):
        with open(self.translation.file_path, 'r', encoding='utf-8') as f:
            orig_data = json.load(f)
        if not orig_data.get('cards'):
            orig_data["cards"] = {}

        orig_data['cards'][card.id] = {}
        orig_data['cards'][card.id]['name'] = card.name

        for side in ('front', 'back'):
            orig_data['cards'][card.id][side] = {}
            for field in ('name', 'text', 'flavor_text', 'subtitle', 'victory', 'traits', 'entries', 'difficulty'):
                if field in card.data[side]:
                    orig_data['cards'][card.id][side][field] = card.data[side][field]

        card.dirty = False
        atomic_write(self.translation.file_path, json.dumps(orig_data, indent=4))

    def save_all(self):
        """Save data to file"""
        project = self.translation.project
        for encounter_set in project.encounter_sets:
            print('checking encounter set', encounter_set, encounter_set.dirty)
            if encounter_set.dirty:
                self.save_encounter_set(encounter_set)
        for card in project.get_all_cards():
            if card.dirty:
                self.save_card(card)
        self.save_project(project)


def atomic_write(filepath, data, mode="w", **kwargs):
    path = Path(filepath)
    if "b" not in mode:
        # never let Windows fall back to its locale charset for project files
        kwargs.setdefault("encoding", "utf-8")
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, mode, **kwargs) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())  # ensure it's on disk before rename
        os.replace(tmp_path, path)  # atomic on both POSIX and Windows
    except Exception:
        os.unlink(tmp_path)  # clean up on failure
        raise
