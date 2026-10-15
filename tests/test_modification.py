"""Modification projects (translations): only the difference is stored, and
the parent is never written."""
import json

import pytest

from shoggoth.modification import ModificationProject, apply, diff, element_change, ADDED
from shoggoth.project import Project

from conftest import card_data, project_data


@pytest.mark.parametrize('base, new', [
    ({}, {}),
    ({'a': 1}, {'a': 2}),
    ({'a': 1}, {}),
    ({}, {'a': {'b': 1}}),
    ({'a': {'b': 1, 'c': 2}}, {'a': {'b': 1, 'c': 3, 'd': 4}}),
    ({'a': {'b': 1}}, {'a': 'now a string'}),
    ({'a': [1, 2]}, {'a': [2, 1]}),
    ({'a': {'b': {'c': 1}}}, {'a': {'b': {}}}),
])
def test_apply_diff_roundtrip(base, new):
    changes = diff(base, new)
    assert apply(json.loads(json.dumps(base)), changes) == new


def test_diff_only_lists_changes():
    assert diff({'a': 1, 'b': {'c': 1, 'd': 2}}, {'a': 1, 'b': {'c': 1, 'd': 3}}) == {'b': {'d': 3}}


def test_element_change():
    assert element_change({'a': 1}, {'a': 1}) is ...
    assert element_change({'a': 1}, None) is None
    assert element_change(None, None) is ...
    assert element_change(None, {'a': 1}) == {'a': 1, ADDED: True}


@pytest.fixture
def parent(write_project):
    data = project_data(
        cards=[
            card_data('a', 'Original A', front={'type': 'asset', 'text': 'Hello'}),
            card_data('b', 'Original B'),
        ],
        encounter_sets=[{'id': 'set', 'name': 'Set', 'icon': ''}],
    )
    return write_project(data, 'parent.shoggoth')


def test_create_edit_save_reload(parent, tmp_path):
    parent_text = parent.read_text(encoding='utf-8')
    mod_path = tmp_path / 'translation.shoggoth'
    mod = ModificationProject.create(mod_path, parent, name='Oversat', language='da')
    assert isinstance(Project.load(mod_path), ModificationProject)

    mod.get_card('a').front.set('text', 'Hej')
    mod.save_all()

    stored = json.loads(mod_path.read_text(encoding='utf-8'))
    assert stored['type'] == 'modification'
    assert stored['parent'] == 'parent.shoggoth'
    assert stored['cards'] == {'a': {'front': {'text': 'Hej'}}}
    assert stored['project'] == {'name': 'Oversat', 'meta': {'language': 'da'}}

    reloaded = Project.load(mod_path)
    assert reloaded.get_card('a').front['text'] == 'Hej'
    assert reloaded.get_card('a').name == 'Original A'
    assert reloaded.original_card('a').front['text'] == 'Hello'
    assert parent.read_text(encoding='utf-8') == parent_text


def test_parent_is_read_only(parent, tmp_path):
    mod = ModificationProject.create(tmp_path / 'mod.shoggoth', parent)
    with pytest.raises(PermissionError):
        mod.parent.save_all()


def test_saving_one_card(parent, tmp_path):
    mod_path = tmp_path / 'mod.shoggoth'
    mod = ModificationProject.create(mod_path, parent)
    mod.get_card('a').set('name', 'A!')
    mod.get_card('b').set('name', 'B!')
    mod.get_card('a').save()
    stored = json.loads(mod_path.read_text(encoding='utf-8'))
    assert stored['cards'] == {'a': {'name': 'A!'}}  # b's edit is not saved yet


def test_added_and_removed_elements(parent, tmp_path):
    mod_path = tmp_path / 'mod.shoggoth'
    mod = ModificationProject.create(mod_path, parent)
    mod.data['cards'] = [c for c in mod.data['cards'] if c['id'] != 'b']
    mod.data['cards'].append(card_data('c', 'Added'))
    mod.save_all()

    stored = json.loads(mod_path.read_text(encoding='utf-8'))
    assert stored['cards']['b'] is None
    assert stored['cards']['c'][ADDED] is True

    reloaded = Project.load(mod_path)
    assert sorted(c['id'] for c in reloaded.data['cards']) == ['a', 'c']


def test_parent_change_shows_through(parent, tmp_path):
    mod_path = tmp_path / 'mod.shoggoth'
    mod = ModificationProject.create(mod_path, parent)
    mod.get_card('a').front.set('text', 'Hej')
    mod.save_all()

    data = json.loads(parent.read_text(encoding='utf-8'))
    data['cards'][1]['name'] = 'Renamed in parent'
    parent.write_text(json.dumps(data), encoding='utf-8')

    reloaded = Project.load(mod_path)
    assert reloaded.get_card('b').name == 'Renamed in parent'
    assert reloaded.get_card('a').front['text'] == 'Hej'


def test_change_to_card_missing_from_parent_is_kept(parent, tmp_path):
    mod_path = tmp_path / 'mod.shoggoth'
    raw = {'type': 'modification', 'id': 'm', 'parent': 'parent.shoggoth', 'project': {},
           'cards': {'gone': {'name': 'orphan'}}, 'encounter_sets': {}, 'guides': {}}
    mod_path.write_text(json.dumps(raw), encoding='utf-8')
    mod = Project.load(mod_path)
    mod.save_all()
    assert json.loads(mod_path.read_text(encoding='utf-8'))['cards'] == {'gone': {'name': 'orphan'}}


def test_legacy_translation_sidecar_loads(parent, tmp_path):
    sidecar = tmp_path / 'old_translation.json'
    sidecar.write_text(json.dumps({
        'language': 'fr', 'project': 'parent.shoggoth', 'project_name': 'Français',
        'cards': {'a': {'front': {'text': 'Bonjour'}}}, 'encounter_sets': {},
    }), encoding='utf-8')
    mod = Project.load(sidecar)
    assert isinstance(mod, ModificationProject)
    assert mod.get_card('a').front['text'] == 'Bonjour'
