"""Shared fixtures for the test suite.

Most tests need no asset pack, network connection or display: the defaults
files a test relies on are written by the test itself (see the `defaults`
fixture), so results don't change when the asset pack does. Those are what the
build on GitHub runs.

Tests marked `assets` run against the SHOGGOTH_ASSET_DIR folder (usually set in
.env), never the installed pack, and skip when it isn't set. Rendering against
the real asset pack is the visual check's job (scripts/visual_check.py).
"""
import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Never open windows, even if a test imports Qt modules.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# Both before anything imports shoggoth.files, which reads the variable once.
load_dotenv(Path(__file__).parent.parent / '.env')
if not os.environ.get('SHOGGOTH_ASSET_DIR'):
    # A folder that doesn't exist, so the installed pack is never picked up.
    os.environ['SHOGGOTH_ASSET_DIR'] = str(Path(__file__).parent / 'no_asset_pack')

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
    config.addinivalue_line('markers', 'assets: needs the asset pack in SHOGGOTH_ASSET_DIR (fonts, templates, ...)')


def pytest_collection_modifyitems(config, items):
    """Tests marked `assets` skip without an asset pack in SHOGGOTH_ASSET_DIR
    (as in CI) -- unless SHOGGOTH_REQUIRE_ASSETS is set (the release scripts
    set it), which turns that skip into a failure."""
    from shoggoth.files import font_dir
    if font_dir.is_dir() and any(font_dir.iterdir()):
        return
    if os.environ.get('SHOGGOTH_REQUIRE_ASSETS'):
        raise pytest.UsageError(f'SHOGGOTH_REQUIRE_ASSETS is set, but there is no asset pack at {font_dir.parent}: set SHOGGOTH_ASSET_DIR in .env')
    skip = pytest.mark.skip(reason='no asset pack in SHOGGOTH_ASSET_DIR')
    for item in items:
        if 'assets' in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _no_leaked_listeners():
    """Project change listeners are class-level: keep tests from leaking them."""
    listeners = list(Project._change_listeners)
    yield
    Project._change_listeners[:] = listeners
