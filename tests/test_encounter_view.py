"""The Encounter group of an encounter set opens the encounter view: enemies
and treacheries one item per copy, with per-copy stats above them."""
import pytest

from tests.conftest import card_data, project_data

QtWidgets = pytest.importorskip('PySide6.QtWidgets')


@pytest.fixture
def encounter_project(load_project, defaults):
    for name in ('enemy', 'treachery', 'location', 'act'):
        defaults(name, {'card_type': name})
    defaults('encounter', {})
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def card(card_id, type, amount=1, **front):
        return card_data(card_id, card_id.title(), front={'type': type, **front},
                         back={'type': 'encounter'}, encounter_set='set-1', amount=amount)
    return load_project(project_data(
        encounter_sets=[{'id': 'set-1', 'name': 'The Gathering', 'icon': ''}],
        cards=[
            card('ghoul', 'enemy', 3, health='3', attack='2', evade='2'),
            card('priest', 'enemy', 1, health='5<per>', attack='4', evade='<dash>'),
            card('rats', 'treachery', 3, text='Test <willpower> (3). If you fail, take 1 horror and 2 damage.'),
            card('grasp', 'treachery', 2, text='test <agi>(X) and then Test <int> (7). Take 1 horror, then 1 more horror.'),
            card('fog', 'treachery', 1, text='Heal all damage from the enemy with the most horror.'),
            card('study', 'location'), card('act1', 'act'),
        ],
    ))


def test_bucket():
    from shoggoth.ui.encounter_view import bucket
    assert [bucket(v) for v in ('0', '1', '5', '6', '9', 'X', '<dash>', '2<per>', None, '')] == \
        ['1', '1', '5', '6+', '6+', 'X', 'X', 'X', None, None]


def test_skill_tests_naive_parse():
    from shoggoth.ui.encounter_view import skill_tests
    assert skill_tests('Test <willpower> (3). Test <com>(X)') == [('willpower', '3'), ('combat', 'X')]
    assert skill_tests('no tests') == []


def test_stats_count_copies(encounter_project):
    from shoggoth.ui import encounter_view as ev
    enemies, treacheries, others = ev.split_encounter_cards(
        ev.encounter_cards(encounter_project.get_encounter_set('set-1')))
    assert [c.id for c in others] == []

    stats = ev.enemy_stats(enemies, treacheries)
    assert stats['health'] == (9, 5)
    assert (stats['count'], stats['deck']) == (4, 10)
    assert stats['combat']['buckets']['2'] == 3 and stats['combat']['buckets']['4'] == 1
    assert stats['combat']['median'] == 2 and stats['combat']['mean'] == 2.5
    assert stats['evade']['buckets']['X'] == 1 and stats['evade']['mean'] == 2

    t = ev.treachery_stats(treacheries)
    assert t['total'] == 6
    assert t['counts'] == {'willpower': 3, 'intellect': 2, 'combat': 0, 'agility': 2}
    assert t['by_bucket']['willpower']['3'] == 3
    assert t['by_bucket']['intellect']['6+'] == 2
    assert t['by_bucket']['agility']['X'] == 2
    assert t['harm'] == {'damage': 3, 'horror': 5, 'either': 0}


def test_view_deals_one_item_per_copy(encounter_project, monkeypatch):
    from shoggoth.ui import card_board, encounter_view
    monkeypatch.setattr(card_board.CardBoardView, 'request_render', lambda self, card, side: None)
    view = encounter_view.EncounterView(encounter_project.get_encounter_set('set-1'), renderer=None)
    counts = {}
    for item in view.card_items:
        counts[item.card.id] = counts.get(item.card.id, 0) + 1
    assert counts == {'ghoul': 3, 'priest': 1, 'rats': 3, 'grasp': 2, 'fog': 1}
    ghouls = [i for i in view.card_items if i.card.id == 'ghoul']
    step = ghouls[1].x() - ghouls[0].x()
    assert step == pytest.approx(ghouls[0].width * 0.15)
    assert len({i.y() for i in ghouls}) == 1
    view.stop()
    view.deleteLater()


@pytest.mark.parametrize('mode', ['tree', 'folders'])
def test_clicking_encounter_group_opens_encounter_view(encounter_project, mode):
    from shoggoth.ui.browser.file_browser import FileBrowser
    fb = FileBrowser()
    fb.add_project(encounter_project)
    fb.switch_view(mode)
    opened = []
    fb.encounter_cards_selected.connect(opened.append)
    item = next(i for i in fb._iterate_items(fb.tree.invisibleRootItem())
                if (i.data(0, 0x0100) or {}).get('group') == 'encounter')
    fb.on_item_clicked(item, 0)
    assert [s.id for s in opened] == ['set-1']
    fb.deleteLater()


def test_harm_types_need_a_number():
    from shoggoth.ui.encounter_view import harm_types
    assert harm_types('Take 2 damage and 1 horror.') == {'damage', 'horror'}
    assert harm_types('Heal all damage from the enemy with the most damage.') == set()
    assert harm_types('Deal 3 Damage to it.') == {'damage'}


def test_harm_choice_is_its_own_kind():
    from shoggoth.ui.encounter_view import harm_types
    assert harm_types('Take 1 damage or horror.') == {'either'}
    assert harm_types('take 1 damage or 1 horror') == {'either'}
    assert harm_types('Take 2 horror or damage.') == {'either'}
    assert harm_types('Take 1 damage or horror. Then take 2 horror.') == {'either', 'horror'}
    assert harm_types('Take 1 damage or discard a card.') == {'damage'}
