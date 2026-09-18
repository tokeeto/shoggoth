"""Live sync for cloud storage projects: a persistent WebSocket connection
per open cloud-backed `Project`, plus a debounced push of local edits back
to the server. See CLOUD.md for the full desktop<->backend contract and
`shoggoth_web`'s app/storage_projects.py for the server side.

Modeled on `ui.main_window.preview.PreviewController`'s Signal-from-thread
pattern for the receive side (a `Signal` emitted from a background thread;
Qt auto-queues delivery onto the main thread since the receiving `QObject`
lives there) -- but unlike that controller's one-shot-per-render threads,
each websocket connection here is long-lived, so this owns an explicit
start/stop lifecycle per project (no existing precedent for that in this
codebase).

Wire format: a project's whole JSON blob is stored server-side with `cards`
as a dict keyed by card id (see shoggoth_web's StorageProject.data_json /
apply_patch), whereas a local `.shoggoth` file's `data['cards']` is a *list*
(see project.py/card.py) -- `project_data_to_wire`/`project_data_from_wire`
below are the one place that conversion happens, so every other piece of
this module (and Project.apply_remote_patch) can stay agnostic to it.
"""
import json
import threading

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QMessageBox

from shoggoth.cloud import client, storage_cache
from shoggoth.i18n import tr

_PUSH_DEBOUNCE_MS = 1500


def _cards_to_wire(cards_list):
    return {c['id']: c for c in cards_list if 'id' in c}


def _cards_from_wire(cards_dict):
    return list(cards_dict.values())


def project_data_to_wire(data: dict) -> dict:
    """A local Project.data dict -> the shape a storage project's blob is
    stored/sent as (cards keyed by id, everything else untouched)."""
    wire = dict(data)
    wire['cards'] = _cards_to_wire(data.get('cards', []))
    return wire


def project_data_from_wire(wire: dict) -> dict:
    """Inverse of project_data_to_wire -- used when downloading/opening a
    storage project into a local .shoggoth file."""
    data = dict(wire)
    data['cards'] = _cards_from_wire(wire.get('cards', {}))
    return data


def _storage_project_id(project) -> str | None:
    location = project.get_meta('cloud_storage_location')
    if not location or not location.startswith('cloud://'):
        return None
    return location[len('cloud://'):]


class CloudSyncController(QObject):
    # Emitted from a websocket thread; Qt queues delivery onto the main thread.
    update_received = Signal(str, dict)  # storage_project_id, message
    # Emitted from a storage_cache background download thread (see
    # storage_cache.on_download_complete) -- also cross-thread-safe the same way.
    resource_ready = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._sockets = {}       # storage_project_id -> websocket.WebSocketApp
        self._pending = {}       # storage_project_id -> {card_id: card_data}
        self._push_timers = {}   # storage_project_id -> QTimer
        self._last_version = {}  # storage_project_id -> int, our own last-known version
        self.update_received.connect(self._handle_update)
        self.resource_ready.connect(self._handle_resource_ready)
        storage_cache.on_download_complete(self.resource_ready.emit)

    # ── Connection lifecycle ────────────────────────────────────────────

    def _credentials(self):
        config = self.window.config
        base_url = config.get('Shoggoth', 'publish_base_url', '')
        token = config.get('Shoggoth', 'publish_token', '')
        return base_url, token

    def start(self, storage_project_id: str):
        """Opens (or reuses) the live-sync connection for one storage
        project. Safe to call repeatedly -- a project can be opened from
        more than one place in the UI without doubling up connections."""
        if storage_project_id in self._sockets:
            return
        base_url, token = self._credentials()
        if not token:
            return

        import websocket

        ws_url = (
            base_url.replace('https://', 'wss://').replace('http://', 'ws://')
            + f'/storage/projects/{storage_project_id}/live?token={token}'
        )

        def on_message(ws, message):
            try:
                data = json.loads(message)
            except ValueError:
                return
            self.update_received.emit(storage_project_id, data)

        app = websocket.WebSocketApp(ws_url, on_message=on_message)
        self._sockets[storage_project_id] = app
        # reconnect=5: best-effort auto-reconnect (e.g. after a brief network
        # blip) rather than silently going stale until the project is
        # reopened -- a dropped connection just means live sync pauses.
        thread = threading.Thread(
            target=app.run_forever, kwargs={'reconnect': 5}, daemon=True
        )
        thread.start()

    def stop(self, storage_project_id: str):
        app = self._sockets.pop(storage_project_id, None)
        if app is not None:
            app.close()
        self._pending.pop(storage_project_id, None)
        timer = self._push_timers.pop(storage_project_id, None)
        if timer is not None:
            timer.stop()

    def stop_all(self):
        for storage_project_id in list(self._sockets):
            self.stop(storage_project_id)

    # ── Remote -> local ──────────────────────────────────────────────────

    @Slot(str, dict)
    def _handle_update(self, storage_project_id, message):
        if message.get('type') != 'project_patched':
            return
        version = message.get('version', 0)
        # Discards our own echoed write (we already applied it locally
        # before sending) and any stale/duplicate replay.
        if version <= self._last_version.get(storage_project_id, 0):
            return
        self._last_version[storage_project_id] = version

        window = self.window
        location = f'cloud://{storage_project_id}'
        project = next(
            (p for p in window.open_projects if p.get_meta('cloud_storage_location') == location),
            None,
        )
        if project is None:
            return

        patch = self._resolve_conflicts(storage_project_id, message.get('patch', {}))
        project.apply_remote_patch(patch)

        if window.active_project is project:
            window.refresh_tree()
            changed_cards = patch.get('cards') or {}
            if window.current_card and window.current_card.id in changed_cards:
                window.show_card(window.current_card)

    def _resolve_conflicts(self, storage_project_id, patch):
        """Checks the incoming patch's card ids against our own
        not-yet-flushed local edits (self._pending, populated by
        schedule_push below) -- a genuine collision: the server already has
        a newer version of a card we've also changed but haven't sent yet
        (normally within the ~1.5s push debounce window). Asks the user
        which to keep; returns a patch with conflicting card entries
        resolved (dropped, if the user kept their own version -- it'll
        still reach the server normally on its own debounced push) or the
        patch unchanged if nothing's pending."""
        cards_patch = patch.get('cards')
        pending = self._pending.get(storage_project_id)
        if not cards_patch or not pending:
            return patch

        conflicting_ids = [card_id for card_id in cards_patch if card_id in pending]
        if not conflicting_ids:
            return patch

        names = ', '.join(
            (cards_patch[card_id] or {}).get('name') or card_id for card_id in conflicting_ids
        )
        box = QMessageBox(self.window)
        box.setWindowTitle(tr("DLG_CLOUD_CONFLICT"))
        box.setText(tr("MSG_CLOUD_CONFLICT").format(cards=names))
        keep_btn = box.addButton(tr("BTN_KEEP_MINE"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("BTN_USE_THEIRS"), QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        keep_mine = box.clickedButton() is keep_btn

        resolved_cards = dict(cards_patch)
        if keep_mine:
            for card_id in conflicting_ids:
                resolved_cards.pop(card_id, None)
        else:
            for card_id in conflicting_ids:
                pending.pop(card_id, None)  # accept theirs -- drop our now-stale queued edit
        return {**patch, 'cards': resolved_cards}

    @Slot()
    def _handle_resource_ready(self):
        """A cloud:// download (kicked off by any find_file() call resolving
        an illustration/image while inside storage_cache.prefer_async, e.g.
        the synchronous first-paint render) has finished -- refresh the
        preview so it now picks up the cached file instead of staying blank
        until some unrelated re-render happens to fire. Debounced (not
        rerender_now()) since several resources for the same card can land
        in a short burst. Calls preview.schedule_update() directly (not the
        window.schedule_preview_update() facade) -- a resource finishing
        download isn't a card edit, so it must not also re-schedule a push
        of the current card's (unchanged) data."""
        self.window.preview.schedule_update()

    # ── Local -> remote ──────────────────────────────────────────────────

    def schedule_push(self):
        """Called alongside window.schedule_preview_update() -- the single
        choke point every local edit (both the direct Face.set() path and
        the FaceEditor signal-bubbling path) already funnels through, so
        this needs no separate wiring per field widget. A no-op unless the
        active project is cloud-storage-backed."""
        window = self.window
        project = window.active_project
        card = window.current_card
        if project is None or card is None:
            return
        storage_project_id = _storage_project_id(project)
        if storage_project_id is None:
            return

        self._pending.setdefault(storage_project_id, {})[card.id] = card.data

        timer = self._push_timers.get(storage_project_id)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda sid=storage_project_id: self._flush_push(sid))
            self._push_timers[storage_project_id] = timer
        timer.start(_PUSH_DEBOUNCE_MS)

    def _flush_push(self, storage_project_id: str):
        pending_cards = self._pending.pop(storage_project_id, None)
        if not pending_cards:
            return
        base_url, token = self._credentials()
        if not token:
            return

        def push_task():
            try:
                result = client.patch_storage_project(
                    base_url, token, storage_project_id, {'cards': pending_cards}
                )
                self._last_version[storage_project_id] = result.get('version', 0)
            except client.PublishError:
                # Best-effort: the next edit re-schedules a push carrying
                # this card's now-current data, so nothing is silently lost
                # beyond a delay -- no retry queue needed.
                pass

        threading.Thread(target=push_task, daemon=True).start()
