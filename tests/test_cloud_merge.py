"""The cloud merge decision table (shoggoth/cloud/merge.py)."""
import pytest

from shoggoth.cloud.merge import from_wire, local_changes, plan_patch, plan_snapshot, to_wire

SYNCED_AT = 100.0
OLD, NEW = 50.0, 200.0


def card(card_id, name, modified):
    return {'id': card_id, 'name': name, 'meta': {'modified': modified}}


def local_project(*cards, **extra):
    return {'id': 'p', 'name': 'P', 'cards': list(cards), 'encounter_sets': [], 'guides': [], **extra}


def remote_wire(*cards, **extra):
    return to_wire(local_project(*cards, **extra))


def decisions(plan):
    """{element id: decision} from a plan, for compact assertions."""
    result = {}
    for _kind, element_id, _ in plan.take:
        result[element_id] = 'take'
    for _kind, element_id in plan.remove:
        result[element_id] = 'remove'
    for _kind, elements in plan.push.items():
        for element_id, element in elements.items():
            result[element_id] = 'push_delete' if element is None else 'push'
    for conflict in plan.conflicts:
        result[conflict.element_id] = 'conflict'
    return result


@pytest.mark.parametrize('local_t, remote_t, expected', [
    (OLD, OLD, 'take'),      # neither changed, contents differ: the server is truth
    (OLD, NEW, 'take'),
    (NEW, OLD, 'push'),
    (NEW, NEW, 'conflict'),
])
def test_both_sides_have_element(local_t, remote_t, expected):
    plan = plan_snapshot(local_project(card('c', 'local', local_t)), remote_wire(card('c', 'remote', remote_t)), SYNCED_AT, {})
    assert decisions(plan) == {'c': expected}


def test_same_content_is_nothing_to_do():
    plan = plan_snapshot(local_project(card('c', 'same', NEW)), remote_wire(card('c', 'same', OLD)), SYNCED_AT, {})
    assert plan.empty


def test_new_remote_element_is_taken():
    plan = plan_snapshot(local_project(), remote_wire(card('c', 'x', OLD)), SYNCED_AT, {})
    assert decisions(plan) == {'c': 'take'}


def test_locally_deleted_element():
    deleted = {'c': {'kind': 'cards', 'at': NEW}}
    unchanged_remote = plan_snapshot(local_project(), remote_wire(card('c', 'x', OLD)), SYNCED_AT, deleted)
    assert decisions(unchanged_remote) == {'c': 'push_delete'}
    changed_remote = plan_snapshot(local_project(), remote_wire(card('c', 'x', NEW)), SYNCED_AT, deleted)
    assert decisions(changed_remote) == {'c': 'conflict'}


def test_element_missing_remotely():
    new_local = plan_snapshot(local_project(card('c', 'x', NEW)), remote_wire(), SYNCED_AT, {})
    assert decisions(new_local) == {'c': 'push'}
    old_local = plan_snapshot(local_project(card('c', 'x', OLD)), remote_wire(), SYNCED_AT, {})
    assert decisions(old_local) == {'c': 'remove'}
    kept = plan_snapshot(local_project(card('c', 'x', OLD)), remote_wire(), SYNCED_AT, {}, prefer_local=True)
    assert decisions(kept) == {'c': 'push'}


def test_patch_with_explicit_deletion():
    edited = plan_patch(local_project(card('c', 'x', NEW)), {'cards': {'c': None}}, SYNCED_AT, {})
    assert decisions(edited) == {'c': 'conflict'}
    untouched = plan_patch(local_project(card('c', 'x', OLD)), {'cards': {'c': None}}, SYNCED_AT, {})
    assert decisions(untouched) == {'c': 'remove'}


def test_patch_only_considers_named_elements():
    plan = plan_patch(local_project(card('a', 'x', NEW), card('b', 'y', OLD)), {'cards': {'b': card('b', 'z', NEW)}}, SYNCED_AT, {})
    assert decisions(plan) == {'b': 'take'}


def test_project_fields_merge():
    local = local_project(meta={'modified': NEW, 'dirty': ['x'], 'celaeno_id': 'local only'}, name='Local')
    remote = remote_wire(meta={'modified': OLD}, name='Remote')
    plan = plan_snapshot(local, remote, SYNCED_AT, {})
    assert plan.push_project['name'] == 'Local'
    assert 'dirty' not in plan.push_project['meta']
    assert 'celaeno_id' not in plan.push_project['meta']


def test_wire_roundtrip():
    data = local_project(card('a', 'x', OLD), card('b', 'y', NEW))
    wire = to_wire(data)
    assert set(wire['cards']) == {'a', 'b'}
    assert 'id' not in wire
    back = from_wire(wire)
    assert back['cards'] == data['cards']


def test_local_changes():
    data = local_project(card('a', 'x', OLD), card('b', 'y', NEW))
    deleted = {'gone': {'kind': 'cards', 'at': NEW}}
    assert local_changes(data, SYNCED_AT, deleted) == {('cards', 'b'), ('cards', 'gone')}
