"""The project tree keeps the current card through refreshes: re-sorting or
moving a card's node must never select (and so open) another card."""
import pytest

from tests.conftest import card_data, project_data

QtWidgets = pytest.importorskip('PySide6.QtWidgets')


@pytest.fixture
def browser(load_project, defaults):
    defaults('asset', {'card_type': 'asset'})
    defaults('player', {})
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from shoggoth.ui.browser.file_browser import FileBrowser

    project = load_project(project_data(cards=[
        card_data(f'card-{name.lower()}', name, front={'type': 'asset', 'classes': ['guardian']})
        for name in ('Alpha', 'Beta', 'Gamma')
    ]))
    fb = FileBrowser()
    fb.add_project(project)
    opened = []
    fb.card_selected.connect(opened.append)
    yield fb, project, opened
    fb.deleteLater()
    app.processEvents()


def current_card_id(widget):
    data = widget.currentItem().data(0, 0x0100)  # Qt.UserRole
    return data['data'].id


@pytest.mark.parametrize('mode', ['tree', 'folders', 'list'])
def test_rename_and_refresh_keeps_current_card(browser, mode):
    fb, project, opened = browser
    fb.switch_view(mode)
    widget = fb.list_tree if mode == 'list' else fb.tree
    assert fb.select_item_in_tree('card-beta') or mode == 'list'
    if mode == 'list':
        item = next(i for i in fb._iterate_items(widget.invisibleRootItem())
                    if (i.data(0, 0x0100) or {}).get('node_id') == 'card:card-beta')
        widget.setCurrentItem(item)
        opened.clear()

    beta = project.get_card('card-beta')
    beta.set('name', 'Zeta')  # now sorts last
    fb.refresh()
    assert current_card_id(widget) == 'card-beta'

    beta.front.set('classes', ['seeker'])  # now in another group
    fb.refresh()
    assert current_card_id(widget) == 'card-beta'
    assert widget.currentItem().isSelected()
    assert opened == []
