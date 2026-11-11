"""Entering a Victory value shortens the text region so both fit; clearing it
gives the text its default size back (FaceEditor._fit_text_region_to_victory)."""
import pytest

pytest.importorskip('PySide6')

from shoggoth.project import Project  # noqa: E402
from shoggoth.ui.face_editor import FaceEditor  # noqa: E402

from conftest import card_data, project_data  # noqa: E402


class StubEditor:
    """Just what _fit_text_region_to_victory touches."""
    def __init__(self, face):
        self.face = face

    def parent(self):
        return None

    fit = FaceEditor._fit_text_region_to_victory


TEXT = {'x': 150, 'y': 530, 'width': 1340, 'height': 605}
VICTORY = {'x': 366, 'y': 1048, 'width': 900, 'height': 72}


@pytest.fixture
def face(defaults):
    defaults('enemy', {'text_region': TEXT, 'victory_region': VICTORY})
    project = Project('unused.shoggoth', project_data(cards=[card_data('a', front={'type': 'enemy'})]))
    return project.get_card('a').front


def test_victory_shrinks_overlapping_text_region(face):
    face.set('victory', 'Victory 1.')
    StubEditor(face).fit('victory')
    assert face.data['text_region'] == {'inherit': True, 'height': 1048 - 530}
    assert face['text_region'] == TEXT | {'height': 518}


def test_clearing_victory_removes_the_override(face):
    face.set('victory', 'Victory 1.')
    StubEditor(face).fit('victory')
    face.set('victory', None)
    StubEditor(face).fit('victory')
    assert 'text_region' not in face.data
    assert face['text_region'] == TEXT


def test_other_overlay_keys_survive(face):
    face.set('text_region', {'inherit': True, 'x': 200})
    face.set('victory', 'Victory 1.')
    StubEditor(face).fit('victory')
    assert face.data['text_region'] == {'inherit': True, 'x': 200, 'height': 518}
    face.set('victory', None)
    StubEditor(face).fit('victory')
    assert face.data['text_region'] == {'inherit': True, 'x': 200}


def test_user_region_is_left_alone(face):
    mine = {'x': 1, 'y': 2, 'width': 3, 'height': 4000}
    face.set('text_region', mine)
    face.set('victory', 'Victory 1.')
    StubEditor(face).fit('victory')
    assert face.data['text_region'] == mine


def test_no_overlap_stores_nothing(defaults):
    defaults('enemy', {'text_region': TEXT | {'height': 100}, 'victory_region': VICTORY})
    project = Project('unused.shoggoth', project_data(cards=[card_data('a', front={'type': 'enemy'})]))
    face = project.get_card('a').front
    face.set('victory', 'Victory 1.')
    StubEditor(face).fit('victory')
    assert 'text_region' not in face.data


def test_default_value_ignores_own_value(face):
    face.set('text_region', {'inherit': True, 'height': 10})
    assert face.default_value('text_region') == TEXT
    assert face.default_value('nothing_here', 'x') == 'x'
