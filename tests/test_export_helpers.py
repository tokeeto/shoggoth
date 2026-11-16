"""SCED GMNotes metadata built from card data (export_helpers.build_gm_notes)."""
import pytest

from shoggoth.export_helpers import build_gm_notes
from shoggoth.project import Project

from conftest import card_data, project_data


def gm_notes_for(text):
    project = Project('unused.shoggoth', project_data(cards=[
        card_data('a', front={'type': 'asset', 'text': text}),
    ]))
    return build_gm_notes(project.get_card('a'))


AMMO = [{'count': 3, 'type': 'Ammo', 'token': 'resource'}]


@pytest.mark.parametrize('text', [
    'Uses (3 ammo).',
    # Uses after a keyword on the same line (reported bug: only found at the start)
    'Fast. Uses (3 ammo).',
])
def test_uses_are_found_in_card_text(defaults, text):
    defaults('asset', {})
    defaults('player', {})
    assert gm_notes_for(text).get('uses') == AMMO
