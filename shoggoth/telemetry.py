"""Opt-in usage-data collection.

Off by default; nothing is gathered or sent unless `SettingsManager`'s
`telemetry_level` setting is 'basic', 'extended', or 'personal' (see
settings.py's Privacy tab). Pure logic, no Qt dependency (mirrors
updater.py/cloud/client.py's style: sync `requests` calls dispatched on a
daemon thread) -- only shoggoth/ui/** code calls into this module; card.py/
project.py/renderer.py never do, matching the model-never-calls-UI rule in
CLAUDE.md. tool.py's -r/-d/--test paths never import this module either, so
headless/CLI runs never collect or send anything.

Every event is one small HTTP POST to `{publish_base_url}/telemetry/events`
(the same Library of Celaeno backend "Publishing" already talks to, see
CLOUD.md) sent from a background thread; every failure is swallowed --
telemetry must never surface an error, block the UI, or otherwise affect the
app.

Tiers (each a superset of the one below; see CLAUDE.md's write-up):
  basic    - UI language, OS, project language(s) open at startup.
  extended - + project/card counts & types, card/template-creation events,
             export-triggered events, session duration.
  personal - + the requester's IP (added server-side, never sent by us) and
             all randomization below turned off.

Randomization (skipped entirely at the 'personal' tier):
  - OS and UI language are each resolved ONCE per session (a 10% chance to
    substitute a random OS / default to English) and reused for every event
    in that session -- resolving them per-event would let repeated events in
    one session be averaged to recover the true value.
  - Every other numeric field is noised per-event: below 10, a 10% chance to
    nudge by +-1; 10 and above, always scaled by a random factor in
    [0.9, 1.1]. Categorical fields (card/export/template type, language
    codes) are never perturbed.
  - The whole session has a 10% chance, decided once at session start, of
    being flagged "not logged": when that happens NOTHING for that session
    is ever sent (not the startup event, not any event during the session,
    not its eventual duration). This -- not a numeric nudge -- is how "number
    of launches" gets its 10% margin: a numeric launch-count field would be
    meaningless noise, since the mere presence of a session_id anywhere in
    the data (an export event, a card-created event, ...) already proves a
    launch happened, letting that proof re-derive an "off" count. Dropping
    the entire session is the only way to actually make some launches not
    count. (Never happens at the 'personal' tier.)

Session duration, specifically, is never sent at shutdown -- `stop_session()`
only ever touches local disk, synchronously, so app close never blocks on
network I/O (and can't be lost to the process exiting before a background
send finishes). Instead, while an extended+/personal, logged session runs,
its elapsed time is heartbeat-written to a small local state file every 30s
(see `_STATE_FILE`); the *next* `start_session()` call -- next app boot, or
an in-process telemetry-level change -- reads and sends whatever session was
left behind (this process's own just-ended one, and/or a previous run's, if
the app crashed or was killed) as that session's 'shutdown' event, then
clears the file. A crash therefore still gets a duration, accurate to within
one heartbeat interval.
"""
from __future__ import annotations

import json
import logging
import platform
import random
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass

import requests

from shoggoth.files import root_dir
from shoggoth.i18n import get_current_language

logger = logging.getLogger(__name__)

_TIMEOUT = 5  # seconds -- telemetry must never noticeably block anything
_TIERS = ('basic', 'extended', 'personal')  # ordered; each a superset of the previous
_HEARTBEAT_SECONDS = 30
_STATE_FILE = root_dir / 'telemetry_session.json'  # local only -- never sent as-is


def _tier_at_least(tier: str, minimum: str) -> bool:
    return tier in _TIERS and _TIERS.index(tier) >= _TIERS.index(minimum)


@dataclass
class _Session:
    id: str
    tier: str
    base_url: str
    os: str
    ui_language: str
    start: float  # time.monotonic()
    logged: bool  # False for the ~10% of basic/extended sessions dropped entirely


_session: _Session | None = None
_lock = threading.Lock()
_heartbeat_stop: threading.Event | None = None
_heartbeat_thread: threading.Thread | None = None


def _real_os() -> str:
    system = platform.system().lower()
    if system == 'darwin':
        return 'mac'
    if system in ('windows', 'linux'):
        return system
    return system or 'unknown'


def _resolve_os(exact: bool) -> str:
    if not exact and random.random() < 0.10:
        return random.choices(('windows', 'mac', 'linux'), weights=(70, 25, 5))[0]
    return _real_os()


def _resolve_ui_language(exact: bool) -> str:
    if not exact and random.random() < 0.10:
        return 'en'
    return get_current_language()


def _noise_int(n: int, exact: bool) -> int:
    """The spec's numeric fuzz for one count/duration."""
    if exact:
        return n
    if n < 10:
        if random.random() < 0.10:
            n += random.choice((-1, 1))
    else:
        n = round(n * random.uniform(0.9, 1.1))
    return max(0, n)


def _noise_value(value, exact: bool):
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return _noise_int(value, exact)
    if isinstance(value, dict):
        return _noise_data(value, exact)
    if isinstance(value, list):
        return [_noise_value(v, exact) for v in value]
    return value  # strings (types/languages/kinds) are never perturbed


def _noise_data(data: dict, exact: bool) -> dict:
    return {key: _noise_value(value, exact) for key, value in data.items()}


def _post(base_url: str, payload: dict) -> None:
    try:
        requests.post(f"{base_url}/telemetry/events", json=payload, timeout=_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - telemetry must never raise
        logger.debug(f"Telemetry send failed (ignored): {exc}")


def _send(session: _Session, event_type: str, data: dict) -> None:
    if not session.logged:
        return
    exact = session.tier == 'personal'
    payload = {
        'session_id': session.id,
        'tier': session.tier,
        'event_type': event_type,
        'os': session.os,
        'ui_language': session.ui_language,
        'data': _noise_data(data, exact),
    }
    threading.Thread(target=_post, args=(session.base_url, payload), daemon=True).start()


# ── Local session-duration persistence ──────────────────────────────────
# Deliberately disk-only: never sent as-is, just how a session's elapsed time
# survives a crash/kill or an in-process level change to be reported as a
# 'shutdown' event the next time start_session() runs.

def _write_state(session: _Session, elapsed: float) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps({
            'session_id': session.id,
            'tier': session.tier,
            'base_url': session.base_url,
            'os': session.os,
            'ui_language': session.ui_language,
            'elapsed_seconds': elapsed,
        }))
    except OSError as exc:
        logger.debug(f"Telemetry state write failed (ignored): {exc}")


def _read_and_clear_state() -> dict | None:
    data = None
    try:
        if _STATE_FILE.exists():
            data = json.loads(_STATE_FILE.read_text())
    except (OSError, ValueError) as exc:
        logger.debug(f"Telemetry state read failed (ignored): {exc}")
    try:
        _STATE_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    return data


def _flush_pending_state() -> None:
    """Send whatever session (this process's own just-ended one, and/or a
    previous run's left behind by a crash) is on disk as its 'shutdown'
    event, then clear it. Only ever written for logged extended+/personal
    sessions (see _start_heartbeat), so anything found here is sent as-is."""
    data = _read_and_clear_state()
    if not data:
        return
    prev = _Session(
        id=data['session_id'], tier=data['tier'], base_url=data['base_url'],
        os=data['os'], ui_language=data['ui_language'], start=0.0, logged=True,
    )
    duration = round(data.get('elapsed_seconds', 0))
    _send(prev, 'shutdown', {'duration_seconds': duration})


def _heartbeat_loop(session: _Session, stop_event: threading.Event) -> None:
    while not stop_event.wait(_HEARTBEAT_SECONDS):
        _write_state(session, time.monotonic() - session.start)


def _start_heartbeat(session: _Session) -> None:
    global _heartbeat_stop, _heartbeat_thread
    _write_state(session, 0.0)  # record it immediately, in case of a near-instant crash
    _heartbeat_stop = threading.Event()
    _heartbeat_thread = threading.Thread(
        target=_heartbeat_loop, args=(session, _heartbeat_stop), daemon=True,
    )
    _heartbeat_thread.start()


def _stop_heartbeat() -> None:
    global _heartbeat_stop, _heartbeat_thread
    if _heartbeat_stop is not None:
        _heartbeat_stop.set()
    if _heartbeat_thread is not None:
        _heartbeat_thread.join(timeout=1)
    _heartbeat_stop, _heartbeat_thread = None, None


def _finalize(session: _Session | None) -> None:
    """Stop any running heartbeat and, for a logged extended+ session, write
    its final accurate elapsed time to disk (overwriting the last periodic
    heartbeat) so the next start_session() call flushes and sends it."""
    _stop_heartbeat()
    if session is not None and session.logged and _tier_at_least(session.tier, 'extended'):
        _write_state(session, time.monotonic() - session.start)


# ── Public API ───────────────────────────────────────────────────────────

def start_session(settings) -> None:
    """(Re)start the telemetry session from the current settings. Called at
    boot, and again whenever the Privacy tab's level changes, so a level
    change always starts a clean session (fresh GUID, freshly-resolved
    OS/UI-language, freshly-rolled "logged" chance) rather than mutating the
    old one -- reusing a session across a level change would let noise draws
    be compared across levels. Finalizes and flushes whatever session was
    previously running (this process's own, and/or a crashed previous run's)
    first. No-ops (clearing any previous session) when the level is 'off'."""
    global _session
    with _lock:
        old_session = _session
        _session = None
    _finalize(old_session)
    _flush_pending_state()

    tier = settings.get('Shoggoth', 'telemetry_level', 'off')
    with _lock:
        if tier not in _TIERS:
            return
        exact = tier == 'personal'
        logged = True if exact else random.random() >= 0.10
        new_session = _Session(
            id=uuid.uuid4().hex,
            tier=tier,
            base_url=settings.get('Shoggoth', 'publish_base_url', 'https://celaeno.cards'),
            os=_resolve_os(exact),
            ui_language=_resolve_ui_language(exact),
            start=time.monotonic(),
            logged=logged,
        )
        _session = new_session
        if logged and _tier_at_least(tier, 'extended'):
            _start_heartbeat(new_session)


def stop_session() -> None:
    """App shutdown: local-only and synchronous (no network call, so this can
    never block app close) -- writes the session's final elapsed time to disk
    so the *next* start_session() reports it as a 'shutdown' event. No-op if
    telemetry isn't running or the tier doesn't include a duration."""
    global _session
    with _lock:
        session = _session
        _session = None
    _finalize(session)


def record_startup(projects) -> None:
    """`projects` is the list of currently-open `Project` objects (e.g.
    `window.open_projects`). Basic tier reports only the distinct project
    languages; extended+ adds per-project card counts and type breakdowns."""
    session = _session
    if session is None:
        return
    languages = sorted({(p.language or 'en') for p in projects})
    data = {'project_languages': languages}
    if _tier_at_least(session.tier, 'extended'):
        summaries = []
        for p in projects:
            cards = list(p.get_all_cards())
            type_counts = Counter(c.front.get('type') or 'unknown' for c in cards)
            summaries.append({'card_count': len(cards), 'type_counts': dict(type_counts)})
        data['project_count'] = len(projects)
        data['projects'] = summaries
    _send(session, 'startup', data)


def record_card_created(card_type: str) -> None:
    """Extended+ only -- basic tier doesn't include per-card events."""
    session = _session
    if session is None or not _tier_at_least(session.tier, 'extended'):
        return
    _send(session, 'card_created', {'card_type': card_type})


def record_template_created(template_kind: str) -> None:
    """`template_kind` is e.g. 'scenario'/'campaign'/'investigator'/
    'investigator_project' (Project menu template actions)."""
    session = _session
    if session is None or not _tier_at_least(session.tier, 'extended'):
        return
    _send(session, 'template_created', {'template_kind': template_kind})


def record_export(export_kinds) -> None:
    """`export_kinds` is the set/iterable of export kinds enabled for this
    run, e.g. {'images', 'pdf', 'tts', 'data', 'guides'}."""
    session = _session
    if session is None or not _tier_at_least(session.tier, 'extended'):
        return
    _send(session, 'export', {'kinds': sorted(export_kinds)})
