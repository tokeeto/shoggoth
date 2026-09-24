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
        self._write(project.data)

    def _write(self, data):
        """Writes the project file, and tells the project what it now holds."""
        text = json.dumps(order_dict(data), indent=4)
        atomic_write(self.project.file_path, text)
        self.project.remember_saved(json.loads(text))

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
        else:
            orig_data['cards'][card.id] = card.data

        self.project.set_dirty(card.id, False)
        self._write(orig_data)

    def save_all(self):
        """Save data to file"""
        self.project.clear_dirty()
        self._write(self.project.data)

    def save_face(self):
        pass

    def save_encounter(self):
        pass

    def save_encounter_set(self, encounter_set):
        pass


class CloudWriter(Writer):
    """Writer for projects in the cloud folder.

    Saving works exactly as for any other project: edits live in memory until
    the user saves, and closing without saving discards them. What a cloud
    project adds is that a save is also the moment the change is *shared* --
    once the file is written, whoever is syncing this project (see
    shoggoth.cloud.sync.CloudSyncController, which sets `on_saved` when it
    attaches) is told what was saved and sends it to the cloud.
    """

    # callback(project, ids): `ids` is the set of saved element ids, or None
    # when the whole project was saved
    on_saved = None

    def save_all(self):
        super().save_all()
        self._saved(None)

    def save_card(self, card):
        super().save_card(card)
        self._saved({card.id})

    def _saved(self, ids):
        if self.on_saved is not None:
            self.on_saved(self.project, ids)


class TranslationWriter(Writer):
    def __init__(self, translation):
        self.translation = translation

    def save_project(self, project):
        """Save data to file"""
        with open(self.translation.file_path, 'r', encoding='utf-8') as f:
            orig_data = json.load(f)
        orig_data["project_name"] = project.name
        orig_data['guides'] = project.data['guides']
        # The translation's own metadata (currently just cloud_translation_id,
        # see Translation.get_meta/set_meta) -- deliberately not project.data
        # ['meta'], which belongs to the overlaid *base* project and isn't
        # this writer's to persist.
        orig_data['meta'] = self.translation.data.get('meta', {})

        project.dirty = False
        atomic_write(self.translation.file_path, json.dumps(order_dict(orig_data), indent=4))

    def save_encounter_set(self, encounter_set):
        """Save data to file"""
        with open(self.translation.file_path, 'r', encoding='utf-8') as f:
            orig_data = json.load(f)
        if not orig_data.get('encounter_sets'):
            orig_data["encounter_sets"] = {}

        orig_data['encounter_sets'][encounter_set.id] = {}
        orig_data['encounter_sets'][encounter_set.id]['name'] = encounter_set.name

        encounter_set.dirty = False
        atomic_write(self.translation.file_path, json.dumps(order_dict(orig_data), indent=4))

    def save_card(self, card):
        with open(self.translation.file_path, 'r', encoding='utf-8') as f:
            orig_data = json.load(f)
        if not orig_data.get('cards'):
            orig_data["cards"] = {}

        orig_data['cards'][card.id] = {}
        orig_data['cards'][card.id]['name'] = card.name
        if card.language:
            orig_data['cards'][card.id]['language'] = card.language

        for side in ('front', 'back'):
            orig_data['cards'][card.id][side] = {}
            for field in ('name', 'text', 'flavor_text', 'subtitle', 'victory', 'traits', 'entries', 'difficulty', 'chaos_extra', 'tracking', 'checkbox_entries'):
                if field in card.data[side]:
                    orig_data['cards'][card.id][side][field] = card.data[side][field]

        card.dirty = False
        atomic_write(self.translation.file_path, json.dumps(order_dict(orig_data), indent=4))

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

KEY_ORDER = [
    "name",
    "id",
    "code",
    "default_copyright",
    "icon",
    "meta",
    "cards",
    "encounter_sets",
    "amount",
    "investigator",
    "project_number",
    "copyright",
    "front",
    "back",
]

def order_dict(data):
    """Return a new dict with preferred keys first, followed by remaining keys."""
    if isinstance(data, dict):
        ordered = {}

        for key in KEY_ORDER:
            if key in data:
                ordered[key] = order_dict(data[key])

        for key in sorted(data.keys()):
            if key not in KEY_ORDER:
                ordered[key] = order_dict(data[key])

        return ordered

    if isinstance(data, list):
        return [order_dict(item) for item in data]

    return data
