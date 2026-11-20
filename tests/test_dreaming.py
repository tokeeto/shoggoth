"""Dreaming levels: `"dreaming": true` on a face swaps the class in the level
overlay for `dreaming` (renderer/card_renderer.py:render_level), and the level
row of every editor that has one carries a checkbox that sets it."""
import pytest

from shoggoth.project import Project
from shoggoth.renderer.card_renderer import CardRenderer
from shoggoth.files import overlay_dir

from conftest import card_data, project_data

LEVEL_REGION = {'x': 100, 'y': 100, 'width': 242, 'height': 242}

# Stored level value -> the {level} the overlay file name gets.
LEVELS = [
    (None, 'no_level'),
    ('None', 'no_level'),
    ('0', '0'),
    ('1', '1'),
    ('2', '2'),
    ('3', '3'),
    ('4', '4'),
    ('5', '5'),
    ('Custom', 'custom'),
]


class OverlaySpy:
    """Just what render_level touches: records the overlay path it loads."""
    def __init__(self):
        self.paths = []

    def get_resized_cached(self, path, size):
        self.paths.append(path)
        from PIL import Image
        return Image.new('RGBA', size)

    render_level = CardRenderer.render_level


def overlay_for(face):
    from PIL import Image
    spy = OverlaySpy()
    spy.render_level(Image.new('RGBA', (500, 500)), face)
    assert len(spy.paths) == 1
    return spy.paths[0].name


def make_face(defaults, card_type='asset', **front):
    defaults(card_type, {
        'level_region': LEVEL_REGION,
        'level_overlay': '{card_class}_{level}.png',
    })
    project = Project('unused.shoggoth', project_data(cards=[
        card_data('a', front={'type': card_type, 'classes': ['seeker'], **front}),
    ]))
    return project.get_card('a').front


@pytest.mark.parametrize('card_type', ['asset', 'event', 'skill'])
@pytest.mark.parametrize('level, file_level', LEVELS)
def test_dreaming_level_uses_dreaming_overlay(defaults, card_type, level, file_level):
    face = make_face(defaults, card_type, level=level, dreaming=True)
    assert overlay_for(face) == f'dreaming_{file_level}.png'


@pytest.mark.parametrize('level, file_level', LEVELS)
def test_without_dreaming_level_uses_class_overlay(defaults, level, file_level):
    face = make_face(defaults, level=level)
    assert overlay_for(face) == f'seeker_{file_level}.png'


@pytest.mark.parametrize('dreaming', [False, None, ''])
def test_falsy_dreaming_is_not_dreaming(defaults, dreaming):
    face = make_face(defaults, level='2', dreaming=dreaming)
    assert overlay_for(face) == 'seeker_2.png'


def test_dreaming_replaces_multiclass_overlay(defaults):
    face = make_face(defaults, level='3', dreaming=True, classes=['seeker', 'mystic'])
    assert overlay_for(face) == 'dreaming_3.png'


def test_fixed_overlay_ignores_dreaming(defaults):
    """Templates whose overlay name has no {card_class} (e.g. skill_{level}.png,
    weakness_no_level.png) are unaffected."""
    defaults('skill', {'level_region': LEVEL_REGION, 'level_overlay': 'skill_{level}.png'})
    project = Project('unused.shoggoth', project_data(cards=[
        card_data('a', front={'type': 'skill', 'level': '4', 'dreaming': True}),
    ]))
    assert overlay_for(project.get_card('a').front) == 'skill_4.png'


@pytest.mark.assets
@pytest.mark.parametrize('level', ['0', '1', '2', '3', '4', '5'])
def test_asset_pack_has_dreaming_overlays(level):
    assert (overlay_dir / 'levels' / f'dreaming_{level}.png').is_file()


# --- Editor checkbox ---------------------------------------------------------

@pytest.fixture(scope='module')
def qapp():
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('editor_name', ['AssetEditor', 'EventEditor', 'SkillEditor'])
def test_level_editors_have_dreaming_checkbox(qapp, defaults, editor_name):
    from PySide6.QtWidgets import QCheckBox
    from shoggoth.ui import player_editors

    face = make_face(defaults, level='2')
    editor = getattr(player_editors, editor_name)(face)
    checkbox = editor.fields['dreaming']
    assert isinstance(checkbox, QCheckBox)
    assert not checkbox.isChecked()

    checkbox.setChecked(True)
    assert face.data['dreaming'] is True
    assert overlay_for(face) == 'dreaming_2.png'

    # Unchecking removes the key rather than storing False.
    checkbox.setChecked(False)
    assert 'dreaming' not in face.data
    assert overlay_for(face) == 'seeker_2.png'


def _editor_with_cost(defaults, **front):
    from shoggoth.ui.player_editors import AssetEditor
    defaults('asset', {'level_region': LEVEL_REGION, 'level_overlay': '{card_class}_{level}.png', 'cost': '---'})
    project = Project('unused.shoggoth', project_data(cards=[
        card_data('a', front={'type': 'asset', 'classes': ['seeker'], 'level': '2', **front}),
    ]))
    face = project.get_card('a').front
    return AssetEditor(face), face


def test_dreaming_blanks_cost(qapp, defaults):
    """Dreaming cards use alternative costs: the cost is stored as a blank, not
    removed (which would fall back to the default '---')."""
    editor, face = _editor_with_cost(defaults, cost='3')
    editor.fields['dreaming'].setChecked(True)
    assert face.data['cost'] == ' '
    assert face.get('cost') == ' '
    assert editor.fields['cost'].text() == ' '

    # Unchecking gives the default back.
    editor.fields['dreaming'].setChecked(False)
    assert 'cost' not in face.data
    assert face.get('cost') == '---'
    assert editor.fields['cost'].text() == '---'


def test_unchecking_dreaming_keeps_a_typed_cost(qapp, defaults):
    editor, face = _editor_with_cost(defaults)
    editor.fields['dreaming'].setChecked(True)
    editor.fields['cost'].setText('2')
    assert face.data['cost'] == '2'
    editor.fields['dreaming'].setChecked(False)
    assert face.data['cost'] == '2'


def test_loading_a_dreaming_card_leaves_cost_alone(qapp, defaults):
    editor, face = _editor_with_cost(defaults, dreaming=True, cost='4')
    assert editor.fields['dreaming'].isChecked()
    assert face.data['cost'] == '4'


def test_editor_loads_stored_dreaming(qapp, defaults):
    from shoggoth.ui.player_editors import AssetEditor
    face = make_face(defaults, level='1', dreaming=True)
    assert AssetEditor(face).fields['dreaming'].isChecked()
