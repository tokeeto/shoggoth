"""Per-element three-way-ish merge between a local project and the cloud copy.

Pure logic, no Qt, no I/O -- everything the sync controller decides about
*what* to take, keep, push or ask about lives here so it can be exercised
without a window or a server.

The unit of merging is an **element**: a card, an encounter set, a guide, or
the project's own top-level fields ("project"). Each carries a `meta.modified`
epoch timestamp, stamped by `Project.stamp()` whenever it's edited. Sync
remembers `synced_at`: the local wall-clock time of the last moment local and
cloud were known to agree. Comparing an element's timestamp to that marker
tells us which side changed *since then*:

    local changed  = local.modified  > synced_at
    remote changed = remote.modified > synced_at

    neither changed, contents differ -> take the cloud's (server is truth)
    only remote changed              -> take remote
    only local changed               -> push local
    both changed, contents differ    -> conflict: ask the user

Missing timestamps count as 0 (older than any sync). Timestamps from two
machines' clocks are compared against `synced_at` only, never against each
other, so a little clock skew between collaborators is tolerated.

Wire format: the cloud stores `cards`, `encounter_sets` and `guides` as dicts
keyed by element id (so a PATCH can name single elements); a local project
file keeps them as lists. `to_wire`/`from_wire` convert.
"""
import copy
from dataclasses import dataclass, field

ELEMENT_KINDS = ('cards', 'encounter_sets', 'guides')
# meta keys that only make sense on this machine and never travel
# top-level keys that only make sense on this machine
LOCAL_KEYS = ('id', 'translations')
LOCAL_META = ('dirty', 'celaeno_id', 'celaeno_version', 'celaeno_synced_at', 'celaeno_deleted', 'celaeno_role')


def modified(element) -> float:
    if not element:
        return 0.0
    return element.get('meta', {}).get('modified', 0) or 0


def _content(element):
    """An element minus its own edit timestamp, for "did the content
    actually differ" checks."""
    if element is None:
        return None
    stripped = copy.copy(element)
    meta = dict(stripped.get('meta', {}))
    meta.pop('modified', None)
    if meta:
        stripped['meta'] = meta
    else:
        stripped.pop('meta', None)
    return stripped


def same_content(a, b) -> bool:
    return _content(a) == _content(b)


def element_name(element) -> str:
    if not element:
        return ''
    return element.get('name') or element.get('id') or ''


# --- wire conversion --------------------------------------------------------

def project_fields(data: dict) -> dict:
    """The project's own fields: everything except the element lists, the
    project's local identity (id) and its local-file-relative translations
    map, and minus the meta keys that are local-only."""
    fields = {k: copy.deepcopy(v) for k, v in data.items()
              if k not in ELEMENT_KINDS and k not in LOCAL_KEYS}
    meta = {k: v for k, v in fields.get('meta', {}).items() if k not in LOCAL_META}
    if meta:
        fields['meta'] = meta
    else:
        fields.pop('meta', None)
    return fields


def to_wire(data: dict) -> dict:
    wire = project_fields(data)
    for kind in ELEMENT_KINDS:
        wire[kind] = {e['id']: e for e in data.get(kind, []) if e.get('id')}
    return wire


def from_wire(wire: dict) -> dict:
    data = {k: v for k, v in wire.items() if k not in ELEMENT_KINDS}
    for kind in ELEMENT_KINDS:
        data[kind] = list(wire.get(kind, {}).values())
    return data


# --- planning ---------------------------------------------------------------

@dataclass
class Conflict:
    kind: str                 # 'cards' | 'encounter_sets' | 'guides' | 'project'
    element_id: str
    local: dict | None        # None: deleted locally
    remote: dict | None       # None: deleted in the cloud


@dataclass
class Plan:
    # (kind, id, remote element) to add/replace locally
    take: list = field(default_factory=list)
    # (kind, id) to delete locally
    remove: list = field(default_factory=list)
    # kind -> {id: element, or None to delete} to send to the cloud
    push: dict = field(default_factory=dict)
    conflicts: list = field(default_factory=list)
    # the project's own fields: take the cloud's / send ours
    take_project: dict | None = None
    push_project: dict | None = None

    def push_element(self, kind, element_id, element):
        self.push.setdefault(kind, {})[element_id] = element

    @property
    def empty(self) -> bool:
        return not (self.take or self.remove or self.push or self.conflicts
                    or self.take_project or self.push_project)


def _decide(local, remote, synced_at, tombstone, remote_deleted=False):
    """Returns one of 'none' | 'take' | 'remove' | 'push' | 'push_delete' |
    'conflict' for one element. `local`/`remote` are element dicts or None."""
    local_t, remote_t = modified(local), modified(remote)
    local_changed = local_t > synced_at
    remote_changed = remote_t > synced_at

    if remote is not None and local is not None:
        if same_content(local, remote):
            return 'none'
        if local_changed and remote_changed:
            return 'conflict'
        if local_changed:
            return 'push'
        return 'take'  # remote changed, or neither did (server is truth)

    if remote is not None:  # absent locally
        if tombstone:
            return 'conflict' if remote_changed else 'push_delete'
        return 'take'

    if local is not None:  # absent remotely
        if remote_deleted:  # an explicit deletion (live patch), not just a missing key
            return 'conflict' if local_changed else 'remove'
        return 'push' if local_changed else 'remove'

    return 'none'


def _plan_element(plan, kind, element_id, local, remote, synced_at, tombstone, remote_deleted=False):
    decision = _decide(local, remote, synced_at, tombstone, remote_deleted)
    if decision == 'take':
        plan.take.append((kind, element_id, remote))
    elif decision == 'remove':
        plan.remove.append((kind, element_id))
    elif decision == 'push':
        plan.push_element(kind, element_id, local)
    elif decision == 'push_delete':
        plan.push_element(kind, element_id, None)
    elif decision == 'conflict':
        plan.conflicts.append(Conflict(kind, element_id, local, remote))


def _plan_project(plan, local_data, remote_fields, synced_at):
    local_fields = project_fields(local_data)
    if same_content(local_fields, remote_fields):
        return
    local_changed = modified(local_fields) > synced_at
    remote_changed = modified(remote_fields) > synced_at
    if local_changed and remote_changed:
        plan.conflicts.append(Conflict('project', local_data.get('id', ''), local_fields, remote_fields))
    elif local_changed:
        plan.push_project = local_fields
    else:
        plan.take_project = remote_fields


def _local_index(local_data, kind):
    return {e['id']: e for e in local_data.get(kind, []) if e.get('id')}


def plan_snapshot(local_data: dict, remote_wire: dict, synced_at: float, deleted: dict) -> Plan:
    """Plan for a whole cloud snapshot: elements absent on one side are
    treated as deleted there (or new here) per the rules above. `deleted` is
    the local tombstone dict {id: {'kind', 'at'}}."""
    plan = Plan()
    for kind in ELEMENT_KINDS:
        local, remote = _local_index(local_data, kind), remote_wire.get(kind, {})
        for element_id in list(dict.fromkeys([*local, *remote])):
            _plan_element(plan, kind, element_id, local.get(element_id), remote.get(element_id),
                          synced_at, element_id in deleted)
    _plan_project(plan, local_data, project_fields(from_wire(remote_wire)), synced_at)
    return plan


def plan_patch(local_data: dict, patch: dict, synced_at: float, deleted: dict) -> Plan:
    """Plan for one live patch: only the elements the patch names are
    considered, and a null value means "deleted in the cloud" explicitly
    (rather than merely absent from a snapshot)."""
    plan = Plan()
    for kind in ELEMENT_KINDS:
        local = _local_index(local_data, kind)
        for element_id, remote in (patch.get(kind) or {}).items():
            _plan_element(plan, kind, element_id, local.get(element_id), remote,
                          synced_at, element_id in deleted, remote_deleted=remote is None)
    remote_fields = {k: v for k, v in patch.items() if k not in ELEMENT_KINDS}
    if remote_fields:
        merged_remote = {**project_fields(local_data), **remote_fields}
        _plan_project(plan, local_data, merged_remote, synced_at)
    return plan


# --- applying ---------------------------------------------------------------

def apply_take(data: dict, kind: str, element_id: str, element: dict) -> None:
    """Adds or replaces an element in a local project's data (in place --
    replacing the dict's contents so anything holding a reference to it, like
    an open Card wrapper, sees the update)."""
    elements = data.setdefault(kind, [])
    for existing in elements:
        if existing.get('id') == element_id:
            existing.clear()
            existing.update(copy.deepcopy(element))
            return
    elements.append(copy.deepcopy(element))


def apply_remove(data: dict, kind: str, element_id: str) -> None:
    data[kind] = [e for e in data.get(kind, []) if e.get('id') != element_id]


def apply_project_fields(data: dict, fields: dict) -> None:
    """Replaces the project's own fields with the cloud's, leaving the
    element lists and this machine's local-only meta keys alone."""
    keep_meta = {k: v for k, v in data.get('meta', {}).items() if k in LOCAL_META}
    for key in [k for k in data if k not in ELEMENT_KINDS and k not in LOCAL_KEYS]:
        del data[key]
    data.update(copy.deepcopy(fields))
    if keep_meta or 'meta' in data:
        data.setdefault('meta', {}).update(keep_meta)
