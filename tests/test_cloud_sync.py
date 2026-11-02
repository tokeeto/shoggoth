"""CloudSyncController merging a pulled snapshot into a project whose file
was changed without new timestamps (edited by hand while Shoggoth was
closed). Network and dialogs are stubbed; only the main-thread merge runs."""
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from shoggoth.cloud import folder, merge, sync
from shoggoth.project import Project

OLD = 50.0
SYNCED_AT = 100.0


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


def project_data(guide_text):
    return {
        'id': 'p', 'name': 'P', 'cards': [], 'encounter_sets': [],
        'guides': [{'id': 'g', 'name': 'Guide', 'meta': {'modified': OLD},
                    'sections': [{'id': 's', 'type': 'blank', 'name': 'S', 'markdown': guide_text}]}],
        'meta': {'celaeno_id': 'cloud', 'celaeno_version': 3, 'celaeno_synced_at': SYNCED_AT,
                 'modified': OLD},
    }


@pytest.fixture
def controller(qapp, tmp_path, monkeypatch):
    window = SimpleNamespace(
        config=SimpleNamespace(get=lambda *a: 'x'),
        status_bar=SimpleNamespace(showMessage=lambda *a: None),
        active_project=None,
    )
    ctrl = sync.CloudSyncController.__new__(sync.CloudSyncController)
    sync.QObject.__init__(ctrl)
    ctrl.window = window
    ctrl._sessions = {}
    asked = []
    monkeypatch.setattr(ctrl, '_ask_conflicts', lambda conflicts: asked.append(conflicts) or True)
    monkeypatch.setattr(ctrl, '_flush_push', lambda session, wait=False: None)
    ctrl.asked = asked
    return ctrl


def attach(ctrl, tmp_path, data, base=None):
    if base is not None:
        folder.write_base(tmp_path, base)
    project = Project(str(tmp_path / 'project.shoggoth'), data)
    session = sync._Session(project, 'cloud')
    session.save_timer = SimpleNamespace(start=lambda *a: None)
    ctrl._sessions['cloud'] = session
    return session


def markdown(project):
    return project.data['guides'][0]['sections'][0]['markdown']


def test_hand_edit_survives_snapshot_and_is_pushed(controller, tmp_path):
    cloud = merge.to_wire(project_data('cloud text'))
    session = attach(controller, tmp_path, project_data('edited by hand'), base=merge.wire_base(cloud))
    controller._apply_snapshot('cloud', {'data': cloud, 'version': 4}, 200.0)
    assert markdown(session.project) == 'edited by hand'
    assert ('guides', 'g') in session.pending
    assert not controller.asked
    # stamped on the way out, so collaborators see it as the newer copy
    session.sent_prints = {}
    controller._build_patch(session, session.pending)
    assert merge.modified(session.project.data['guides'][0]) > SYNCED_AT


def test_hand_edit_without_base_is_asked_about(controller, tmp_path):
    cloud = merge.to_wire(project_data('cloud text'))
    session = attach(controller, tmp_path, project_data('edited by hand'))
    controller._apply_snapshot('cloud', {'data': cloud, 'version': 4}, 200.0)
    assert controller.asked  # never silently replaced
    assert markdown(session.project) == 'edited by hand'  # kept: the stub keeps mine


def test_snapshot_records_base(controller, tmp_path):
    cloud = merge.to_wire(project_data('cloud text'))
    session = attach(controller, tmp_path, project_data('cloud text'))
    controller._apply_snapshot('cloud', {'data': cloud, 'version': 4}, 200.0)
    assert folder.read_base(tmp_path) == merge.wire_base(cloud) == session.base


def test_hand_edit_found_when_cloud_has_nothing_new(controller, tmp_path):
    cloud = merge.to_wire(project_data('cloud text'))
    session = attach(controller, tmp_path, project_data('edited by hand'), base=merge.wire_base(cloud))
    controller._apply_snapshot('cloud', None, 200.0)  # 304
    assert ('guides', 'g') in session.pending


def test_push_success_updates_base(controller, tmp_path):
    cloud = merge.to_wire(project_data('cloud text'))
    session = attach(controller, tmp_path, project_data('edited by hand'), base=merge.wire_base(cloud))
    session.push_timer = SimpleNamespace(start=lambda *a: None)
    keys = {('guides', 'g')}
    controller._build_patch(session, keys)
    controller._on_push_finished('cloud', True, 300.0, keys, 4)
    assert session.base['guides/g'] == merge.fingerprint(session.project.data['guides'][0])


def test_guide_with_missing_file_is_restored_from_the_cloud(controller, tmp_path):
    """Never pushed as empty: taken from the cloud, its file written on save."""
    cloud_data = project_data('cloud text')
    cloud_data['guides'][0]['file'] = 'guides/g.guide.md'
    cloud = merge.to_wire(cloud_data)
    local = project_data('')
    local['guides'] = [{'id': 'g', 'file': 'guides/g.guide.md', 'meta': {'modified': OLD}}]
    session = attach(controller, tmp_path, local, base=merge.wire_base(cloud))
    assert 'g' in session.project.missing_guide_files
    controller._apply_snapshot('cloud', {'data': cloud, 'version': 4}, 200.0)
    assert ('guides', 'g') not in session.pending
    assert markdown(session.project) == 'cloud text'
    session.project.save_all()
    assert 'cloud text' in (tmp_path / 'guides' / 'g.guide.md').read_text(encoding='utf-8')


def test_hand_edited_guide_file_is_pushed(controller, tmp_path):
    """The guide file edited while Shoggoth was closed: the project file
    didn't change, but the content read from the guide file differs from
    the base."""
    data = project_data('cloud text')
    data['guides'][0]['file'] = 'g.guide.md'
    cloud = merge.to_wire(data)
    from shoggoth import guide_file
    entry = dict(data['guides'][0], sections=[{'type': 'blank', 'name': 'S', 'markdown': 'edited by hand'}])
    (tmp_path / 'g.guide.md').write_text(guide_file.serialize(entry), encoding='utf-8')
    local = project_data('')
    local['guides'] = [{'id': 'g', 'file': 'g.guide.md', 'meta': {'modified': OLD}}]
    session = attach(controller, tmp_path, local, base=merge.wire_base(cloud))
    controller._apply_snapshot('cloud', None, 200.0)  # 304
    assert ('guides', 'g') in session.pending
    patch = controller._build_patch(session, session.pending)
    assert patch['guides']['g']['sections'][0]['markdown'] == 'edited by hand'
    assert patch['guides']['g']['file'] == 'g.guide.md'
