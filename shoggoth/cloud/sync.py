"""Cloud sync for projects that live in the cloud folder.

A cloud project is a normal project folder under `cloud_cache/<provider>/<id>/`
whose project file carries `meta.celaeno_id` (see shoggoth.cloud.folder).
Opening one is instant and purely local; `CloudSyncController.attach()` then
brings it in step with the server in the background:

* **Pull** (background thread): ask for the cloud copy only if it's newer than
  our `meta.celaeno_version`, then merge it element by element (project, sets,
  cards, guides) using their `meta.modified` timestamps -- see
  shoggoth.cloud.merge for the rules. Conflicts (an element changed on both
  sides since the last sync) are put to the user.
* **Resources**: relative paths inside the project are just files in that
  folder, so sync mirrors the folder -- downloads files the cloud has that we
  don't (or that changed), and uploads files added/changed locally, found by a
  folder monitor (anything that isn't a file sync itself just wrote).
* **Live**: a WebSocket per project delivers other clients' patches, merged
  the same way; local edits are pushed as small per-element patches after a
  short debounce.

Everything that touches project data runs on the main thread; background
threads only do network/file I/O and hand results back through Qt Signals
(Signal.emit is thread-safe -- the same pattern PreviewController uses).
"""
import copy
import json
import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QMessageBox
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from shoggoth.cloud import client, folder, merge
from shoggoth.i18n import tr
from shoggoth.project import Project

_PUSH_DEBOUNCE_MS = 1500
_UPLOAD_DEBOUNCE_MS = 1000
_SAVE_DEBOUNCE_MS = 2000
_RETRY_MS = 15000
_RESOURCE_REFRESH_MS = 300


class _Session:
    """Sync state for one attached project."""

    def __init__(self, project, cloud_id):
        self.project = project
        self.id = cloud_id
        self.root = Path(project.file_path).parent
        self.project_file = Path(project.file_path).name
        self.pending = set()        # {(kind, element_id)} edited, not yet pushed
        self.pushing = False
        self.pulling = False
        self.upload_queue = set()   # rel paths touched on disk, not yet uploaded
        self.manifest = folder.read_manifest(self.root)
        self.lock = threading.Lock()  # guards manifest (touched from worker threads)
        self.socket = None
        self.observer = None
        self.sent = {}              # {(kind, id): modified we last pushed (-1: deletion)}
        self.remote_floor = 0.0     # newest edit stamp taken from the cloud (see _mark_synced)
        self.push_timer = None
        self.upload_timer = None
        self.save_timer = None

    @property
    def meta(self):
        return self.project.data.setdefault('meta', {})

    @property
    def read_only(self) -> bool:
        return self.meta.get('celaeno_role') == 'viewer'

    @property
    def version(self) -> int:
        return int(self.meta.get('celaeno_version', 0) or 0)

    @property
    def synced_at(self) -> float:
        return float(self.meta.get('celaeno_synced_at', 0) or 0)

    @property
    def deleted(self) -> dict:
        return self.meta.setdefault('celaeno_deleted', {})


class _FolderHandler(FileSystemEventHandler):
    def __init__(self, on_touch):
        self.on_touch = on_touch

    def on_created(self, event):
        if not event.is_directory:
            self.on_touch(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.on_touch(event.src_path)

    def on_moved(self, event):  # atomic-replace writes arrive as a move
        if not event.is_directory:
            self.on_touch(event.dest_path)


class CloudSyncController(QObject):
    # All emitted from worker threads; Qt queues delivery onto the main thread.
    snapshot_received = Signal(str, object, float)   # cloud id, detail, pull start time
    update_received = Signal(str, object)            # cloud id, websocket message
    reconnected = Signal(str)                        # cloud id: socket (re)opened
    resource_written = Signal(str, str)              # cloud id, absolute path
    file_touched = Signal(str, str)                  # cloud id, absolute path
    push_finished = Signal(str, bool, float, object)  # id, ok, flush start, pushed keys
    status = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._sessions = {}
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._refresh_preview)

        self.snapshot_received.connect(self._apply_snapshot)
        self.update_received.connect(self._apply_patch)
        self.reconnected.connect(self._on_reconnected)
        self.resource_written.connect(self._on_resource_written)
        self.file_touched.connect(self._on_file_touched)
        self.push_finished.connect(self._on_push_finished)
        self.status.connect(self._show_status)

        Project.add_change_listener(self._on_project_change)

    # ── Attach / detach ──────────────────────────────────────────────────

    def _credentials(self):
        config = self.window.config
        return config.get('Shoggoth', 'publish_base_url', ''), config.get('Shoggoth', 'publish_token', '')

    def is_attachable(self, project) -> bool:
        return (
            project.is_cloud_project
            and not getattr(project, '_translation', None)
            and folder.is_in_cloud_cache(project.file_path)
        )

    def session_for(self, project):
        cloud_id = project.data.get('meta', {}).get('celaeno_id')
        session = self._sessions.get(cloud_id)
        return session if session and session.project is project else None

    def attach(self, project):
        """Starts syncing a just-opened cloud project (no-op for anything
        else, or when not signed in). Returns immediately."""
        if not self.is_attachable(project) or self.session_for(project):
            return
        _, token = self._credentials()
        if not token:
            return
        session = _Session(project, project.data['meta']['celaeno_id'])
        self._sessions[session.id] = session

        for name, slot in (('push_timer', self._flush_push), ('upload_timer', self._flush_uploads),
                           ('save_timer', self._autosave)):
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda s=session, f=slot: f(s))
            setattr(session, name, timer)

        self._start_monitor(session)
        self._start_socket(session)
        self._start_pull(session)

    def detach(self, project):
        session = self.session_for(project)
        if session is None:
            return
        self._flush_push(session, wait=True)
        self._teardown(session)
        self._sessions.pop(session.id, None)
        self._save(session)

    def stop_all(self):
        for session in list(self._sessions.values()):
            self.detach(session.project)

    def _teardown(self, session):
        for timer in (session.push_timer, session.upload_timer, session.save_timer):
            if timer:
                timer.stop()
        if session.socket is not None:
            session.socket.close()
            session.socket = None
        if session.observer is not None:
            session.observer.stop()
            session.observer = None

    # ── Pull (background) ────────────────────────────────────────────────

    def _start_pull(self, session):
        if session.pulling:
            return
        session.pulling = True
        base_url, token = self._credentials()
        since = session.version
        started = time.time()

        def task():
            try:
                detail = client.get_storage_project(base_url, token, session.id, since_version=since)
            except client.PublishError as exc:
                self.status.emit(str(exc))
                detail = None
            self.snapshot_received.emit(session.id, detail, started)
            try:
                self._sync_resources(session, base_url, token)
            except client.PublishError as exc:
                self.status.emit(str(exc))

        threading.Thread(target=task, daemon=True).start()

    @Slot(str, object, float)
    def _apply_snapshot(self, cloud_id, detail, started):
        session = self._sessions.get(cloud_id)
        if session is None:
            return
        session.pulling = False
        if detail is None:  # 304 (nothing newer) or the pull failed
            if not session.pending and not session.pushing:
                self._mark_synced(session, started)
            return

        project = session.project
        plan = merge.plan_snapshot(project.data, detail['data'], session.synced_at, session.deleted)
        changed, touched = self._resolve_and_apply(session, plan)
        session.meta['celaeno_version'] = max(session.version, int(detail['version']))
        if not session.pending and not session.pushing:
            self._mark_synced(session, started)
        self._after_merge(session, changed, touched)

    # ── Resources (background) ───────────────────────────────────────────

    def _sync_resources(self, session, base_url, token):
        """Mirrors the cloud project's files into the folder and vice versa.
        Runs on the pull thread."""
        remote = {f['path']: f for f in client.list_storage_files(base_url, token, session.id)
                  if not folder.is_ignored(f['path'], session.project_file)}

        for rel, info in remote.items():
            dest = session.root / rel
            with session.lock:
                record = session.manifest.get(rel)
            if dest.exists():
                if record is None:
                    continue  # a local file we've never synced: it wins, uploaded below
                if record.get('etag') == info.get('content_hash'):
                    continue  # already current
                if not folder.is_untouched(session.root, rel, {rel: record}):
                    continue  # changed locally too: keep ours, uploaded below
            self._download(session, base_url, token, rel, info, dest)

        if not session.read_only:
            self._upload_unsynced(session, base_url, token, remote)

    def _download(self, session, base_url, token, rel, info, dest):
        tmp = dest.with_name(dest.name + '.dl.tmp')  # ignored by the monitor
        try:
            client.download_storage_file(base_url, token, session.id, rel, tmp)
            os.replace(tmp, dest)
        except (client.PublishError, OSError):
            tmp.unlink(missing_ok=True)
            return
        with session.lock:
            session.manifest[rel] = folder.observe(session.root, rel, info.get('content_hash'))
            folder.write_manifest(session.root, session.manifest)
        self.resource_written.emit(session.id, str(dest))

    def _upload_unsynced(self, session, base_url, token, remote):
        for rel in folder.local_files(session.root, session.project_file):
            with session.lock:
                known = dict(session.manifest)
            if rel in known and folder.is_untouched(session.root, rel, known):
                continue
            info = remote.get(rel)
            if info is not None and rel not in known:
                # Both sides have a file we've never synced. Same size: assume
                # it's the same file and just remember it; otherwise ours wins.
                if info.get('size_bytes') == (session.root / rel).stat().st_size:
                    with session.lock:
                        session.manifest[rel] = folder.observe(session.root, rel, info.get('content_hash'))
                        folder.write_manifest(session.root, session.manifest)
                    continue
            self._upload(session, base_url, token, rel)

    def _upload(self, session, base_url, token, rel):
        path = session.root / rel
        try:
            result = client.upload_storage_file(base_url, token, session.id, rel, path)
        except (client.PublishError, OSError) as exc:
            self.status.emit(f'Upload of {rel} failed: {exc}')
            return
        with session.lock:
            session.manifest[rel] = folder.observe(session.root, rel, result.get('content_hash'))
            folder.write_manifest(session.root, session.manifest)

    # ── Folder monitor ───────────────────────────────────────────────────

    def _start_monitor(self, session):
        if not session.root.exists():
            return
        observer = Observer()
        handler = _FolderHandler(lambda path, cid=session.id: self.file_touched.emit(cid, path))
        observer.schedule(handler, str(session.root), recursive=True)
        observer.daemon = True
        observer.start()
        session.observer = observer

    @Slot(str, str)
    def _on_file_touched(self, cloud_id, path):
        session = self._sessions.get(cloud_id)
        if session is None or session.read_only:
            return
        rel = folder.rel_posix(session.root, path)
        if rel is None or folder.is_ignored(rel, session.project_file) or not (session.root / rel).is_file():
            return
        with session.lock:
            if folder.is_untouched(session.root, rel, session.manifest):
                return  # a file sync itself just wrote
        session.upload_queue.add(rel)
        session.upload_timer.start(_UPLOAD_DEBOUNCE_MS)

    def _flush_uploads(self, session):
        queue, session.upload_queue = session.upload_queue, set()
        if not queue:
            return
        base_url, token = self._credentials()

        def task():
            for rel in sorted(queue):
                with session.lock:
                    if folder.is_untouched(session.root, rel, session.manifest):
                        continue
                if (session.root / rel).is_file():
                    self._upload(session, base_url, token, rel)

        threading.Thread(target=task, daemon=True).start()

    @Slot(str, str)
    def _on_resource_written(self, cloud_id, path):
        """A file finished downloading: drop the renderer's cached copy and
        schedule a (debounced) preview refresh so it shows up."""
        self.window.card_renderer.invalidate_cache(path)
        self._refresh_timer.start(_RESOURCE_REFRESH_MS)

    def _refresh_preview(self):
        self.window.preview.schedule_update()

    # ── WebSocket ────────────────────────────────────────────────────────

    def _start_socket(self, session):
        base_url, token = self._credentials()
        import websocket

        ws_url = (
            base_url.replace('https://', 'wss://').replace('http://', 'ws://')
            + f'/storage/projects/{session.id}/live?token={token}'
        )

        def on_message(ws, message):
            try:
                data = json.loads(message)
            except ValueError:
                return
            self.update_received.emit(session.id, data)

        app = websocket.WebSocketApp(
            ws_url, on_message=on_message, on_open=lambda ws: self.reconnected.emit(session.id)
        )
        session.socket = app
        # reconnect=5: best-effort auto-reconnect after a network blip; every
        # (re)open triggers a pull (see _on_reconnected), which fills any gap.
        threading.Thread(target=app.run_forever, kwargs={'reconnect': 5}, daemon=True).start()

    @Slot(str)
    def _on_reconnected(self, cloud_id):
        session = self._sessions.get(cloud_id)
        if session is not None:
            self._start_pull(session)

    @Slot(str, object)
    def _apply_patch(self, cloud_id, message):
        session = self._sessions.get(cloud_id)
        if session is None or message.get('type') != 'project_patched':
            return
        version = int(message.get('version', 0))
        if version <= session.version:
            return  # stale replay
        if version != session.version + 1:
            self._start_pull(session)  # we missed something: resync instead of guessing
            return

        patch = self._without_own_echo(session, message.get('patch', {}))
        plan = merge.plan_patch(session.project.data, patch, session.synced_at, session.deleted)
        changed, touched = self._resolve_and_apply(session, plan)
        session.meta['celaeno_version'] = version
        if not session.pending and not session.pushing:
            self._mark_synced(session, time.time())
        self._after_merge(session, changed, touched)

    # ── Applying a plan ──────────────────────────────────────────────────

    def _resolve_and_apply(self, session, plan):
        """Puts conflicts to the user (one question for the whole batch), then
        applies the plan to the project and queues what needs pushing. Returns
        (anything_changed_locally, ids_of_elements_replaced_or_removed)."""
        project = session.project
        keep_mine = True
        if session.read_only:
            keep_mine = False  # a viewer never pushes, so the cloud always wins
        elif plan.conflicts:
            keep_mine = self._ask_conflicts(plan.conflicts)

        for conflict in plan.conflicts:
            if conflict.kind == 'project':
                if keep_mine:
                    plan.push_project = conflict.local
                else:
                    plan.take_project = conflict.remote
            elif keep_mine:
                plan.push_element(conflict.kind, conflict.element_id, conflict.local)
            elif conflict.remote is None:
                plan.remove.append((conflict.kind, conflict.element_id))
            else:
                plan.take.append((conflict.kind, conflict.element_id, conflict.remote))

        for kind, element_id, element in plan.take:
            merge.apply_take(project.data, kind, element_id, element)
            session.deleted.pop(element_id, None)
            session.remote_floor = max(session.remote_floor, merge.modified(element))
        for kind, element_id in plan.remove:
            merge.apply_remove(project.data, kind, element_id)
        if plan.take_project:
            merge.apply_project_fields(project.data, plan.take_project)

        if not session.read_only:
            for kind, elements in plan.push.items():
                for element_id in elements:
                    session.pending.add((kind, element_id))
            if plan.push_project is not None:
                session.pending.add(('project', project.id))

        changed = bool(plan.take or plan.remove or plan.take_project)
        touched = {i for _, i, _ in plan.take} | {i for _, i in plan.remove}
        return changed, touched

    def _ask_conflicts(self, conflicts) -> bool:
        """True to keep the user's own versions, False to take the cloud's."""
        names = ', '.join(
            merge.element_name(c.local) or merge.element_name(c.remote) or c.element_id
            for c in conflicts
        )
        box = QMessageBox(self.window)
        box.setWindowTitle(tr("DLG_CLOUD_CONFLICT"))
        box.setText(tr("MSG_CLOUD_CONFLICT").format(cards=names))
        keep_btn = box.addButton(tr("BTN_KEEP_MINE"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("BTN_USE_THEIRS"), QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        return box.clickedButton() is keep_btn

    def _after_merge(self, session, changed, touched):
        window = self.window
        if changed and window.active_project is session.project:
            window.refresh_tree()
            current = window.current_card
            if current is not None:
                if any(c.get('id') == current.id for c in session.project.data.get('cards', [])):
                    if current.id in touched:
                        window.show_card(current)
                else:
                    window.clear_editor()
        if session.pending:
            self._flush_push(session)
        session.save_timer.start(_SAVE_DEBOUNCE_MS)

    # ── Push (local -> cloud) ────────────────────────────────────────────

    def _on_project_change(self, project, kind, element_id, changed):
        """Project change-listener: queues edited elements for the next push.
        Runs on the main thread, wherever the edit happened."""
        if not changed:
            return
        session = self.session_for(project)
        if session is None or session.read_only:
            return
        session.pending.add((kind, element_id))
        session.push_timer.start(_PUSH_DEBOUNCE_MS)
        session.save_timer.start(_SAVE_DEBOUNCE_MS)

    def _build_patch(self, session, keys):
        data = session.project.data
        patch = {}
        for kind, element_id in keys:
            if kind == 'project':
                fields = merge.project_fields(data)
                patch.update(fields)
                session.sent[('project', element_id)] = merge.modified(fields)
                continue
            element = next((e for e in data.get(kind, []) if e.get('id') == element_id), None)
            patch.setdefault(kind, {})[element_id] = copy.deepcopy(element)  # None = deleted
            session.sent[(kind, element_id)] = merge.modified(element) if element else -1
        return patch

    def _without_own_echo(self, session, patch):
        """Drops elements from an incoming patch that are just the server
        echoing back what this client pushed (same edit timestamp) -- they
        can arrive before our own push's HTTP response does, i.e. before
        synced_at has caught up, and would otherwise look like a competing
        remote edit if the user has typed more since."""
        filtered = {}
        for kind in merge.ELEMENT_KINDS:
            elements = {
                element_id: element
                for element_id, element in (patch.get(kind) or {}).items()
                if session.sent.get((kind, element_id)) != (merge.modified(element) if element else -1)
            }
            if elements:
                filtered[kind] = elements
        rest = {k: v for k, v in patch.items() if k not in merge.ELEMENT_KINDS}
        if rest and session.sent.get(('project', session.project.id)) == merge.modified(rest):
            rest = {}
        filtered.update(rest)
        return filtered

    def _flush_push(self, session, wait=False):
        if not session.pending or session.pushing:
            return
        keys, session.pending = set(session.pending), set()
        patch = self._build_patch(session, keys)
        started = time.time()
        base_url, token = self._credentials()
        session.pushing = True

        def task():
            ok = True
            try:
                client.patch_storage_project(base_url, token, session.id, patch)
            except client.PublishError as exc:
                ok = False
                self.status.emit(str(exc))
            self.push_finished.emit(session.id, ok, started, keys)

        thread = threading.Thread(target=task, daemon=True)
        thread.start()
        if wait:
            thread.join(timeout=5)

    @Slot(str, bool, float, object)
    def _on_push_finished(self, cloud_id, ok, started, keys):
        session = self._sessions.get(cloud_id)
        if session is None:
            return
        session.pushing = False
        if not ok:
            session.pending |= keys
            session.push_timer.start(_RETRY_MS)
            return
        for kind, element_id in keys:
            if kind != 'project' and element_id in session.deleted:
                session.deleted.pop(element_id, None)
        # Everything edited before this flush began is now in the cloud.
        self._mark_synced(session, started)
        if session.pending:
            session.push_timer.start(_PUSH_DEBOUNCE_MS)
        session.save_timer.start(_SAVE_DEBOUNCE_MS)

    # ── Bookkeeping ──────────────────────────────────────────────────────

    def _mark_synced(self, session, when):
        """Records "local and cloud agreed as of `when`". Never earlier than
        the newest edit stamp we've taken from the cloud: those stamps come
        from other machines' clocks, and one running ahead of ours would
        otherwise keep looking "changed since the last sync" and cause
        phantom conflicts."""
        session.meta['celaeno_synced_at'] = max(session.synced_at, when, session.remote_floor)

    def _autosave(self, session):
        self._save(session)

    def _save(self, session):
        """Cloud projects autosave: the file on disk mirrors what's been
        merged/pushed, so reopening never starts from a stale copy. Writes the
        meta directly (not via set_meta) so it doesn't itself count as an edit."""
        try:
            session.project.save_all()
        except OSError as exc:
            self.status.emit(str(exc))

    @Slot(str)
    def _show_status(self, message):
        self.window.status_bar.showMessage(message, 5000)
