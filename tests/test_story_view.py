"""The Story group of an encounter set opens the story view: agendas and acts
(both sides) in their own columns, every other story card in a third."""
import pytest

from tests.conftest import card_data, project_data

QtWidgets = pytest.importorskip('PySide6.QtWidgets')


@pytest.fixture
def story_project(load_project, defaults):
    for name, card_type in (('agenda', 'agenda'), ('act', 'act'), ('story', 'story'),
                            ('location', 'location'), ('treachery', 'treachery')):
        defaults(name, {'card_type': card_type})
        defaults(f'{name}_back', {'card_type': card_type})
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def card(card_id, type):
        return card_data(card_id, card_id.title(), front={'type': type}, back={'type': f'{type}_back'},
                         encounter_set='set-1')
    return load_project(project_data(
        encounter_sets=[{'id': 'set-1', 'name': 'The Gathering', 'icon': ''}],
        cards=[card('agenda1', 'agenda'), card('act1', 'act'), card('act2', 'act'),
               card('interlude', 'story'), card('study', 'location'), card('rats', 'treachery')],
    ))


def test_story_cards_split_into_columns(story_project):
    from shoggoth.ui.story_view import split_story_cards, story_cards
    encounter_set = story_project.get_encounter_set('set-1')
    agendas, acts, others = split_story_cards(story_cards(encounter_set))
    assert [c.id for c in agendas] == ['agenda1']
    assert sorted(c.id for c in acts) == ['act1', 'act2']
    assert [c.id for c in others] == ['interlude']


@pytest.mark.parametrize('mode', ['tree', 'folders'])
def test_clicking_story_group_opens_story_view(story_project, mode):
    from shoggoth.ui.browser.file_browser import FileBrowser
    fb = FileBrowser()
    fb.add_project(story_project)
    fb.switch_view(mode)
    opened = []
    fb.story_selected.connect(opened.append)

    item = next(i for i in fb._iterate_items(fb.tree.invisibleRootItem())
                if (i.data(0, 0x0100) or {}).get('group') == 'story')
    fb.on_item_clicked(item, 0)
    assert [s.id for s in opened] == ['set-1']
    fb.deleteLater()


def test_story_view_lays_out_sides(story_project, monkeypatch):
    from shoggoth.ui import card_board, story_view
    monkeypatch.setattr(card_board.CardBoardView, 'request_render', lambda self, card, side: None)
    view = story_view.StoryView(story_project.get_encounter_set('set-1'), renderer=None)
    items = view.card_items
    # agenda + 2 acts with both sides, the story card front only
    assert sorted((i.card.id, i.side) for i in items) == [
        ('act1', 'back'), ('act1', 'front'), ('act2', 'back'), ('act2', 'front'),
        ('agenda1', 'back'), ('agenda1', 'front'), ('interlude', 'front'),
    ]
    assert [i.card.id for i in view.flippable_items] == ['interlude']
    view.stop()
    view.deleteLater()


def test_threshold_total_splits_plain_and_per():
    from shoggoth.ui.story_view import threshold_total

    class C:
        def __init__(self, value):
            self.front = {'doom': value}
    cards = [C('4'), C('2<per>'), C('<dash>'), C(None), C('X'), C(3)]
    assert threshold_total(cards, 'doom') == (7, 2)


@pytest.mark.parametrize('n, x, rating', [
    (15, 0, 'ok'), (3, 4, 'ok'), (16, 0, 'warn'), (18, 0, 'warn'), (0, 6, 'warn'),
    (14, 0, 'bad'), (19, 0, 'bad'), (0, 0, 'bad'),
])
def test_doom_rating(n, x, rating):
    from shoggoth.ui.story_view import doom_rating
    assert doom_rating(n, x) == rating


@pytest.mark.parametrize('clues, rating', [
    ((0, 9), 'ok'), ((6, 7), 'ok'), ((0, 11), 'ok'), ((0, 12), 'warn'), ((0, 15), 'warn'),
    ((0, 16), 'bad'), ((0, 8), 'bad'), ((3, 8), 'ok'),
])
def test_clue_rating_against_15_doom(clues, rating):
    from shoggoth.ui.story_view import clue_rating
    assert clue_rating(*clues, 15, 0) == rating
    assert clue_rating(0, 9, 0, 0) is None


def test_threshold_text():
    from shoggoth.ui import story_view
    html = story_view.threshold_html
    assert html(15, 0, 'doom') == '15 doom'
    assert html(0, 0, 'doom') == '0 doom'
    assert html(0, 9, 'clues').startswith('9') and html(0, 9, 'clues').endswith(' clues')
    assert html(6, 7, 'clues').startswith('6 + 7')


def _indexed(*indexes):
    class Face:
        def __init__(self, index):
            self.data = {'index': index} if index is not None else {}

    class C:
        def __init__(self, index):
            self.id = index
            self.front = Face(index)
    return [C(i) for i in indexes]


def test_index_rows_put_same_number_side_by_side():
    from shoggoth.ui.story_view import index_rows
    rows = index_rows(_indexed('4a', '3e', '1a', '3a', '2a', '3d'))
    assert [[c.id for c in row] for row in rows] == [['1a'], ['2a'], ['3a', '3d', '3e'], ['4a']]

    rows = index_rows(_indexed('2c', '1a', '1d', '1c', '2a', '10a', None, '2d'))
    assert [[c.id for c in row] for row in rows] == [
        ['1a', '1c', '1d'], ['2a', '2c', '2d'], ['10a'], [None]]


def test_unnumbered_cards_get_a_row_each():
    from shoggoth.ui.story_view import index_rows
    assert [len(row) for row in index_rows(_indexed(None, None, ''))] == [1, 1, 1]
