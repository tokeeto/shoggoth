"""Shared fixtures for the fast test suite.

Nothing here needs the asset pack, a network connection or a display: the
defaults files a test relies on are written by the test itself (see the
`defaults` fixture), so results don't change when the asset pack does.
Rendering against the real asset pack is the visual check's job
(scripts/visual_check.py).
"""
import json
import os

import pytest

# Never open windows, even if a test imports Qt modules.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import shoggoth.card  # noqa: E402
from shoggoth.project import Project  # noqa: E402


def card_data(card_id, name='Card', front=None, back=None, **extra):
    """A minimal stored card."""
    return {
        'id': card_id,
        'name': name,
        'front': front if front is not None else {'type': 'asset'},
        'back': back if back is not None else {'type': 'player'},
        **extra,
    }


def project_data(cards=(), encounter_sets=(), **extra):
    """A minimal stored project."""
    return {
        'name': 'Test Project',
        'id': 'project-id',
        'cards': list(cards),
        'encounter_sets': list(encounter_sets),
        **extra,
    }


@pytest.fixture
def write_project(tmp_path):
    """write_project(data, name='project.shoggoth') -> path of the written file."""
    def write(data, name='project.shoggoth'):
        path = tmp_path / name
        path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding='utf-8')
        return path
    return write


@pytest.fixture
def load_project(write_project):
    """load_project(data) -> Project loaded from a freshly written file."""
    def load(data, name='project.shoggoth'):
        return Project.load(write_project(data, name))
    return load


@pytest.fixture
def defaults(tmp_path, monkeypatch):
    """defaults(name, content): writes a defaults file that faces of type
    `name` resolve against, instead of the asset pack's."""
    folder = tmp_path / 'defaults'
    folder.mkdir()
    monkeypatch.setattr(shoggoth.card, 'defaults_dir', folder)

    def write(name, content):
        (folder / f'{name}.json').write_text(json.dumps(content), encoding='utf-8')
    return write


def pytest_configure(config):
    config.addinivalue_line('markers', 'assets: needs the installed asset pack (fonts, templates, ...)')


def pytest_collection_modifyitems(config, items):
    """Tests marked `assets` skip when the asset pack isn't installed (as in
    CI) -- unless SHOGGOTH_REQUIRE_ASSETS is set (scripts/release.py sets it),
    which turns that skip into a failure."""
    from shoggoth.files import font_dir
    if font_dir.is_dir() and any(font_dir.iterdir()):
        return
    if os.environ.get('SHOGGOTH_REQUIRE_ASSETS'):
        raise pytest.UsageError(f'SHOGGOTH_REQUIRE_ASSETS is set, but there is no asset pack at {font_dir.parent}')
    skip = pytest.mark.skip(reason='asset pack not installed')
    for item in items:
        if 'assets' in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _no_leaked_listeners():
    """Project change listeners are class-level: keep tests from leaking them."""
    listeners = list(Project._change_listeners)
    yield
    Project._change_listeners[:] = listeners
