"""Loading and saving project files: nothing may get lost or mangled."""
import json

import pytest

from shoggoth.card import Card
from shoggoth.project import Project
from shoggoth.project_writer import order_dict

from conftest import card_data, project_data


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def test_save_and_reload_keeps_everything(load_project):
    data = project_data(
        cards=[
            card_data('a', 'Æblegrød — “quoted” 日本', front={'type': 'asset', 'text': '<b>Fight.</b>', 'custom_key': [1, 2]}),
            card_data('b', 'Second', meta={'folder': 'x/y'}),
        ],
        encounter_sets=[{'id': 'set', 'name': 'Set', 'icon': 'icon.png', 'order': 2}],
        default_copyright='© me',
        meta={'language': 'fr', 'something_new': {'nested': True}},
    )
    project = load_project(data)
    project.save_all()

    reloaded = Project.load(project.file_path)
    saved = reloaded.data
    saved['meta'].pop('dirty', None)
    assert saved == data


def test_save_writes_unicode_unescaped(load_project):
    project = load_project(project_data(cards=[card_data('a', 'Ærø')]))
    project.save_all()
    text = open(project.file_path, encoding='utf-8').read()
    assert 'Ærø' in text


def test_save_leaves_no_temp_files(load_project, tmp_path):
    project = load_project(project_data(cards=[card_data('a')]))
    project.save_all()
    project.save_all()
    assert sorted(p.name for p in tmp_path.iterdir()) == ['project.shoggoth']


def test_saved_file_has_name_and_id_first(load_project):
    project = load_project(project_data(cards=[card_data('a')]))
    project.save_all()
    keys = list(read_json(project.file_path).keys())
    assert keys[:2] == ['name', 'id']


def test_order_dict_keeps_list_order():
    data = {'z': 1, 'cards': [{'b': 1, 'name': 'x'}, {'name': 'y'}], 'name': 'n'}
    ordered = order_dict(data)
    assert list(ordered) == ['name', 'cards', 'z']
    assert [c['name'] for c in ordered['cards']] == ['x', 'y']
    assert list(ordered['cards'][0]) == ['name', 'b']


def test_missing_id_is_created_and_kept(write_project):
    data = project_data()
    del data['id']
    project = Project.load(write_project(data))
    assert project.id
    project.save_all()
    assert Project.load(project.file_path).id == project.id


def test_invalid_encounter_set_is_rejected(write_project):
    path = write_project(project_data(encounter_sets=[{'name': 'no icon'}]))
    with pytest.raises(Exception):
        Project.load(path)


@pytest.mark.parametrize('index', [0, 1])
def test_saving_one_card_writes_only_that_card(load_project, index):
    project = load_project(project_data(cards=[card_data('a', 'A'), card_data('b', 'B')]))
    card = project.get_card(['a', 'b'][index])
    card.set('name', 'Changed')
    card.save()

    names = [c['name'] for c in read_json(project.file_path)['cards']]
    expected = ['A', 'B']
    expected[index] = 'Changed'
    assert names == expected
    assert not card.dirty


def test_saving_a_new_card_adds_it(load_project):
    project = load_project(project_data(cards=[card_data('a', 'A')]))
    project.data['cards'].append(card_data('new', 'New'))
    project.get_card('new').save()
    assert [c['id'] for c in read_json(project.file_path)['cards']] == ['a', 'new']


# ── Changes made outside Shoggoth ────────────────────────────────────────

def test_own_saves_are_not_external_changes(load_project):
    project = load_project(project_data(cards=[card_data('a')]))
    assert not project.has_external_changes()
    project.get_card('a').set('name', 'Edited')
    assert not project.has_external_changes()  # unsaved edits aren't on disk
    project.save_all()
    assert not project.has_external_changes()


def test_reformatting_is_not_an_external_change(load_project):
    project = load_project(project_data(cards=[card_data('a')]))
    data = read_json(project.file_path)
    with open(project.file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, sort_keys=True)  # different order and indentation
    assert not project.has_external_changes()


def test_outside_edit_is_detected_and_reload_picks_it_up(load_project):
    project = load_project(project_data(cards=[card_data('a', 'Mine')]))
    data = read_json(project.file_path)
    data['cards'][0]['name'] = 'Theirs'
    with open(project.file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    assert project.has_external_changes()
    project.reload()
    assert not project.has_external_changes()
    assert project.get_card('a').name == 'Theirs'


def test_acknowledge_external_changes(load_project):
    project = load_project(project_data(cards=[card_data('a')]))
    data = read_json(project.file_path)
    data['name'] = 'Renamed elsewhere'
    with open(project.file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    project.acknowledge_external_changes()
    assert not project.has_external_changes()


def test_save_as_writes_new_file_and_keeps_old(load_project, tmp_path):
    project = load_project(project_data(cards=[card_data('a')]))
    old_path = project.file_path
    old_text = open(old_path, encoding='utf-8').read()
    project.get_card('a').set('name', 'Moved')

    project.save_as(tmp_path / 'copy.shoggoth')
    assert project.file_path == str(tmp_path / 'copy.shoggoth')
    assert read_json(tmp_path / 'copy.shoggoth')['cards'][0]['name'] == 'Moved'
    assert open(old_path, encoding='utf-8').read() == old_text


def test_save_as_failure_keeps_old_path(load_project, tmp_path):
    project = load_project(project_data())
    old_path = project.file_path
    with pytest.raises(Exception):
        project.save_as(tmp_path / 'missing_folder' / 'copy.shoggoth')
    assert project.file_path == old_path


# ── Dirty tracking / change notification ─────────────────────────────────

def test_editing_marks_dirty_and_notifies(load_project):
    project = load_project(project_data(cards=[card_data('a')]))
    events = []
    Project.add_change_listener(lambda p, kind, element_id, changed: events.append((kind, element_id, changed)))

    card = project.get_card('a')
    card.front.set('text', 'new text')
    assert card.dirty
    assert ('cards', 'a', True) in events

    project.save_all()
    assert not project.get_card('a').dirty


def test_setting_same_value_does_not_dirty(load_project):
    project = load_project(project_data(cards=[card_data('a', front={'type': 'asset', 'text': 'same'})]))
    card = project.get_card('a')
    card.front.set('text', 'same')
    assert not card.dirty


def test_setting_none_removes_key(load_project):
    project = load_project(project_data(cards=[card_data('a', front={'type': 'asset', 'text': 'x'})]))
    card = project.get_card('a')
    card.front.set('text', None)
    assert 'text' not in card.data['front']


def test_card_without_id_gets_one():
    project = Project('unused.shoggoth', project_data())
    data = {'name': 'x', 'front': {'type': 'asset'}, 'back': {'type': 'player'}}
    card = Card(data, project)
    assert card.id and data['id'] == card.id
